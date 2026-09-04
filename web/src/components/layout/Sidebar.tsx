import { Activity, BarChart3, FileText, LayoutDashboard, Settings, ShieldCheck } from "lucide-react"
import { NavLink } from "react-router-dom"

const links = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/discrepancies", label: "Discrepancies", icon: BarChart3 },
  { to: "/agents", label: "Agents", icon: Activity },
  { to: "/report", label: "Report", icon: FileText },
  { to: "/integrity", label: "Integrity", icon: ShieldCheck },
  { to: "/settings", label: "Settings", icon: Settings },
]

export function Sidebar() {
  return (
    <aside className="hidden w-56 flex-col border-r bg-card md:flex">
      <nav className="flex flex-col gap-1 p-3">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`
            }
          >
            <link.icon className="h-4 w-4" />
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
