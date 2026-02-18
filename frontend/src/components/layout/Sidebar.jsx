import { motion } from "framer-motion";
import { LayoutDashboard, MessageSquare, FileText, Sparkles, Network, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, shortcut: '⌘0' },
  { id: 'chat', label: 'Chat', icon: MessageSquare, shortcut: '⌘1' },
  { id: 'docs', label: 'Documents', icon: FileText, shortcut: '⌘2' },
  { id: 'summary', label: 'Summary', icon: Sparkles, shortcut: '⌘3' },
  { id: 'graph', label: 'Graph', icon: Network, shortcut: '⌘4' },
];

export function Sidebar({ activeView, onViewChange }) {
  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="w-64 h-screen bg-card border-r border-border flex flex-col"
    >
      {/* Logo/Brand */}
      <div className="p-6 border-b border-border">
        <motion.div
          initial={{ scale: 0.9 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 200 }}
          className="flex items-center gap-3"
        >
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-foreground">DocuMind</h1>
            <p className="text-xs text-muted-foreground">Knowledge Base AI</p>
          </div>
        </motion.div>
      </div>

      {/* Navigation Items */}
      <nav className="flex-1 p-4 space-y-2">
        {navItems.map((item, index) => {
          const isActive = activeView === item.id;
          const Icon = item.icon;

          return (
            <motion.button
              key={item.id}
              initial={{ x: -20, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              transition={{ delay: index * 0.05 }}
              onClick={() => onViewChange(item.id)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-smooth relative group",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              )}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {/* Active indicator */}
              {isActive && (
                <motion.div
                  layoutId="activeTab"
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-primary rounded-r-full"
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}

              <Icon className={cn("w-5 h-5", isActive && "text-primary")} />

              <span className="flex-1 text-left font-medium">
                {item.label}
              </span>

              {/* Keyboard shortcut hint */}
              <span className="text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-smooth">
                {item.shortcut}
              </span>
            </motion.button>
          );
        })}
      </nav>

      {/* Settings (Future) */}
      <div className="p-4 border-t border-border">
        <button
          className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-smooth"
        >
          <Settings className="w-5 h-5" />
          <span className="font-medium">Settings</span>
        </button>
      </div>
    </motion.aside>
  );
}
