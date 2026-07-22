import React, { useEffect, useState, useRef } from 'react';
import { useUIStore } from '../../store/useUIStore';
import {
  MessageSquare,
  TrendingUp,
  DollarSign,
  Award,
  Search,
  History,
} from 'lucide-react';

export const LeftSidebar: React.FC = () => {
  const {
    selectedCompany,
    recentCompanies,
    searchResults,
    isLoadingRecent,
    isLoadingSearch,
    fetchCompanies,
    fetchRecentCompanies,
    searchCompanies,
    selectCompany,
    activeTab,
    setActiveTab,
  } = useUIStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchCompanies();
    fetchRecentCompanies();
  }, [fetchCompanies, fetchRecentCompanies]);

  // Debounced search logic (300ms)
  useEffect(() => {
    const delayDebounce = setTimeout(() => {
      if (searchTerm.trim() !== '') {
        searchCompanies(searchTerm);
      }
    }, 300);

    return () => clearTimeout(delayDebounce);
  }, [searchTerm, searchCompanies]);

  // Click outside to close dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsOpen(false);
    }
  };

  const handleSelect = (company: any) => {
    selectCompany(company);
    setSearchTerm('');
    setIsOpen(false);
  };

  // Determine what list to show in dropdown
  const showRecent = searchTerm.trim() === '';
  const displayList = showRecent ? recentCompanies : searchResults;

  return (
    <aside className="left-sidebar">
      {/* 1. Company Selection */}
      <div className="sidebar-section">
        <h3 className="sidebar-title">Select Portfolio Company</h3>
        
        <div ref={containerRef} className="select-wrapper" style={{ position: 'relative' }}>
          {/* Search Input Box */}
          <div style={{ position: 'relative', width: '100%' }}>
            <input
              type="text"
              className="custom-select"
              style={{
                paddingLeft: '38px',
                paddingRight: '12px',
                width: '100%',
                cursor: 'text',
              }}
              placeholder={selectedCompany ? `${selectedCompany.ticker_symbol} - ${selectedCompany.company_name}` : "Search company..."}
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setIsOpen(true);
              }}
              onFocus={() => {
                fetchRecentCompanies();
                setIsOpen(true);
              }}
              onKeyDown={handleKeyDown}
            />
            <Search
              size={15}
              style={{
                position: 'absolute',
                left: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted)',
                pointerEvents: 'none',
              }}
            />
          </div>

          {/* Results/Recent Dropdown Overlay */}
          {isOpen && (
            <div
              style={{
                position: 'absolute',
                top: 'calc(100% + 6px)',
                left: 0,
                width: '100%',
                backgroundColor: 'rgba(11, 15, 25, 0.98)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                boxShadow: 'var(--shadow-lg)',
                zIndex: 100,
                maxHeight: '260px',
                overflowY: 'auto',
                backdropFilter: 'blur(10px)',
              }}
            >
              {showRecent && (
                <div
                  style={{
                    padding: '8px 12px 4px',
                    fontSize: '0.68rem',
                    color: 'var(--text-muted)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    borderBottom: '1px solid rgba(255,255,255,0.03)',
                  }}
                >
                  <History size={10} />
                  <span>RECENTLY SELECTED</span>
                </div>
              )}

              {(isLoadingRecent || isLoadingSearch) ? (
                <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '0.82rem', textAlign: 'center', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}>
                  <div className="spinner" style={{ width: '12px', height: '12px', borderLeftColor: 'var(--accent)' }} />
                  <span>Loading...</span>
                </div>
              ) : displayList.length === 0 ? (
                <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '0.82rem', textAlign: 'center' }}>
                  {showRecent ? 'No recent selections' : 'No matching companies found'}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {displayList.map((company) => (
                    <button
                      key={company.id}
                      onClick={() => handleSelect(company)}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        width: '100%',
                        padding: '10px 12px',
                        background: 'none',
                        border: 'none',
                        borderBottom: '1px solid rgba(255,255,255,0.02)',
                        textAlign: 'left',
                        cursor: 'pointer',
                        transition: 'background-color 0.15s ease',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = 'rgba(16, 185, 129, 0.08)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'transparent';
                      }}
                    >
                      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--accent)' }}>
                        {company.ticker_symbol}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', width: '100%' }}>
                        {company.company_name}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {selectedCompany && (
          <div style={{
            fontSize: '0.78rem',
            color: '#9ca3af',
            padding: '10px 12px',
            backgroundColor: 'rgba(255,255,255,0.02)',
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.05)',
            marginTop: '10px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px'
          }}>
            <div>Exchange: <strong style={{ color: '#e5e7eb' }}>{selectedCompany.exchange}</strong></div>
            <div>Industry: <strong style={{ color: '#e5e7eb' }}>{selectedCompany.industry}</strong></div>
            <div>ISIN: <strong style={{ color: '#e5e7eb' }}>{selectedCompany.isin}</strong></div>
            <div>Sector: <strong style={{ color: '#e5e7eb' }}>{selectedCompany.sector}</strong></div>
            {selectedCompany.website && (
              <div>
                Website:{' '}
                <a
                  href={selectedCompany.website}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: '#10b981', textDecoration: 'none', fontWeight: 600 }}
                >
                  {selectedCompany.website}
                </a>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 2. Intelligence Core Navigation */}
      <div className="sidebar-section">
        <h3 className="sidebar-title">Intelligence Core</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
          {[
            { id: 'chat', label: 'Research Terminal', icon: <MessageSquare size={15} /> },
            { id: 'financials', label: 'Financials', icon: <TrendingUp size={15} /> },
            { id: 'valuation', label: 'Valuation (DCF)', icon: <DollarSign size={15} /> },
            { id: 'market', label: 'Market Intel', icon: <Award size={15} /> },
          ].map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                id={`nav-btn-${item.id}`}
                onClick={() => setActiveTab(isActive && item.id !== 'chat' ? 'chat' : (item.id as any))}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '10px 14px',
                  backgroundColor: isActive ? 'rgba(16, 185, 129, 0.18)' : 'rgba(255, 255, 255, 0.025)',
                  border: isActive ? '1px solid #10b981' : '1px solid rgba(255, 255, 255, 0.06)',
                  borderRadius: '8px',
                  color: isActive ? '#10b981' : '#d1d5db',
                  fontSize: '0.85rem',
                  fontWeight: isActive ? 700 : 500,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: isActive ? '0 0 12px rgba(16, 185, 129, 0.15)' : 'none',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.backgroundColor = 'rgba(16, 185, 129, 0.08)';
                    e.currentTarget.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.025)';
                    e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.06)';
                  }
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
};

