import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopNavbar } from './components/Layout/TopNavbar';
import { LeftSidebar } from './components/Layout/LeftSidebar';
import { CenterWorkspace } from './components/Layout/CenterWorkspace';
import { RightContextPanel } from './components/Layout/RightContextPanel';
import { useUIStore } from './store/useUIStore';
import { useDebugStore } from './store/useDebugStore';
import { DebugConsole } from './components/Layout/DebugConsole';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
});

const FinsightAIWorkspaceContent: React.FC = () => {
  const { error } = useUIStore();
  const { isOpen: isDebugOpen } = useDebugStore();

  const isDev = import.meta.env.DEV;
  const debugClass = isDev ? (isDebugOpen ? 'debug-expanded' : 'debug-collapsed') : '';

  return (
    <div className={`app-container ${debugClass}`}>
      {/* 1. Top Navigation */}
      <TopNavbar />

      {/* 2. Main Sidebar & Workspaces */}
      <div className="workspace-container">
        {/* Left Drawer / Sidebar */}
        <LeftSidebar />

        {/* Central Chat Interface */}
        <CenterWorkspace />

        {/* Right Dashboard Context Panel */}
        <RightContextPanel />
      </div>



      {/* Global Toast Alert for error messages */}
      {error && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          backgroundColor: '#ef4444',
          color: '#ffffff',
          padding: '12px 20px',
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(239, 68, 68, 0.3)',
          zIndex: 1000,
          fontWeight: 500,
          display: 'flex',
          gap: '10px',
          alignItems: 'center'
        }}>
          <span>Error: {error}</span>
          <button
            onClick={() => useUIStore.setState({ error: null })}
            style={{
              background: 'none',
              border: 'none',
              color: '#ffffff',
              cursor: 'pointer',
              fontWeight: 'bold',
              fontSize: '1rem'
            }}
          >
            ×
          </button>
        </div>
      )}

      {/* Dev-only Collapsible Debug Console */}
      {import.meta.env.DEV && <DebugConsole />}
    </div>
  );
};

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <FinsightAIWorkspaceContent />
    </QueryClientProvider>
  );
}

export default App;
