import { Sidebar } from "./Sidebar";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";

export function AppLayout({ activeView, onViewChange, children }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      {/* Left Sidebar */}
      <Sidebar activeView={activeView} onViewChange={onViewChange} />
      
      {/* Main Content Area */}
      {/* FIX: Changed overflow-auto to overflow-hidden so the child (ChatPage) controls the scroll */}
      <main className="flex-1 overflow-hidden flex flex-col">
        <ErrorBoundary>
          {children}
        </ErrorBoundary>
      </main>
    </div>
  );
}