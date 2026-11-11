import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface ToastItem {
  id: number;
  message: string;
  tone: "info" | "error";
}

interface ToastApi {
  show: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);
let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((message: string, tone: ToastItem["tone"]) => {
    const id = nextId++;
    setItems((current) => [...current.slice(-2), { id, message, tone }]);
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 4200);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({ show: (message) => push(message, "info"), error: (message) => push(message, "error") }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={item.tone === "error" ? "toast toast-error" : "toast"}>
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
