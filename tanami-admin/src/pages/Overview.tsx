import { Link } from "react-router-dom";

import { apiGet } from "../api/client";
import type { Overview as OverviewData } from "../api/types";
import { useMe } from "../auth/AuthContext";
import { StemChart } from "../components/StemChart";
import { ErrorNotice, Loading } from "../components/States";
import { canUse } from "../lib/access";
import { firstName, formatDateLong, formatNumber, greeting } from "../lib/format";
import { OUTCOME_LABEL, ROLE_LABEL, STATUS_LABEL } from "../lib/labels";
import { useLoad } from "../lib/useLoad";

function plural(count: number, noun: string): string {
  return `${formatNumber(count)} ${noun}`;
}

function Brief({ data }: { data: OverviewData }) {
  const me = useMe();
  const { open_reports: reports, feedback_pending: feedback } = data.queues;
  const reportText = plural(reports, "laporan forum");
  const feedbackText = plural(feedback, "hasil deteksi");

  const reportPart = canUse(me.role, "reports") ? <Link to="/laporan">{reportText}</Link> : reportText;
  const feedbackPart = canUse(me.role, "review") ? <Link to="/tinjauan">{feedbackText}</Link> : feedbackText;

  let queues;
  if (reports === 0 && feedback === 0) {
    queues = <>Tidak ada antrean yang menunggu. Semua laporan dan tinjauan sudah diselesaikan.</>;
  } else if (reports > 0 && feedback > 0) {
    queues = (
      <>
        Ada {reportPart} yang menunggu keputusan dan {feedbackPart} yang ditandai salah oleh petani.
      </>
    );
  } else if (reports > 0) {
    queues = <>Ada {reportPart} yang menunggu keputusan moderator.</>;
  } else {
    queues = <>Ada {feedbackPart} yang ditandai salah oleh petani dan perlu ditinjau ahli.</>;
  }

  return (
    <p className="brief">
      {queues} Dalam tujuh hari terakhir {plural(data.detection.scans_7d, "foto")} dianalisis dan{" "}
      {plural(data.users.new_7d, "pengguna baru")} bergabung.
    </p>
  );
}

function OutcomeBar({ outcomes }: { outcomes: OverviewData["tracking"]["outcomes"] }) {
  const order = ["failed", "suboptimal", "normal", "bumper"] as const;
  const total = order.reduce((sum, key) => sum + outcomes[key], 0);
  if (total === 0) return <p className="ledger-note">Belum ada tanaman yang selesai dipanen.</p>;
  return (
    <div className="outcomes">
      <div className="outcome-bar" aria-hidden="true">
        {order.map((key) =>
          outcomes[key] > 0 ? (
            <span key={key} className={`outcome outcome-${key}`} style={{ flexGrow: outcomes[key] }} />
          ) : null,
        )}
      </div>
      <dl className="ledger-list">
        {order.map((key) => (
          <div key={key} className="ledger-row">
            <dt>
              <span className={`swatch outcome-${key}`} aria-hidden="true" />
              {OUTCOME_LABEL[key]}
            </dt>
            <dd className="num">{formatNumber(outcomes[key])}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Overview() {
  const me = useMe();
  const { data, error, loading, reload } = useLoad(() => apiGet<OverviewData>("/admin/overview"), "overview");

  return (
    <div className="overview">
      <p className="overview-date">{formatDateLong(new Date())}</p>
      <h1>
        {greeting()}, {firstName(me.full_name)}.
      </h1>

      {loading && !data ? <Loading /> : null}
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}

      {data ? (
        <>
          <Brief data={data} />

          <section className="overview-section" aria-labelledby="activity-title">
            <div className="section-head">
              <h2 id="activity-title">Aktivitas deteksi</h2>
              <p className="section-aside num">
                {formatNumber(data.detection.scans_total)} foto sejak awal,{" "}
                {formatNumber(data.detection.active_detection_plants)} tanaman deteksi aktif
              </p>
            </div>
            <StemChart days={data.scans_daily} />
          </section>

          <section className="ledger" aria-label="Rincian">
            <div className="ledger-col">
              <h2>Pengguna</h2>
              <p className="ledger-figure num">{formatNumber(data.users.total)}</p>
              <dl className="ledger-list">
                {(["farmer", "expert", "moderator", "admin"] as const).map((role) => (
                  <div key={role} className="ledger-row">
                    <dt>{ROLE_LABEL[role]}</dt>
                    <dd className="num">{formatNumber(data.users.by_role[role] ?? 0)}</dd>
                  </div>
                ))}
                {data.users.pending_deletion > 0 ? (
                  <div className="ledger-row">
                    <dt>Menunggu penghapusan</dt>
                    <dd className="num">{formatNumber(data.users.pending_deletion)}</dd>
                  </div>
                ) : null}
              </dl>
            </div>

            <div className="ledger-col">
              <h2>Tanaman dipantau</h2>
              <p className="ledger-figure num">{formatNumber(data.tracking.active_plants)}</p>
              <p className="ledger-note">
                masih dipantau, {formatNumber(data.tracking.ended_plants)} sudah selesai. Hasil akhir
                yang dilaporkan petani:
              </p>
              <OutcomeBar outcomes={data.tracking.outcomes} />
            </div>

            <div className="ledger-col">
              <h2>Deteksi 30 hari</h2>
              <dl className="ledger-list">
                {Object.keys(STATUS_LABEL).map((status) => (
                  <div key={status} className="ledger-row">
                    <dt>{STATUS_LABEL[status]}</dt>
                    <dd className="num">{formatNumber(data.scan_status_30d[status] ?? 0)}</dd>
                  </div>
                ))}
              </dl>
              <h3 className="ledger-sub">Penyakit paling sering</h3>
              {data.top_diseases_30d.length === 0 ? (
                <p className="ledger-note">Belum ada penyakit yang terdeteksi.</p>
              ) : (
                <ol className="rank">
                  {data.top_diseases_30d.map((item) => (
                    <li key={item.code}>
                      <span>{item.name}</span>
                      <span className="rank-bar" aria-hidden="true">
                        <span style={{ width: `${(item.count / (data.top_diseases_30d[0]?.count || 1)) * 100}%` }} />
                      </span>
                      <span className="num">{formatNumber(item.count)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
