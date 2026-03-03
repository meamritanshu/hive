import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquare,
  Brain,
  Blocks,
  Settings,
  Clock,
  Hexagon,
} from "lucide-react";
import { cn } from "../lib/utils";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/chat", label: "Chat", icon: MessageSquare },
  { to: "/memory", label: "Memory", icon: Brain },
  { to: "/skills", label: "Skills", icon: Blocks },
  { to: "/scheduler", label: "Scheduler", icon: Clock },
  { to: "/config", label: "Config", icon: Settings },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="flex w-56 flex-col border-r border-surface-800 bg-surface-900">
        {/* Logo */}
        <div className="flex items-center gap-2.5 border-b border-surface-800 px-4 py-4">
          <Hexagon className="h-7 w-7 text-hive-400" strokeWidth={2.5} />
          <div>
            <h1 className="text-sm font-bold text-surface-100">HiveCore</h1>
            <p className="text-[10px] text-surface-500">Console</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-0.5 px-2 py-3">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-hive-500/10 text-hive-400 font-medium"
                    : "text-surface-400 hover:bg-surface-800 hover:text-surface-200"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-surface-800 px-4 py-3">
          <p className="text-[10px] text-surface-600">
            HiveCore v0.1.0
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
