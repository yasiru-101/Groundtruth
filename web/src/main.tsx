import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"

import App from "./App.tsx"
import { ErrorBoundary } from "@/components/common/ErrorBoundary"
import { JobProvider } from "@/components/jobs/JobProvider"
import { ToastProvider } from "@/components/ui/toast"
import { apiRetry } from "@/lib/query"
import "./index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: apiRetry,
    },
  },
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <JobProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </JobProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>
)
