import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError, apiPage, apiSend } from "../api/client";
import type { Broadcast, StaffUser } from "../api/types";
import { LeafMark } from "../components/Icons";
import { ConfirmDialog } from "../components/Overlay";
import { Empty, ErrorNotice, Loading, PageHead } from "../components/States";
import { useToast } from "../components/Toast";
import { formatDateTime, formatNumber } from "../lib/format";
import { useLoad } from "../lib/useLoad";

interface Recipient {
  id: string;
  name: string;
}

function RecipientPicker({ value, onChange }: { value: Recipient | null; onChange: (r: Recipient | null) => void }) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<StaffUser[]>([]);

  useEffect(() => {
    if (term.trim().length < 2) {
      setResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      apiPage<StaffUser>("/admin/users", { q: term, limit: 6 })
        .then((page) => setResults(page.data))
        .catch(() => setResults([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [term]);

  if (value) {
    return (
      <div className="recipient-chosen">
        <span>{value.name}</span>
        <button type="button" className="btn btn-link" onClick={() => onChange(null)}>
          Ganti
        </button>
      </div>
    );
  }
  return (
    <div className="recipient-search">
      <input
        className="input"
        type="search"
        placeholder="Ketik nama atau username"
        aria-label="Cari penerima"
        value={term}
        onChange={(event) => setTerm(event.target.value)}
      />
      {results.length > 0 ? (
        <ul className="recipient-results">
          {results.map((user) => (
            <li key={user.id}>
              <button type="button" onClick={() => onChange({ id: user.id, name: user.full_name })}>
                <span>{user.full_name}</span>
                <span className="cell-sub">@{user.username}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function PhonePreview({ title, body }: { title: string; body: string }) {
  return (
    <div className="phone" aria-label="Pratinjau notifikasi di ponsel petani">
      <div className="phone-notice">
        <div className="phone-app">
          <LeafMark width={18} height={18} />
          <span>Tanami</span>
          <span className="phone-time">sekarang</span>
        </div>
        <p className="phone-title">{title || "Judul pengumuman"}</p>
        <p className="phone-body">{body || "Isi pengumuman akan tampil di sini."}</p>
      </div>
    </div>
  );
}

export function Announcements() {
  const toast = useToast();
  const [params] = useSearchParams();
  const preset = params.get("user");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState<"all" | "user">(preset ? "user" : "all");
  const [recipient, setRecipient] = useState<Recipient | null>(
    preset ? { id: preset, name: params.get("nama") ?? "Pengguna terpilih" } : null,
  );
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const history = useLoad(() => apiPage<Broadcast>("/admin/reminders/general", { limit: 30 }), "broadcasts");

  const titleOk = title.trim().length >= 5;
  const ready = titleOk && body.trim().length > 0 && (audience === "all" || recipient !== null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (ready) setConfirming(true);
  }

  async function send() {
    setSending(true);
    setProblem(null);
    try {
      const result = await apiSend<{ created: number }>("POST", "/admin/reminders/general", {
        title: title.trim(),
        body: body.trim(),
        user_id: audience === "user" ? recipient?.id : undefined,
      });
      toast.show(`Pengumuman terkirim ke ${formatNumber(result.created)} akun.`);
      setTitle("");
      setBody("");
      setConfirming(false);
      history.reload();
    } catch (reason) {
      setProblem(reason instanceof ApiError ? reason.message : "Pengumuman gagal dikirim. Coba lagi.");
      setConfirming(false);
    } finally {
      setSending(false);
    }
  }

  const items = history.data?.data ?? [];

  return (
    <>
      <PageHead
        title="Pengumuman"
        intro="Pesan dari tim Tanami yang muncul sebagai notifikasi di aplikasi petani. Pengumuman berlaku tujuh hari. Pada jam tenang pengguna, notifikasinya ditunda sampai pagi."
      />

      <div className="compose">
        <form className="compose-form" onSubmit={submit} noValidate>
          {problem ? (
            <p className="notice" role="alert">
              {problem}
            </p>
          ) : null}
          <div className="field">
            <label className="field-label" htmlFor="announce-title">
              Judul
            </label>
            <input
              id="announce-title"
              className="input"
              maxLength={140}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
            <span className="field-hint num">{title.length} dari 140 karakter, minimal 5</span>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="announce-body">
              Isi
            </label>
            <textarea
              id="announce-body"
              className="textarea"
              rows={5}
              maxLength={1000}
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
            <span className="field-hint num">{body.length} dari 1000 karakter</span>
          </div>
          <fieldset className="audience">
            <legend className="field-label">Penerima</legend>
            <label className="check">
              <input type="radio" name="audience" checked={audience === "all"} onChange={() => setAudience("all")} />
              Semua akun aktif
            </label>
            <label className="check">
              <input type="radio" name="audience" checked={audience === "user"} onChange={() => setAudience("user")} />
              Satu pengguna
            </label>
            {audience === "user" ? <RecipientPicker value={recipient} onChange={setRecipient} /> : null}
          </fieldset>
          <div>
            <button type="submit" className="btn btn-primary" disabled={!ready}>
              Kirim pengumuman
            </button>
          </div>
        </form>
        <PhonePreview title={title} body={body} />
      </div>

      <section className="history" aria-labelledby="history-title">
        <div className="section-head">
          <h2 id="history-title">Sudah dikirim</h2>
        </div>
        {history.loading && !history.data ? <Loading /> : null}
        {history.error ? <ErrorNotice message={history.error} onRetry={history.reload} /> : null}
        {history.data && items.length === 0 ? (
          <Empty title="Belum ada pengumuman">Pengumuman yang Anda kirim akan tercatat di sini.</Empty>
        ) : null}
        <ul className="history-list">
          {items.map((item) => (
            <li key={item.batch} className="history-item">
              <div>
                <p className="history-title">{item.title}</p>
                <p className="history-body">{item.body}</p>
              </div>
              <div className="history-meta">
                <span>{formatDateTime(item.sent_at)}</span>
                <span>{item.audience === "all" ? "Semua akun" : "Satu pengguna"}</span>
                <span className="num">
                  Dibaca {formatNumber(item.read)} dari {formatNumber(item.recipients)}
                </span>
                <span className="read-line" aria-hidden="true">
                  <span style={{ width: `${(item.read / Math.max(1, item.recipients)) * 100}%` }} />
                </span>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <ConfirmDialog
        open={confirming}
        title={audience === "all" ? "Kirim ke semua akun aktif?" : `Kirim ke ${recipient?.name ?? "pengguna ini"}?`}
        confirmLabel="Kirim pengumuman"
        busy={sending}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void send()}
      >
        Pengumuman tidak bisa ditarik kembali setelah dikirim.
      </ConfirmDialog>
    </>
  );
}
