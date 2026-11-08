import type { ReactNode } from "react";

export function Loading({ label = "Memuat data..." }: { label?: string }) {
  return <p className="loading">{label}</p>;
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="notice" role="alert">
      {message}{" "}
      {onRetry ? (
        <button type="button" className="btn btn-link" onClick={onRetry}>
          Muat ulang
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
    </div>
  );
}

export function PageHead({ title, intro, actions }: { title: string; intro?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {intro ? <p className="page-intro">{intro}</p> : null}
      </div>
      {actions}
    </header>
  );
}
