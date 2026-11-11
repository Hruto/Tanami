import { useState } from "react";

import { apiPage, apiSend } from "../api/client";
import type { ReportAction, ReportedTarget } from "../api/types";
import { ConfirmDialog } from "../components/Overlay";
import { Empty, ErrorNotice, Loading, PageHead } from "../components/States";
import { useToast } from "../components/Toast";
import { formatDateTime, formatNumber, formatRelative } from "../lib/format";
import { REASON_LABEL } from "../lib/labels";
import { messageOf, useLoad } from "../lib/useLoad";

const DONE: Record<ReportAction, string> = {
  dismiss: "Laporan diabaikan. Konten tampil lagi di forum.",
  hide: "Konten disembunyikan dari forum.",
  remove: "Konten dihapus dari forum.",
};

interface Pending {
  target: ReportedTarget;
  action: ReportAction;
}

export function Reports() {
  const toast = useToast();
  const { data, error, loading, reload, setData } = useLoad(
    () => apiPage<ReportedTarget>("/moderation/reports", { limit: 100 }),
    "reports",
  );
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);

  async function resolve({ target, action }: Pending) {
    setBusy(true);
    try {
      await apiSend("POST", `/moderation/reports/${target.target_type}/${target.target_id}/resolve`, { action });
      setData((current) =>
        current ? { ...current, data: current.data.filter((item) => item.target_id !== target.target_id) } : current,
      );
      toast.show(DONE[action]);
      window.dispatchEvent(new Event("tanami:queues-changed"));
      setPending(null);
    } catch (reason) {
      toast.error(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  const items = data?.data ?? [];

  return (
    <>
      <PageHead
        title="Laporan forum"
        intro="Konten yang dilaporkan petani, yang paling lama menunggu di atas. Konten dengan tiga laporan atau lebih sudah disembunyikan otomatis sampai Anda memutuskan."
      />
      {loading && !data ? <Loading /> : null}
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
      {data && items.length === 0 ? (
        <Empty title="Tidak ada laporan yang menunggu">Laporan baru dari petani akan muncul di sini.</Empty>
      ) : null}

      {items.length > 0 ? (
        <ol className="report-list">
          {items.map((item) => (
            <li key={item.target_id} className="report">
              <div className="report-body">
                <p className="report-kind">
                  {item.target_type === "post" ? "Postingan" : "Komentar"} oleh {item.author.display_name}{" "}
                  <span className="report-handle">@{item.author.username}</span>
                </p>
                <blockquote className="report-excerpt">{item.excerpt}</blockquote>
                <div className="report-reasons">
                  {Object.entries(item.reasons).map(([reason, count]) => (
                    <span key={reason} className="tag">
                      {REASON_LABEL[reason] ?? reason}
                      {count > 1 ? ` (${formatNumber(count)})` : ""}
                    </span>
                  ))}
                </div>
              </div>

              <div className="report-meta">
                <span className={item.status === "hidden" ? "mark mark-wait" : "mark mark-ok"}>
                  {item.status === "hidden" ? "Disembunyikan sementara" : "Masih tampil"}
                </span>
                <span>{formatNumber(item.report_count)} laporan</span>
                <span title={formatDateTime(item.first_reported_at)}>
                  Pertama dilaporkan {formatRelative(item.first_reported_at)}
                </span>
              </div>

              <div className="report-actions">
                <button
                  type="button"
                  className="btn btn-quiet btn-small"
                  onClick={() => void resolve({ target: item, action: "dismiss" })}
                >
                  Abaikan laporan
                </button>
                <button
                  type="button"
                  className="btn btn-quiet btn-small"
                  onClick={() => void resolve({ target: item, action: "hide" })}
                >
                  {item.status === "hidden" ? "Tetap sembunyikan" : "Sembunyikan"}
                </button>
                <button
                  type="button"
                  className="btn btn-danger btn-small"
                  onClick={() => setPending({ target: item, action: "remove" })}
                >
                  Hapus konten
                </button>
              </div>
            </li>
          ))}
        </ol>
      ) : null}

      <ConfirmDialog
        open={pending !== null}
        title="Hapus konten ini?"
        confirmLabel="Hapus konten"
        tone="danger"
        busy={busy}
        onCancel={() => setPending(null)}
        onConfirm={() => pending && void resolve(pending)}
      >
        {pending?.target.target_type === "post"
          ? "Postingan beserta komentarnya tidak akan tampil lagi di forum. Penulis tetap bisa melihat bahwa postingannya dihapus."
          : "Komentar ini tidak akan tampil lagi di forum."}
      </ConfirmDialog>
    </>
  );
}
