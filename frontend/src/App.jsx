import { useState } from 'react';
import { AppLayout } from './components/layout/AppLayout';
import { WorkspaceProvider } from '@/contexts/WorkspaceContext';
import { WorkspacePage } from './pages/WorkspacePage';
import { GraphPage } from './pages/GraphPage';
import { DashboardPage } from './pages/DashboardPage';
import { EvaluationPage } from '@/pages/EvaluationPage';
import { useKeyboard } from './hooks/useKeyboard';

function App() {
  const [activeView, setActiveView] = useState('dashboard');

  useKeyboard([
    { key: '1', ctrlKey: true, callback: () => setActiveView('dashboard') },
    { key: '2', ctrlKey: true, callback: () => setActiveView('workspace') },
    { key: '3', ctrlKey: true, callback: () => setActiveView('graph') },
    { key: '4', ctrlKey: true, callback: () => setActiveView('evaluation') },
  ]);

  const renderPage = () => {
    switch (activeView) {
      case 'workspace':
        return <WorkspacePage />;
      case 'graph':
        return <GraphPage />;
      case 'evaluation':
        return <EvaluationPage />;
      case 'dashboard':
        return <DashboardPage onViewChange={setActiveView} />;
      default:
        return <WorkspacePage />;
    }
  };

  return (
    <WorkspaceProvider>
      <AppLayout activeView={activeView} onViewChange={setActiveView}>
        {renderPage()}
      </AppLayout>
    </WorkspaceProvider>
  );
}

export default App;