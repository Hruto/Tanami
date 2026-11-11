import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { LeafMark } from "../components/Icons";

// A chili plant drawn as a single herbarium sketch for the sign-in panel.
function ChiliSketch() {
  return (
    <svg className="sketch" viewBox="0 0 320 420" fill="none" aria-hidden="true">
      <g stroke="#a7bd8a" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M160 410C158 330 162 250 150 170C144 128 150 92 168 52" />
        <path d="M156 300C128 284 104 262 92 230" />
        <path d="M152 220C176 204 204 196 236 198" />
        <path d="M150 160C126 146 112 124 108 98" />
        <path d="M92 230C70 236 52 226 42 206C66 198 84 206 92 230Z" />
        <path d="M236 198C252 182 274 180 292 190C276 208 256 210 236 198Z" />
        <path d="M108 98C92 84 90 64 98 46C114 58 118 78 108 98Z" />
        <path d="M168 52C182 40 200 38 214 44C204 60 186 64 168 52Z" />
        <path d="M156 300C176 312 190 334 194 360C172 352 158 330 156 300Z" />
      </g>
      <g stroke="#ede6d2" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M206 202C214 226 214 252 204 278C198 258 198 230 206 202Z" />
        <path d="M120 246C118 270 124 292 138 310C142 290 136 266 120 246Z" />
        <path d="M204 196c2-6 6-9 11-9" />
        <path d="M120 240c-1-6 1-11 6-14" />
      </g>
      <path d="M130 410h70" stroke="#a7bd8a" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

export function Login() {
  const { signIn } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(identifier, password);
    } catch (reason) {
      setError(
        reason instanceof ApiError && reason.status !== 401
          ? reason.message
          : "Email, username, atau sandi tidak cocok. Periksa lalu coba lagi.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <aside className="login-panel">
        <div className="wordmark">
          <LeafMark />
          <span className="wordmark-name">Tanami</span>
        </div>
        <ChiliSketch />
        <p className="login-note">
          Ruang kerja untuk ahli, moderator, dan admin yang menjaga hasil deteksi tetap benar dan forum tetap aman.
        </p>
      </aside>
      <main className="login-main">
        <form className="login-form" onSubmit={submit}>
          <h1>Masuk ke ruang kerja tim</h1>
          <p className="page-intro">Gunakan akun Tanami yang sudah diberi peran ahli, moderator, atau admin.</p>
          {error ? (
            <p className="notice" role="alert">
              {error}
            </p>
          ) : null}
          <div className="field">
            <label className="field-label" htmlFor="identifier">
              Email atau username
            </label>
            <input
              id="identifier"
              className="input"
              autoComplete="username"
              required
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="password">
              Sandi
            </label>
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
            {busy ? "Memeriksa..." : "Masuk"}
          </button>
        </form>
      </main>
    </div>
  );
}
