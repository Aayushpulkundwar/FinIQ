import React, { useState, useEffect, useRef } from 'react';
import { useDebugStore } from '../../store/useDebugStore';
import { Terminal, ShieldAlert, Wifi, Info, ChevronUp, ChevronDown, Trash2, Search } from 'lucide-react';

export const DebugConsole: React.FC = () => {
  const { logs, isOpen, toggleOpen, clearLogs } = useDebugStore();
  const [filterLevels, setFilterLevels] = useState<Record<string, boolean>>({
    info: true,
    warn: true,
    error: true,
    network: true,
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedLogIds, setExpandedLogIds] = useState<Record<string, boolean>>({});
  
  const consoleBodyRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  // Check if scroll is at bottom
  const checkScroll = () => {
    if (!consoleBodyRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = consoleBodyRef.current;
    // Allow small margin (10px) for high DPI/zoom levels
    isAtBottomRef.current = scrollHeight - scrollTop - clientHeight <= 15;
  };

  // Auto-scroll to bottom on new log if already at bottom
  useEffect(() => {
    if (isOpen && consoleBodyRef.current && isAtBottomRef.current) {
      consoleBodyRef.current.scrollTop = consoleBodyRef.current.scrollHeight;
    }
  }, [logs, isOpen]);

  const handleScroll = () => {
    checkScroll();
  };

  const toggleLevelFilter = (level: string) => {
    setFilterLevels(prev => ({ ...prev, [level]: !prev[level] }));
  };

  const toggleLogExpand = (id: string) => {
    setExpandedLogIds(prev => ({ ...prev, [id]: !prev[id] }));
  };

  // Filter logs
  const filteredLogs = logs.filter(log => {
    if (!filterLevels[log.level]) return false;
    if (searchQuery.trim() === '') return true;
    const query = searchQuery.toLowerCase();
    return (
      log.message.toLowerCase().includes(query) ||
      log.source.toLowerCase().includes(query) ||
      (log.details && JSON.stringify(log.details).toLowerCase().includes(query))
    );
  });

  // Calculate badge counts
  const errorCount = logs.filter(l => l.level === 'error').length;
  const warnCount = logs.filter(l => l.level === 'warn').length;
  const networkCount = logs.filter(l => l.level === 'network').length;
  const infoCount = logs.filter(l => l.level === 'info').length;

  return (
    <div className={`debug-console-container ${isOpen ? 'expanded' : 'collapsed'}`}>
      {/* 1. Header Bar (always visible) */}
      <div className="debug-console-header" onClick={toggleOpen}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#10b981', fontWeight: 700, fontSize: '0.82rem', letterSpacing: '0.5px' }}>
            <Terminal size={14} />
            <span>DEBUG CONSOLE</span>
          </div>
          
          {/* Badge counts */}
          <div style={{ display: 'flex', gap: '10px', fontSize: '0.72rem' }}>
            <span style={{ color: '#ef4444', display: 'flex', alignItems: 'center', gap: '3px', fontWeight: 600 }}>
              <ShieldAlert size={12} /> {errorCount} errors
            </span>
            <span style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '3px', fontWeight: 600 }}>
              <ShieldAlert size={12} /> {warnCount} warnings
            </span>
            <span style={{ color: '#0d9488', display: 'flex', alignItems: 'center', gap: '3px', fontWeight: 600 }}>
              <Wifi size={12} /> {networkCount} network
            </span>
            <span style={{ color: '#9ca3af', display: 'flex', alignItems: 'center', gap: '3px', fontWeight: 600 }}>
              <Info size={12} /> {infoCount} info
            </span>
          </div>
        </div>

        {/* Toggle Button */}
        <button className="debug-console-toggle-btn" aria-label="Toggle debug console">
          {isOpen ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      </div>

      {/* 2. Expanded Body */}
      {isOpen && (
        <div className="debug-console-body">
          {/* Controls Bar */}
          <div className="debug-console-controls">
            {/* Filter Toggle Buttons */}
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <button
                className={`filter-btn error ${filterLevels.error ? 'active' : ''}`}
                onClick={() => toggleLevelFilter('error')}
              >
                Error
              </button>
              <button
                className={`filter-btn warn ${filterLevels.warn ? 'active' : ''}`}
                onClick={() => toggleLevelFilter('warn')}
              >
                Warning
              </button>
              <button
                className={`filter-btn network ${filterLevels.network ? 'active' : ''}`}
                onClick={() => toggleLevelFilter('network')}
              >
                Network
              </button>
              <button
                className={`filter-btn info ${filterLevels.info ? 'active' : ''}`}
                onClick={() => toggleLevelFilter('info')}
              >
                Info
              </button>
            </div>

            {/* Search Box */}
            <div className="debug-search-wrapper">
              <Search size={13} className="search-icon" />
              <input
                type="text"
                placeholder="Search logs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="debug-search-input"
              />
            </div>

            {/* Clear Button */}
            <button className="debug-clear-btn" onClick={clearLogs}>
              <Trash2 size={13} />
              <span>Clear Logs</span>
            </button>
          </div>

          {/* Logs List Container */}
          <div
            className="debug-logs-list"
            ref={consoleBodyRef}
            onScroll={handleScroll}
          >
            {filteredLogs.length === 0 ? (
              <div style={{ padding: '24px', color: '#6b7280', textAlign: 'center', fontSize: '0.8rem' }}>
                No matching debug logs recorded.
              </div>
            ) : (
              filteredLogs.map((log) => {
                const badgeColor =
                  log.level === 'error' ? '#ef4444' :
                  log.level === 'warn' ? '#f59e0b' :
                  log.level === 'network' ? '#0d9488' : '#4b5563';

                return (
                  <div key={log.id} className="debug-log-row">
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', width: '100%', flexWrap: 'wrap' }}>
                      <span className="log-timestamp">
                        {log.timestamp.toLocaleTimeString()}
                      </span>
                      
                      <span
                        className="log-level-badge"
                        style={{ backgroundColor: badgeColor }}
                      >
                        {log.level.toUpperCase()}
                      </span>
                      
                      <span className="log-source">[{log.source}]</span>
                      
                      <span className="log-message">{log.message}</span>

                      {log.details && (
                        <button
                          className="log-details-toggle"
                          onClick={() => toggleLogExpand(log.id)}
                        >
                          {expandedLogIds[log.id] ? 'Hide details' : 'Show details'}
                        </button>
                      )}
                    </div>

                    {log.details && expandedLogIds[log.id] && (
                      <div className="log-details-json">
                        <pre>{typeof log.details === 'object' ? JSON.stringify(log.details, null, 2) : String(log.details)}</pre>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
