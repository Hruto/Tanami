import { useEffect, useRef, type ReactNode } from "react";

import { IconClose } from "./Icons";

// Native <dialog> gives focus trapping, Escape-to-close and an inert page
// behind it for free, which a hand-rolled overlay would have to re-implement.
function useModal(open: boolean) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return ref;
}

interface ConfirmProps {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  tone?: "primary" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  tone = "primary",
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmProps) {
  const ref = useModal(open);
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby="confirm-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 id="confirm-title">{title}</h2>
      <p>{children}</p>
      <div className="dialog-actions">
        <button type="button" className="btn btn-quiet" onClick={onCancel} disabled={busy}>
          Batal
        </button>
        <button
          type="button"
          className={tone === "danger" ? "btn btn-danger-solid" : "btn btn-primary"}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? "Memproses..." : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

interface DrawerProps {
  open: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  onClose: () => void;
}

export function Drawer({ open, title, subtitle, footer, children, onClose }: DrawerProps) {
  const ref = useModal(open);
  return (
    <dialog
      ref={ref}
      className="drawer"
      aria-labelledby="drawer-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="drawer-head">
        <div>
          <h2 id="drawer-title">{title}</h2>
          {subtitle ? <div className="page-intro">{subtitle}</div> : null}
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Tutup">
          <IconClose />
        </button>
      </div>
      <div className="drawer-body">{children}</div>
      {footer ? <div className="drawer-foot">{footer}</div> : null}
    </dialog>
  );
}
