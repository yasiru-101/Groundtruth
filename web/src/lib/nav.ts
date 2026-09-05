import {
  Activity,
  AlertTriangle,
  FileText,
  GitCompare,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react"

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  title: string
  description: string
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Monitor",
    items: [
      {
        to: "/",
        label: "Overview",
        icon: LayoutDashboard,
        title: "Overview",
        description: "How truthful the board is right now and what needs attention.",
      },
      {
        to: "/discrepancies",
        label: "Discrepancies",
        icon: AlertTriangle,
        title: "Discrepancies",
        description: "Gaps Groundtruth found between Jira and Git, each backed by evidence.",
      },
      {
        to: "/report",
        label: "Report",
        icon: FileText,
        title: "Report",
        description: "Standup summary and sprint plan drawn from the latest run.",
      },
    ],
  },
  {
    label: "Evidence",
    items: [
      {
        to: "/agents",
        label: "Agents",
        icon: Activity,
        title: "Agents",
        description: "What each autonomous agent did and the ledger it wrote.",
      },
      {
        to: "/integrity",
        label: "Integrity",
        icon: ShieldCheck,
        title: "Integrity",
        description: "Verify that the hash-chained ledger was not tampered with.",
      },
      {
        to: "/runs",
        label: "Runs",
        icon: GitCompare,
        title: "Runs",
        description: "Browse past runs and compare truthfulness scores over time.",
      },
    ],
  },
  {
    label: "Configure",
    items: [
      {
        to: "/settings",
        label: "Settings",
        icon: Settings,
        title: "Settings",
        description: "Connect GitHub, Jira, and the LLM provider.",
      },
    ],
  },
]

export const NAV_FLAT: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)

export function navItemByPath(path: string): NavItem | undefined {
  return NAV_FLAT.find((item) => item.to === path)
}
