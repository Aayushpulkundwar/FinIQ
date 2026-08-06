import React from 'react';
import { useUIStore } from '../../store/useUIStore';
import {
  Newspaper,
  ExternalLink,
  RotateCw,
  Clock,
  AlertTriangle,
} from 'lucide-react';

export const CompanyNewsTab: React.FC = () => {
  const {
    companyNews,
    isLoadingNews,
    newsError,
    fetchCompanyNews,
    selectedCompany,
  } = useUIStore();

  if (isLoadingNews) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '10px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#9ca3af', fontSize: '0.88rem' }}>
          <div className="spinner" style={{ width: '14px', height: '14px', borderLeftColor: '#10b981' }} />
          <span>Fetching live APITube company news feed...</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '16px' }}>
          <div className="glass-panel" style={{ height: '220px', borderRadius: '8px', animation: 'pulse 1.5s infinite' }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div className="glass-panel" style={{ height: '100px', borderRadius: '8px', animation: 'pulse 1.5s infinite' }} />
            <div className="glass-panel" style={{ height: '100px', borderRadius: '8px', animation: 'pulse 1.5s infinite' }} />
          </div>
        </div>
      </div>
    );
  }

  if (newsError) {
    return (
      <div className="glass-panel" style={{
        borderLeft: '4px solid #ef4444',
        padding: '18px 22px',
        color: '#ef4444',
        backgroundColor: 'rgba(239, 68, 68, 0.04)',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        marginTop: '10px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <AlertTriangle size={22} />
          <div>
            <h4 style={{ margin: 0, fontWeight: 700, fontSize: '0.95rem' }}>Failed to load APITube news feed</h4>
            <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#fca5a5' }}>
              Reason: {newsError}
            </p>
          </div>
        </div>
        <button
          onClick={() => selectedCompany && fetchCompanyNews(selectedCompany.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '7px 16px',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            color: '#f87171',
            borderRadius: '6px',
            fontSize: '0.82rem',
            fontWeight: 600,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
            transition: 'all 0.15s ease',
          }}
        >
          <RotateCw size={14} /> Retry
        </button>
      </div>
    );
  }

  if (!companyNews || !companyNews.articles || companyNews.articles.length === 0) {
    return (
      <div className="glass-panel" style={{ padding: '36px 20px', textAlign: 'center', color: '#6b7280', borderRadius: '8px', marginTop: '10px' }}>
        <Newspaper size={36} color="#4b5563" style={{ marginBottom: '10px', opacity: 0.6 }} />
        <h4 style={{ color: '#f3f4f6', fontSize: '1rem', marginBottom: '4px', margin: 0 }}>No recent news found</h4>
        <span style={{ fontSize: '0.82rem', color: '#9ca3af', marginTop: '6px', display: 'block' }}>
          APITube news search returned 0 results for {selectedCompany?.company_name || 'this company'}.
        </span>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Tab Header Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Newspaper size={20} color="#10b981" />
          <h3 style={{ fontSize: '1rem', color: '#10b981', textTransform: 'uppercase', fontWeight: 700, margin: 0, letterSpacing: '0.5px' }}>
            {selectedCompany?.company_name} ({selectedCompany?.ticker_symbol}) — Live Market News
          </h3>
        </div>
        <span style={{ fontSize: '0.78rem', backgroundColor: 'rgba(16,185,129,0.12)', color: '#10b981', border: '1px solid rgba(16,185,129,0.3)', padding: '3px 10px', borderRadius: '12px', fontWeight: 700 }}>
          {companyNews.articles.length} Articles Sourced via APITube
        </span>
      </div>

      {/* Bloomberg-Style News Grid */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
        
        {/* Upper Grid: Featured Hero Story + Secondary Headlines */}
        <div style={{ display: 'grid', gridTemplateColumns: companyNews.articles.length > 1 ? '1.35fr 1fr' : '1fr', gap: '18px' }}>
          
          {/* HERO FEATURED STORY (First Article) */}
          {companyNews.articles[0] && (
            <div className="glass-panel" style={{
              padding: '20px',
              borderRadius: '8px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid rgba(16,185,129,0.25)',
              backgroundColor: 'rgba(11, 15, 25, 0.75)',
            }}>
              <div>
                {/* Hero Cover Image or Gradient */}
                {companyNews.articles[0].image_url ? (
                  <div style={{ width: '100%', height: '160px', borderRadius: '6px', overflow: 'hidden', marginBottom: '14px' }}>
                    <img
                      src={companyNews.articles[0].image_url}
                      alt={companyNews.articles[0].title}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={(e) => { (e.currentTarget as HTMLElement).style.display = 'none'; }}
                    />
                  </div>
                ) : (
                  <div style={{
                    width: '100%',
                    height: '90px',
                    borderRadius: '6px',
                    background: 'linear-gradient(135deg, rgba(16,185,129,0.18) 0%, rgba(6,182,212,0.12) 100%)',
                    border: '1px solid rgba(16,185,129,0.2)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '14px',
                  }}>
                    <span style={{ fontSize: '0.95rem', fontWeight: 800, color: '#10b981', letterSpacing: '1px' }}>
                      {selectedCompany?.ticker_symbol} FEATURED NEWS
                    </span>
                  </div>
                )}

                {/* Source & Timestamp */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.78rem', color: '#9ca3af' }}>
                  <span style={{ fontWeight: 700, color: '#10b981', textTransform: 'uppercase' }}>
                    {companyNews.articles[0].source}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={12} /> {formatRelativeTime(companyNews.articles[0].published_at)}
                  </span>
                </div>

                {/* Hero Headline */}
                <h4 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f3f4f6', lineHeight: 1.35, marginBottom: '10px' }}>
                  {companyNews.articles[0].title}
                </h4>

                {/* Hero Excerpt / Snippet */}
                {companyNews.articles[0].snippet && (
                  <p style={{ fontSize: '0.85rem', color: '#9ca3af', lineHeight: 1.55, margin: 0, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {companyNews.articles[0].snippet}
                  </p>
                )}
              </div>

              {/* Read Full Article Button */}
              <div style={{ marginTop: '14px', paddingTop: '10px', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'flex-end' }}>
                <a
                  href={companyNews.articles[0].url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    fontSize: '0.82rem',
                    fontWeight: 700,
                    color: '#10b981',
                    textDecoration: 'none',
                  }}
                >
                  Read Full Article <ExternalLink size={13} />
                </a>
              </div>
            </div>
          )}

          {/* SECONDARY HEADLINES (Articles 2 to 4) */}
          {companyNews.articles.length > 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {companyNews.articles.slice(1, 4).map((art) => (
                <div
                  key={art.id}
                  className="glass-panel"
                  style={{
                    padding: '14px 16px',
                    borderRadius: '8px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    border: '1px solid rgba(255,255,255,0.06)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.74rem', color: '#6b7280' }}>
                    <span style={{ fontWeight: 600, color: '#06b6d4' }}>{art.source}</span>
                    <span>{formatRelativeTime(art.published_at)}</span>
                  </div>
                  <a
                    href={art.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      fontSize: '0.88rem',
                      fontWeight: 600,
                      color: '#e5e7eb',
                      textDecoration: 'none',
                      lineHeight: 1.35,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = '#10b981'; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = '#e5e7eb'; }}
                  >
                    {art.title}
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* LATEST NEWS STREAM (Articles 4 onwards) */}
        {companyNews.articles.length > 4 && (
          <div className="glass-panel" style={{ padding: '16px 18px', borderRadius: '8px' }}>
            <h4 style={{ fontSize: '0.82rem', color: '#9ca3af', textTransform: 'uppercase', fontWeight: 700, margin: '0 0 12px', letterSpacing: '0.5px' }}>
              Latest News Stream ({companyNews.articles.length - 4} More)
            </h4>
            <div style={{ maxHeight: '320px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px', paddingRight: '4px' }}>
              {companyNews.articles.slice(4).map((art) => (
                <div
                  key={art.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '14px',
                    padding: '9px 12px',
                    backgroundColor: 'rgba(255,255,255,0.015)',
                    border: '1px solid rgba(255,255,255,0.03)',
                    borderRadius: '6px',
                    fontSize: '0.82rem',
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', overflow: 'hidden' }}>
                    <a
                      href={art.url}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        fontWeight: 500,
                        color: '#d1d5db',
                        textDecoration: 'none',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = '#10b981'; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = '#d1d5db'; }}
                    >
                      {art.title}
                    </a>
                    <div style={{ display: 'flex', gap: '10px', fontSize: '0.72rem', color: '#6b7280' }}>
                      <span style={{ color: '#06b6d4' }}>{art.source}</span>
                      <span>•</span>
                      <span>{formatRelativeTime(art.published_at)}</span>
                    </div>
                  </div>
                  <a
                    href={art.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#9ca3af', flexShrink: 0 }}
                    title="Open article"
                  >
                    <ExternalLink size={14} />
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

    </div>
  );
};

/* Helper Functions */

function formatRelativeTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 60) return `${Math.max(1, diffMins)}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return 'Recently';
  }
}
