"""Minimal .onnx writer used to exercise the ONNX backend in tests and CI.

It builds a graph that maps the flat input (1, H, W, C) to a fixed logit
vector, so `OnnxPredictor` runs its real code path - session creation, tensor
binding, softmax, label mapping - without a trained model.

Only used by tests and local tooling, never imported by the service.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.domain import ScanType, known_labels


def build_fixture_onnx(output: Path, *, labels: list[str], input_size: int) -> None:
    from onnx import TensorProto, helper

    logits = [0.1 * index for index in range(len(labels))]
    initializer = helper.make_tensor(
        name="logits",
        data_type=TensorProto.FLOAT,
        dims=[1, len(labels)],
        vals=logits,
    )
    add = helper.make_node("Add", inputs=["input", "constant_zero"], outputs=["shifted"])
    drop = helper.make_node("ReduceMean", inputs=["shifted"], outputs=["summary"], keepdims=0)
    reshape = helper.make_node("Reshape", inputs=["logits", "shape"], outputs=["output"])
    shape = helper.make_tensor(
        name="shape",
        data_type=TensorProto.INT64,
        dims=[2],
        vals=[1, len(labels)],
    )
    zero = helper.make_tensor(
        name="constant_zero", data_type=TensorProto.FLOAT, dims=[1], vals=[0.0]
    )

    graph = helper.make_graph(
        nodes=[add, drop, reshape],
        name="tanami_fixture",
        inputs=[
            helper.make_tensor_value_info(
                "input", TensorProto.FLOAT, [1, input_size, input_size, 3]
            )
        ],
        outputs=[helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, len(labels)])],
        initializer=[initializer, shape, zero],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
    model.ir_version = 10
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(model.SerializeToString())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-type", choices=["disease", "ripeness"], default="disease")
    parser.add_argument("--version", required=True)
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    args = parser.parse_args()

    scan_type = ScanType(args.scan_type)
    target = args.model_dir / args.version
    build_fixture_onnx(target / "model.onnx", labels=list(known_labels(scan_type)), input_size=224)
    manifest = {
        "model_version": args.version,
        "scan_type": scan_type.value,
        "commodity_code": "chili",
        "artifact": "model.onnx",
        "labels": list(known_labels(scan_type)),
        "input_size": 224,
        "input_name": "input",
        "output_name": "output",
        "normalization": "zero_one",
        "output_activation": "softmax",
        "sha256": "",
        "metrics": {"source": "fixture"},
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote fixture model to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
