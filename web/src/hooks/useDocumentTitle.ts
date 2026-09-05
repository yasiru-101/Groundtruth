import { useEffect } from "react"
import { useLocation } from "react-router-dom"

import { navItemByPath } from "@/lib/nav"

export function useDocumentTitle(suffix?: string) {
  const { pathname } = useLocation()

  useEffect(() => {
    const item = navItemByPath(pathname)
    const title = item ? `${item.title} · Groundtruth` : "Groundtruth"
    document.title = suffix ? `${title} · ${suffix}` : title
  }, [pathname, suffix])
}
