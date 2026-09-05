import { NavLink } from "react-router-dom"

import { NAV_GROUPS } from "@/lib/nav"

export function Sidebar() {
  return (
    <aside className="hidden w-56 flex-col border-r bg-card md:flex">
      <nav className="flex flex-col gap-4 p-3">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <p className="mb-1 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {group.label}
            </p>
            <div className="flex flex-col gap-1">
              {group.items.map((link) => (
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
            </div>
          </div>
        ))}
      </nav>
    </aside>
  )
}
