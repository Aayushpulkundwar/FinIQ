import React, { useEffect } from 'react';
import { useUIStore } from '../../store/useUIStore';
import { Cpu } from 'lucide-react';

export const TopNavbar: React.FC = () => {
  const { healthStatus, checkHealth } = useUIStore();

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  const isHealthy = healthStatus?.status === 'healthy';

  return (
    <nav className="top-navbar">
      <div className="logo-container">
        <Cpu className="logo-icon" size={24} color="#10b981" />
        <span className="logo-text">FinIQ</span>
        <span className="logo-badge" style={{
          fontSize: '0.75rem',
          padding: '2px 8px',
          borderRadius: '12px',
          backgroundColor: 'rgba(16, 185, 129, 0.15)',
          color: '#10b981',
          border: '1px solid rgba(16, 185, 129, 0.3)',
          fontWeight: 600
        }}>
          Workspace v1.2
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className={`status-indicator ${isHealthy ? '' : 'unhealthy'}`} />
          <span style={{ fontSize: '0.85rem', color: '#9ca3af', fontWeight: 500 }}>
            {isHealthy ? 'Connected' : 'Offline/Unhealthy'}
          </span>
        </div>

        {healthStatus && (
          <div style={{
            display: 'flex',
            gap: '8px',
            fontSize: '0.75rem',
            color: '#6b7280',
            backgroundColor: 'rgba(255, 255, 255, 0.02)',
            padding: '4px 10px',
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.05)'
          }}>
            <span>DB: {healthStatus.postgres}</span>
            <span>|</span>
            <span>Redis: {healthStatus.redis}</span>
          </div>
        )}
      </div>
    </nav>
  );
};
