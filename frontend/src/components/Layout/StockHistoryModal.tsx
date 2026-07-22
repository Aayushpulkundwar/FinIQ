import React, { useState, useEffect } from 'react';
import { X, AlertOctagon } from 'lucide-react';
import {
  BarChart,
  ComposedChart,
  Bar,
  Line,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { api } from '../../services/api';
import { getCurrencySymbol } from '../../utils';
import type { Company, HistoricalPricePoint } from '../../types';

interface StockHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  company: Company;
}

// Helper to compute Simple Moving Average (SMA)
const computeSMA = (points: HistoricalPricePoint[], period: number): (number | null)[] => {
  const smas: (number | null)[] = [];
  for (let i = 0; i < points.length; i++) {
    if (i < period - 1) {
      smas.push(null);
    } else {
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += points[i - j].close;
      }
      smas.push(sum / period);
    }
  }
  return smas;
};

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
          strokeWidth: 1.5,
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

export const StockHistoryModal: React.FC<StockHistoryModalProps> = ({
  isOpen,
  onClose,
  company,
}) => {
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const currencySymbol = getCurrencySymbol(company.isin.startsWith('IN') ? 'INR' : 'USD');
      return (
        <div style={{
          backgroundColor: '#0b0f19',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '12px',
          boxShadow: 'var(--shadow-lg)',
          fontSize: '0.8rem',
          color: '#e5e7eb',
        }}>
          <div style={{ color: 'var(--accent)', fontWeight: 700, marginBottom: '6px' }}>Date: {label}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '20px' }}>
              <span style={{ color: '#9ca3af' }}>Open:</span>
              <span style={{ color: '#fff', fontWeight: 600 }}>{currencySymbol}{data.open.toFixed(2)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '20px' }}>
              <span style={{ color: '#9ca3af' }}>High:</span>
              <span style={{ color: '#10b981', fontWeight: 600 }}>{currencySymbol}{data.high.toFixed(2)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '20px' }}>
              <span style={{ color: '#9ca3af' }}>Low:</span>
              <span style={{ color: '#ef4444', fontWeight: 600 }}>{currencySymbol}{data.low.toFixed(2)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '20px' }}>
              <span style={{ color: '#9ca3af' }}>Close:</span>
              <span style={{ color: '#fff', fontWeight: 600 }}>{currencySymbol}{data.close.toFixed(2)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '20px', marginTop: '4px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '4px' }}>
              <span style={{ color: '#9ca3af' }}>Volume:</span>
              <span style={{ color: '#e5e7eb', fontWeight: 600 }}>{data.volume.toLocaleString()}</span>
            </div>
          </div>
        </div>
      );
    }
    return null;
  };

  const [range, setRange] = useState<'1D' | '1W' | '1M' | '1Y'>('1M');
  const [data, setData] = useState<HistoricalPricePoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showSMA20, setShowSMA20] = useState(true);
  const [showSMA50, setShowSMA50] = useState(true);
  const [showSMA200, setShowSMA200] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    let active = true;
    const fetchHistory = async () => {
      setLoading(true);
      setError(null);
      try {
        const historyData = await api.getHistory(company.id, range);
        if (active) {
          // Compute SMAs from closing prices
          const sma20 = computeSMA(historyData, 20);
          const sma50 = computeSMA(historyData, 50);
          const sma200 = computeSMA(historyData, 200);

          const mapped = historyData.map((item, idx) => ({
            ...item,
            openClose: [item.open, item.close],
            sma20: sma20[idx],
            sma50: sma50[idx],
            sma200: sma200[idx],
          }));
          setData(mapped);
        }
      } catch (err: any) {
        if (active) {
          setError(err.message || 'Failed to retrieve historical price data.');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    fetchHistory();

    return () => {
      active = false;
    };
  }, [isOpen, company.id, range]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        backgroundColor: 'rgba(5, 7, 15, 0.85)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1100,
        padding: '20px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '900px',
          height: '600px',
          backgroundColor: '#0b0f19',
          border: '1px solid var(--border-color)',
          borderRadius: '12px',
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--accent)' }}>
                {company.ticker_symbol}
              </span>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                {company.exchange}
              </span>
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              {company.company_name} Historical Stock Performance
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.2s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.03)')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          >
            <X size={18} />
          </button>
        </div>

        {/* Filters Panel */}
        <div
          style={{
            padding: '12px 24px',
            backgroundColor: 'rgba(255,255,255,0.01)',
            borderBottom: '1px solid rgba(255,255,255,0.03)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          {/* Left panel options: Timeframe + SMA Toggles */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            {/* Timeframe selector pills */}
            <div style={{ display: 'flex', gap: '8px' }}>
              {(['1D', '1W', '1M', '1Y'] as const).map((t) => {
                const active = range === t;
                return (
                  <button
                    key={t}
                    onClick={() => setRange(t)}
                    style={{
                      padding: '6px 14px',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      borderRadius: '6px',
                      border: '1px solid',
                      borderColor: active ? 'var(--accent)' : 'rgba(255,255,255,0.05)',
                      backgroundColor: active ? 'rgba(16, 185, 129, 0.12)' : 'rgba(255,255,255,0.02)',
                      color: active ? 'var(--accent)' : 'var(--text-secondary)',
                      cursor: 'pointer',
                      transition: 'var(--transition-smooth)',
                    }}
                  >
                    {t}
                  </button>
                );
              })}
            </div>

            {/* SMA overlay toggles */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>MAs:</span>
              <button
                onClick={() => setShowSMA20(!showSMA20)}
                style={{
                  padding: '5px 12px',
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  borderRadius: '6px',
                  border: '1px solid',
                  borderColor: showSMA20 ? '#eab308' : 'rgba(255,255,255,0.05)',
                  backgroundColor: showSMA20 ? 'rgba(234, 179, 8, 0.12)' : 'rgba(255,255,255,0.02)',
                  color: showSMA20 ? '#eab308' : 'var(--text-muted)',
                  cursor: 'pointer',
                  transition: 'var(--transition-smooth)',
                }}
              >
                SMA-20
              </button>
              <button
                onClick={() => setShowSMA50(!showSMA50)}
                style={{
                  padding: '5px 12px',
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  borderRadius: '6px',
                  border: '1px solid',
                  borderColor: showSMA50 ? '#3b82f6' : 'rgba(255,255,255,0.05)',
                  backgroundColor: showSMA50 ? 'rgba(59, 130, 246, 0.12)' : 'rgba(255,255,255,0.02)',
                  color: showSMA50 ? '#3b82f6' : 'var(--text-muted)',
                  cursor: 'pointer',
                  transition: 'var(--transition-smooth)',
                }}
              >
                SMA-50
              </button>
              <button
                onClick={() => setShowSMA200(!showSMA200)}
                style={{
                  padding: '5px 12px',
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  borderRadius: '6px',
                  border: '1px solid',
                  borderColor: showSMA200 ? '#a855f7' : 'rgba(255,255,255,0.05)',
                  backgroundColor: showSMA200 ? 'rgba(168, 85, 247, 0.12)' : 'rgba(255,255,255,0.02)',
                  color: showSMA200 ? '#a855f7' : 'var(--text-muted)',
                  cursor: 'pointer',
                  transition: 'var(--transition-smooth)',
                }}
              >
                SMA-200
              </button>
            </div>
          </div>

          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              <div className="spinner" style={{ width: '12px', height: '12px', borderLeftColor: 'var(--accent)' }} />
              <span>Fetching new range...</span>
            </div>
          )}
        </div>

        {/* Content Body */}
        <div style={{ flex: 1, padding: '24px', display: 'flex', position: 'relative' }}>
          {error ? (
            <div
              style={{
                margin: 'auto',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                color: 'var(--danger)',
                backgroundColor: 'rgba(239, 68, 68, 0.04)',
                border: '1px solid rgba(239, 68, 68, 0.15)',
                borderRadius: '8px',
                padding: '16px 24px',
                maxWidth: '480px',
              }}
            >
              <AlertOctagon size={24} style={{ flexShrink: 0 }} />
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>Failed to Load Stock Chart</div>
                <div style={{ fontSize: '0.8rem', opacity: 0.8, marginTop: '2px' }}>{error}</div>
              </div>
            </div>
          ) : loading && data.length === 0 ? (
            <div style={{ margin: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', color: 'var(--text-muted)' }}>
              <div className="spinner" style={{ width: '24px', height: '24px', borderLeftColor: 'var(--accent)' }} />
              <span style={{ fontSize: '0.85rem' }}>Loading chart data...</span>
            </div>
          ) : data.length === 0 ? (
            <div style={{ margin: 'auto', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No historical data available for selected range.
            </div>
          ) : (
            <div style={{ width: '100%', height: '100%', position: 'relative' }}>
              {/* Overlay loading spinner when switching ranges */}
              {loading && (
                <div
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    backgroundColor: 'rgba(11, 15, 25, 0.4)',
                    backdropFilter: 'blur(1px)',
                    zIndex: 10,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <div className="spinner" style={{ width: '24px', height: '24px', borderLeftColor: 'var(--accent)' }} />
                </div>
              )}

              <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', gap: '4%' }}>
                {/* Price Chart */}
                <div style={{ height: '72%', width: '100%', position: 'relative' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart syncId="stockHistorySync" data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        stroke="#4b5563"
                        style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)' }}
                        tickFormatter={(val) => {
                          // Compact representation
                          if (range === '1D') return val.split(' ')[1] || val;
                          if (range === '1W') return val.split(' ')[0]?.substring(5) || val;
                          return val.substring(5) || val; // MM-DD
                        }}
                      />
                      <YAxis
                        stroke="#4b5563"
                        style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)' }}
                        domain={['auto', 'auto']}
                        tickFormatter={(val) => `${getCurrencySymbol(company.isin.startsWith('IN') ? 'INR' : 'USD')}${val.toFixed(0)}`}
                      />
                      <Tooltip
                        content={<CustomTooltip />}
                        cursor={{ stroke: 'rgba(255, 255, 255, 0.15)', strokeWidth: 1, strokeDasharray: '3 3' }}
                      />
                      <Bar
                        dataKey="openClose"
                        // Custom CandlestickShape renders wicks and body for each candle.
                        shape={<CandlestickShape />}
                      />
                      {showSMA20 && (
                        <Line
                          type="monotone"
                          dataKey="sma20"
                          stroke="#eab308"
                          strokeWidth={1.5}
                          dot={false}
                          activeDot={false}
                          name="SMA 20"
                        />
                      )}
                      {showSMA50 && (
                        <Line
                          type="monotone"
                          dataKey="sma50"
                          stroke="#3b82f6"
                          strokeWidth={1.5}
                          dot={false}
                          activeDot={false}
                          name="SMA 50"
                        />
                      )}
                      {showSMA200 && (
                        <Line
                          type="monotone"
                          dataKey="sma200"
                          stroke="#a855f7"
                          strokeWidth={1.5}
                          dot={false}
                          activeDot={false}
                          name="SMA 200"
                        />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                {/* Volume Histogram Panel */}
                <div style={{ height: '24%', width: '100%' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart syncId="stockHistorySync" data={data} margin={{ top: 0, right: 10, left: -20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
                      <XAxis dataKey="date" hide={true} />
                      <YAxis
                        stroke="#4b5563"
                        style={{ fontSize: '0.6rem', fontFamily: 'var(--font-mono)' }}
                        tickFormatter={(val) => {
                          if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
                          if (val >= 1e3) return `${(val / 1e3).toFixed(0)}K`;
                          return val.toString();
                        }}
                      />
                      <Bar dataKey="volume">
                        {data.map((entry, index) => {
                          const isUp = entry.close >= entry.open;
                          const fillColor = isUp ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)';
                          return <Cell key={`cell-${index}`} fill={fillColor} />;
                        })}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer info */}
        <div
          style={{
            padding: '12px 24px',
            backgroundColor: 'rgba(255,255,255,0.01)',
            borderTop: '1px solid rgba(255,255,255,0.03)',
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '0.7rem',
            color: 'var(--text-muted)',
          }}
        >
          <span>Data provided by Yahoo Finance feed</span>
          <span>Click outside or press ESC to dismiss</span>
        </div>
      </div>
    </div>
  );
};
