import { useEffect, useState } from "react";

import { apiPage, apiSend } from "../api/client";
import type { FeedbackItem } from "../api/types";
import { Empty, ErrorNotice, Loading, PageHead } from "../components/States";
import { useToast } from "../components/Toast";
import { formatDateTime, formatRelative } from "../lib/format";
import { labelName } from "../lib/labels";
import { messageOf, useLoad } from "../lib/useLoad";

type Tab = "waiting" | "done";

function predictedLabel(item: FeedbackItem): { code: string | null; confidence: number | null } {
  const predicted = item.predicted ?? {};
  const code = (item.scan_type === "disease" ? predicted["disease_code"] : predicted["stage"]) as string | undefined;
  const confidence = predicted["confidence"];
  return { code: code ?? null, confidence: typeof confidence === "number" ? confidence : null };
}

function Detail({ item, onSaved }: { item: FeedbackItem; onSaved: (updated: FeedbackItem) => void }) {
  const toast = useToast();
  const prediction = predictedLabel(item);
  const [choice, setChoice] = useState<string>(item.correct_label ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => setChoice(item.correct_label ?? ""), [item.id, item.correct_label]);

  async function save() {
    if (!choice) return;
    setSaving(true);
    try {
      const updated = await apiSend<FeedbackItem>("PATCH", `/review/feedback/${item.id}`, { correct_label: choice });
      toast.show(`Label ${labelName(choice).toLowerCase()} disimpan.`);
      window.dispatchEvent(new Event("tanami:queues-changed"));
      onSaved(updated);
    } catch (reason) {
      toast.error(messageOf(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="review-detail" aria-labelledby="review-title">
      <img className="review-photo" src={item.image_url} alt="Foto yang dikirim petani" />

      <div className="review-facts">
        <div>
          <h2 id="review-title">
            Model membaca {labelName(prediction.code).toLowerCase()}
            {prediction.confidence !== null ? `, ${Math.round(prediction.confidence * 100)}% yakin` : ""}
          </h2>
          <p className="review-sub">
            Foto {item.scan_type === "disease" ? "daun" : "buah"}, dikirim {formatDateTime(item.created_at)}, model{" "}
            {item.model_version}
          </p>
        </div>
        <div className="review-farmer">
          <p className="review-farmer-label">Petani menandai hasil ini salah</p>
          <p className="review-farmer-text">{item.comment ? `"${item.comment}"` : "Tanpa catatan."}</p>
        </div>
        <p className={item.consent_training_data ? "notice notice-calm" : "notice"}>
          {item.consent_training_data
            ? "Petani mengizinkan foto ini dipakai untuk melatih ulang model."
            : "Petani tidak mengizinkan foto ini dipakai untuk pelatihan. Label Anda tetap dicatat untuk evaluasi model."}
        </p>
      </div>

      <fieldset className="label-picker">
        <legend>Label yang benar</legend>
        <div className="label-options">
          {item.allowed_labels.map((code) => (
            <label key={code} className={choice === code ? "label-option is-chosen" : "label-option"}>
              <input
                type="radio"
                name={`label-${item.id}`}
                value={code}
                checked={choice === code}
                onChange={() => setChoice(code)}
              />
              <span>{labelName(code)}</span>
              {code === prediction.code ? <span className="label-model">tebakan model</span> : null}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="review-actions">
        <button type="button" className="btn btn-primary" disabled={!choice || saving} onClick={() => void save()}>
          {saving ? "Menyimpan..." : item.reviewed_at ? "Perbarui label" : "Simpan label"}
        </button>
        {item.reviewed_at ? <span className="field-hint">Ditinjau {formatRelative(item.reviewed_at)}</span> : null}
      </div>
    </article>
  );
}

export function Review() {
  const [tab, setTab] = useState<Tab>("waiting");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, error, loading, reload, setData } = useLoad(
    () => apiPage<FeedbackItem>("/review/feedback", { reviewed: tab === "done", limit: 100 }),
    tab,
  );

  const items = data?.data ?? [];
  const selected = items.find((item) => item.id === selectedId) ?? items[0] ?? null;

  function onSaved(updated: FeedbackItem) {
    if (tab === "waiting") {
      const index = items.findIndex((item) => item.id === updated.id);
      const next = items[index + 1] ?? items[index - 1] ?? null;
      setData((current) => (current ? { ...current, data: current.data.filter((item) => item.id !== updated.id) } : current));
      setSelectedId(next?.id ?? null);
    } else {
      setData((current) =>
        current ? { ...current, data: current.data.map((item) => (item.id === updated.id ? updated : item)) } : current,
      );
    }
  }

  return (
    <>
      <PageHead
        title="Tinjauan deteksi"
        intro="Hasil deteksi yang ditandai salah oleh petani. Pilih label yang benar agar model bisa dievaluasi dan, bila petani mengizinkan, dilatih ulang."
        actions={
          <div className="segmented" role="group" aria-label="Status tinjauan">
            <button type="button" aria-pressed={tab === "waiting"} onClick={() => setTab("waiting")}>
              Menunggu
            </button>
            <button type="button" aria-pressed={tab === "done"} onClick={() => setTab("done")}>
              Sudah ditinjau
            </button>
          </div>
        }
      />
      {loading && !data ? <Loading /> : null}
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
      {data && items.length === 0 ? (
        <Empty title={tab === "waiting" ? "Semua hasil sudah ditinjau" : "Belum ada yang ditinjau"}>
          {tab === "waiting"
            ? "Hasil baru yang ditandai salah oleh petani akan muncul di sini."
            : "Label yang Anda simpan akan tercatat di sini."}
        </Empty>
      ) : null}

      {items.length > 0 && selected ? (
        <div className="review">
          <ul className="review-queue" aria-label="Antrean">
            {items.map((item) => {
              const prediction = predictedLabel(item);
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className="queue-item"
                    aria-current={item.id === selected.id ? "true" : undefined}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <img src={item.image_url} alt="" />
                    <span>
                      <span className="queue-title">{labelName(prediction.code)}</span>
                      <span className="queue-sub">
                        {item.correct_label ? `Benar: ${labelName(item.correct_label)}` : formatRelative(item.created_at)}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <Detail key={selected.id} item={selected} onSaved={onSaved} />
        </div>
      ) : null}
    </>
  );
}
