import { X } from "lucide-react"
import { createContext, useCallback, useContext, useState, type ReactNode } from "react"
import { createPortal } from "react-dom"

import { cn } from "@/lib/utils"

export type ToastVariant = "default" | "success" | "error"

export interface Toast {
  id: string
  title?: string
  description: string
  variant?: ToastVariant
}

interface ToastContextValue {
  toast: (toast: Omit<Toast, "id">) => void
  dismiss: (id: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((prev) => [...prev, { id, ...t }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id))
    }, 5000)
  }, [])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toast, dismiss }}>
      {children}
      {createPortal(
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
          {toasts.map((t) => (
            <div
              key={t.id}
              className={cn(
                "flex w-80 items-start gap-3 rounded-md border p-4 shadow-lg",
                t.variant === "error" && "border-destructive/50 bg-destructive/10 text-destructive-foreground",
                t.variant === "success" && "border-emerald-500/50 bg-emerald-500/10 text-emerald-50",
                (!t.variant || t.variant === "default") && "border-border bg-card text-card-foreground"
              )}
            >
              <div className="flex-1">
                {t.title && <p className="text-sm font-medium">{t.title}</p>}
                <p className="text-sm text-muted-foreground">{t.description}</p>
              </div>
              <button
                onClick={() => dismiss(t.id)}
                className="rounded-sm opacity-70 hover:opacity-100"
                aria-label="Dismiss"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error("useToast must be used within ToastProvider")
  return ctx
}
