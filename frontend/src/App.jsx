import { useState } from 'react';
import { AppLayout } from './components/layout/AppLayout';
import { DocumentProvider } from '@/contexts/DocumentContext';
import { ChatProvider } from '@/contexts/ChatContext';
import { SummaryProvider } from '@/contexts/SummaryContext';
import { DocumentsPage } from './pages/DocumentsPage';
import { ChatPage } from './pages/ChatPage';
import { SummaryPage } from './pages/SummaryPage';
import { GraphPage } from './pages/GraphPage';
import { DashboardPage } from './pages/DashboardPage';
import { useKeyboard } from './hooks/useKeyboard';

// We moved the logic from 'AppContent' directly into 'App' for simplicity
function App() {
  const [activeView, setActiveView] = useState('dashboard');

  // Keyboard shortcuts to switch views
  useKeyboard([
    { key: '1', ctrlKey: true, callback: () => setActiveView('dashboard') },
    { key: '2', ctrlKey: true, callback: () => setActiveView('chat') },
    { key: '3', ctrlKey: true, callback: () => setActiveView('docs') },
    { key: '4', ctrlKey: true, callback: () => setActiveView('summary') },
    { key: '5', ctrlKey: true, callback: () => setActiveView('graph') },
  ]);

  const renderPage = () => {
    switch (activeView) {
      case 'chat':
        return <ChatPage />;
      case 'docs':
        return <DocumentsPage />;
      case 'summary':
        return <SummaryPage />;
      case 'graph':
        return <GraphPage />;
      case 'dashboard':
        return <DashboardPage onViewChange={setActiveView} />;
      default:
        return <ChatPage />;
    }
  };

  return (
    <DocumentProvider>
      <ChatProvider>
        <SummaryProvider>
          {/* We pass activeView and onViewChange so the Sidebar works */}
          <AppLayout activeView={activeView} onViewChange={setActiveView}>
            {renderPage()}
          </AppLayout>
        </SummaryProvider>
      </ChatProvider>
    </DocumentProvider>
  );
}

export default App;