import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { Icon } from "./Icon";

type ToastType = "success" | "error" | "info" | "warning";
interface ToastItem {
  id: number;
  type: ToastType;
  title: string;
  message?: string;
}

interface ToastContextValue {
  toast: (type: ToastType, title: string, message?: string) => void;
  success: (title: string, message?: string) => void;
  error: (title: string, message?: string) => void;
  info: (title: string, message?: string) => void;
  warning: (title: string, message?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);
let counter = 0;

const ICONS: Record<ToastType, "check-circle" | "x-circle" | "info" | "alert"> = {
  success: "check-circle",
  error: "x-circle",
  info: "info",
  warning: "alert",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (type: ToastType, title: string, message?: string) => {
      const id = ++counter;
      setItems((prev) => [...prev.slice(-3), { id, type, title, message }]);
      setTimeout(() => remove(id), type === "error" ? 7000 : 4500);
    },
    [remove],
  );

  const value: ToastContextValue = {
    toast,
    success: (t, m) => toast("success", t, m),
    error: (t, m) => toast("error", t, m),
    info: (t, m) => toast("info", t, m),
    warning: (t, m) => toast("warning", t, m),
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.type}`} role="status">
            <span className="toast-icon">
              <Icon name={ICONS[t.type]} size={19} />
            </span>
            <div className="toast-body">
              <strong>{t.title}</strong>
              {t.message && <span>{t.message}</span>}
            </div>
            <button className="toast-close" onClick={() => remove(t.id)} aria-label="Dismiss">
              <Icon name="x" size={15} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}