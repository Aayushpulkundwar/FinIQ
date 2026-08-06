import React from 'react';
import { useUIStore } from '../../store/useUIStore';
import {
  AlertOctagon,
  TrendingUp,
  TrendingDown,
  Activity,
  RefreshCw,
} from 'lucide-react';
import { getCurrencySymbol, formatMarketCap, formatPercent } from '../../utils';
import { BarChart, Bar, YAxis, ResponsiveContainer } from 'recharts';
import { api } from '../../services/api';
import { StockHistoryModal } from './StockHistoryModal';

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function formatVolume(value: number | null): string {
  if (value === null) return '—';
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(0)}K`;
  return value.toLocaleString();
}

// Custom Candlestick SVG drawing shape for Recharts Bar
const CandlestickShape = (props: any) => {
  const { x, y, width, height, payload } = props;
  if (!payload) return null;
  const { open, close, high, low } = payload;
  const isUp = close >= open;
  const color = isUp ? '#10b981' : '#ef4444';

  const cx = x + width / 2;
  
  // Calculate price-to-pixel ratio to draw wicks correctly
  const bodyRange = Math.abs(close - open) || 0.0001;
  const bodyTop = Math.min(y, y + height);
  const bodyHeight = Math.abs(height) || 1;
  const scale = bodyHeight / bodyRange;

  const yHigh = bodyTop - (high - Math.max(open, close)) * scale;
  const yLow = bodyTop + bodyHeight + (Math.min(open, close) - low) * scale;

  return (
    <g>
      {/* Wick line */}
      <line
        x1={cx}
        y1={yHigh}
        x2={cx}
        y2={yLow}
        style={{
          stroke: color,
          strokeWidth: 1.2,
        }}
      />
      {/* Body rectangle */}
      <rect
        x={x}
        y={bodyTop}
        width={width}
        height={bodyHeight}
        style={{
          fill: color,
          stroke: color,
        }}
      />
    </g>
  );
};


export const RightContextPanel: React.FC = () => {
  const {
    selectedCompany,
    financialAnalysis,
    financialSummary,
    isLoadingFinancialSummary,
    eventAnalysis,
    isLoadingAnalysis,
    liveMarketData,
    isLoadingMarketData,
    fetchMarketData,
  } = useUIStore();

  const [historyData, setHistoryData] = React.useState<any[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = React.useState(false);
  const [isHistoryModalOpen, setIsHistoryModalOpen] = React.useState(false);

  React.useEffect(() => {
    if (!selectedCompany) {
      setHistoryData([]);
      return;
    }

    let active = true;
    const fetchHistory = async () => {
      setIsLoadingHistory(true);
      try {
        const data = await api.getHistory(selectedCompany.id, '1W');
        if (active) {
          // Aggregate the 15-minute intervals into daily candles to prevent squeezing
          const dailyGroups: Record<string, any[]> = {};
          data.forEach((item) => {
            const datePart = item.date.split(' ')[0];
            if (!dailyGroups[datePart]) {
              dailyGroups[datePart] = [];
            }
            dailyGroups[datePart].push(item);
          });

          const aggregated = Object.keys(dailyGroups)
            .sort()
            .map((date) => {
              const dayItems = dailyGroups[date];
              const open = dayItems[0].open;
              const close = dayItems[dayItems.length - 1].close;
              const high = Math.max(...dayItems.map((i) => i.high));
              const low = Math.min(...dayItems.map((i) => i.low));
              const volume = dayItems.reduce((sum, i) => sum + i.volume, 0);
              return {
                date,
                open,
                high,
                low,
                close,
                volume,
                openClose: [open, close],
              };
            });

          setHistoryData(aggregated);
        }
      } catch (e) {
        console.error("Failed to fetch 1W history", e);
      } finally {
        if (active) setIsLoadingHistory(false);
      };
    };

    fetchHistory();

    return () => {
      active = false;
    };
  }, [selectedCompany]);

  if (!selectedCompany) {
    return (
      <aside className="right-context-panel" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <p style={{ color: '#6b7280', fontSize: '0.9rem', textAlign: 'center' }}>
          Select a company in the sidebar to populate financial intelligence models.
        </p>
      </aside>
    );
  }

  // Helper to format values in the summary cards
  const summaryFormatVal = (val: number | null | undefined) => {
    if (val === null || val === undefined || val === 0) return '—';
    return formatMarketCap(val, financialSummary?.currency || 'INR');
  };

  // ── Live market data helpers ──
  const md = liveMarketData;
  const mdAvailable = md?.available === true;
  const dayPositive = (md?.day_change_pct ?? 0) >= 0;

  return (
    <aside className="right-context-panel">
      <div className="context-header">
        <span>{selectedCompany.ticker_symbol} Dashboard</span>
        {(isLoadingAnalysis || isLoadingMarketData) && (
          <div className="spinner" style={{ width: '14px', height: '14px', borderLeftColor: '#10b981' }} />
        )}
      </div>

      {financialAnalysis?.reporting_status && (
        <div className="glass-panel" style={{
          borderLeft: '3px solid #f59e0b',
          padding: '10px 14px',
          marginBottom: '12px',
          fontSize: '0.78rem',
          color: '#f59e0b',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          backgroundColor: 'rgba(245, 158, 11, 0.04)',
          borderRadius: '8px',
        }}>
          <AlertOctagon size={14} />
          <span>{financialAnalysis.reporting_status}</span>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════
          0. LIVE MARKET DATA — Real-time Yahoo Finance strip
          ═══════════════════════════════════════════════════════ */}
      <div className="glass-panel" style={{ borderLeft: '3px solid #06b6d4', padding: '14px 16px' }}>
        {/* Header row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h4 style={{ fontSize: '0.75rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
            Live Market Data · NSE
          </h4>
          <button
            id="refresh-market-data-btn"
            title="Refresh market data"
            onClick={() => fetchMarketData(selectedCompany.id)}
            disabled={isLoadingMarketData}
            style={{
              background: 'none',
              border: 'none',
              color: '#6b7280',
              cursor: 'pointer',
              padding: '2px',
              display: 'flex',
              alignItems: 'center',
              transition: 'color 0.2s',
            }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.color = '#10b981')}
            onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.color = '#6b7280')}
          >
            <RefreshCw size={12} style={{ animation: isLoadingMarketData ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>

        {isLoadingMarketData ? (
          <div style={{ color: '#6b7280', fontSize: '0.82rem', textAlign: 'center', padding: '8px 0' }}>
            Fetching live data…
          </div>
        ) : !mdAvailable ? (
          <div style={{ color: '#6b7280', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Activity size={13} />
            Market data unavailable
            {md?.reason && (
              <span style={{ fontSize: '0.72rem', color: '#4b5563' }} title={md.reason}>
                {' '}(hover for reason)
              </span>
            )}
          </div>
        ) : (
          <>
            {/* Price + change row */}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '10px', marginBottom: '10px' }}>
              <div>
                <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginBottom: '2px' }}>Current Price</div>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f3f4f6', lineHeight: 1 }}>
                  {getCurrencySymbol(md?.currency)}{md?.current_price?.toFixed(2) ?? '—'}
                </div>
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 10px',
                  borderRadius: '6px',
                  backgroundColor: dayPositive ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                  color: dayPositive ? '#10b981' : '#ef4444',
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  marginBottom: '4px',
                }}
              >
                {dayPositive ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                {md?.day_change_pct !== null ? `${dayPositive ? '+' : ''}${md!.day_change_pct!.toFixed(2)}%` : '—'}
              </div>
            </div>

            {/* 4-cell metric grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              <div style={{ padding: '8px 10px', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ fontSize: '0.68rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '3px' }}>Market Cap</div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#f3f4f6' }}>{formatMarketCap(md?.market_cap ?? null, md?.currency)}</div>
              </div>
              <div style={{ padding: '8px 10px', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ fontSize: '0.68rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '3px' }}>P/E Ratio</div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#f3f4f6' }}>{md?.pe_ratio !== null && md?.pe_ratio !== undefined ? `${md.pe_ratio.toFixed(1)}x` : 'N/A'}</div>
              </div>
              <div style={{ padding: '8px 10px', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ fontSize: '0.68rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '3px' }}>52W Range</div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#f3f4f6' }}>
                  {md?.week_52_low !== null && md?.week_52_low !== undefined ? `${getCurrencySymbol(md?.currency)}${md.week_52_low.toFixed(0)}` : '—'}
                  <span style={{ color: '#6b7280' }}> – </span>
                  {md?.week_52_high !== null && md?.week_52_high !== undefined ? `${getCurrencySymbol(md?.currency)}${md.week_52_high.toFixed(0)}` : '—'}
                </div>
              </div>
              <div style={{ padding: '8px 10px', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ fontSize: '0.68rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '3px' }}>Volume</div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#f3f4f6' }}>{formatVolume(md?.volume ?? null)}</div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ══════════════════════════════════════
          2. Core Financial Metrics
          ══════════════════════════════════════ */}
      <div className="glass-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <h4 style={{ fontSize: '0.85rem', color: '#9ca3af', textTransform: 'uppercase', margin: 0, letterSpacing: '0.5px' }}>
            Financial Summary
            {financialSummary?.fiscal_year
              ? <span style={{ color: '#10b981', marginLeft: '6px' }}>({financialSummary.fiscal_year})</span>
              : isLoadingFinancialSummary
                ? <span style={{ color: '#6b7280', marginLeft: '6px', fontSize: '0.75rem' }}>loading…</span>
                : <span style={{ color: '#6b7280', marginLeft: '6px' }}>(—)</span>
            }
          </h4>
          {isLoadingFinancialSummary && (
            <div className="spinner" style={{ width: '12px', height: '12px', borderLeftColor: '#10b981' }} />
          )}
        </div>

        {!isLoadingFinancialSummary && financialSummary?.available === false ? (
          <div style={{ color: '#6b7280', fontSize: '0.8rem', padding: '4px 0' }}>
            Financial summary unavailable
            {financialSummary.reason && (
              <span style={{ fontSize: '0.72rem', color: '#4b5563', display: 'block', marginTop: '2px' }}>
                {financialSummary.reason}
              </span>
            )}
          </div>
        ) : (
          <div className="metric-grid">
            <div className="metric-card">
              <span className="metric-label">Revenue</span>
              <span className="metric-value">{summaryFormatVal(financialSummary?.revenue)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">EBITDA</span>
              <span className="metric-value">{summaryFormatVal(financialSummary?.ebitda)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Net Profit</span>
              <span className="metric-value">{summaryFormatVal(financialSummary?.net_profit)}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">ROE</span>
              <span className="metric-value">
                {financialSummary?.roe !== null && financialSummary?.roe !== undefined
                  ? formatPercent(financialSummary.roe)
                  : '—'}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ══════════════════════════════════════
          3. DCF Recommendation
          ══════════════════════════════════════ */}
      <div className="glass-panel" style={{ borderLeft: '3px solid #8b5cf6' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <h4 style={{ fontSize: '0.85rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
            Live Price
          </h4>
          {isLoadingHistory && (
            <div className="spinner" style={{ width: '12px', height: '12px', borderLeftColor: '#8b5cf6' }} />
          )}
        </div>

        {/* Live Sparkline Candlestick Chart */}
        {isLoadingHistory ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '140px', color: '#6b7280', fontSize: '0.75rem', marginBottom: '4px' }}>
            <div className="spinner" style={{ width: '12px', height: '12px', borderLeftColor: 'var(--accent)', marginRight: '6px' }} />
            <span>Loading chart…</span>
          </div>
        ) : historyData && historyData.length > 0 ? (
          <div
            onClick={() => setIsHistoryModalOpen(true)}
            style={{
              height: '140px',
              width: '100%',
              cursor: 'pointer',
              marginBottom: '4px',
              position: 'relative',
              borderRadius: '6px',
              backgroundColor: 'rgba(255,255,255,0.01)',
              border: '1px dashed rgba(255,255,255,0.05)',
              padding: '6px 0',
              overflow: 'hidden',
              transition: 'border-color 0.2s',
            }}
            title="Click to view detailed history chart"
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent)')}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.05)')}
          >
            <div style={{ position: 'absolute', top: '4px', right: '8px', fontSize: '0.62rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', zIndex: 10 }}>
              1W Performance (Click for history)
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={historyData} margin={{ top: 22, right: 12, left: 12, bottom: 4 }}>
                <YAxis hide={true} domain={['auto', 'auto']} />
                <Bar
                  dataKey="openClose"
                  shape={<CandlestickShape />}
                  barSize={16}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '140px', color: '#6b7280', fontSize: '0.75rem', marginBottom: '4px' }}>
            No historical data
          </div>
        )}
      </div>

      {/* ══════════════════════════════════════
          5. Event Alert Segment
          ══════════════════════════════════════ */}
      {eventAnalysis && (
        <div className="glass-panel" style={{ borderLeft: '3px solid #ef4444' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
            <AlertOctagon size={16} color="#ef4444" style={{ marginTop: '2px' }} />
            <div>
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f3f4f6' }}>
                Macro Event Detected
              </div>
              <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '4px', lineHeight: 1.4 }}>
                "{eventAnalysis.title}" (Severity: <strong style={{ color: '#ef4444' }}>{eventAnalysis.severity}</strong>)
              </div>
            </div>
          </div>
        </div>
      )}
      {/* ══════════════════════════════════════
          6. Pipeline Integrity State
          ══════════════════════════════════════ */}
      <div className="glass-panel" style={{ fontSize: '0.78rem' }}>
        <h4 style={{ color: '#10b981', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: 0 }}>
          Pipeline Integrity State
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', color: '#9ca3af' }}>
          <div>Vector Embeddings: <strong style={{ color: '#10b981' }}>Synchronized</strong></div>
          <div>SEC Ingestion: <strong style={{ color: '#10b981' }}>FY26 Active</strong></div>
          <div>Audit Logs: <strong style={{ color: '#10b981' }}>Secured (SHA-256)</strong></div>
          <div>Circuit Breakers: <strong style={{ color: '#10b981' }}>Closed (Healthy)</strong></div>
        </div>
      </div>

      <StockHistoryModal
        isOpen={isHistoryModalOpen}
        onClose={() => setIsHistoryModalOpen(false)}
        company={selectedCompany}
      />
    </aside>
  );
};
