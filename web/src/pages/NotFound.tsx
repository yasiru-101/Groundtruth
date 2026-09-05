import { Link } from "react-router-dom"
import { Home } from "lucide-react"

import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/layout/PageHeader"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"

export function NotFound() {
  useDocumentTitle("Not found")

  return (
    <div className="space-y-6">
      <PageHeader title="Page not found" description="The page you requested doesn't exist." />
      <Button asChild>
        <Link to="/">
          <Home className="mr-2 h-4 w-4" />
          Back to Overview
        </Link>
      </Button>
    </div>
  )
}
