import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { formatMarketCap, formatPercent, getCurrencySymbol } from '../../utils';
import {
  TrendingUp,
  TrendingDown,
  AlertOctagon,
  Calendar,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface FinancialsTabProps {
  ticker: string;
}

export const FinancialsTab: React.FC<FinancialsTabProps> = ({ ticker }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [periodType, setPeriodType] = useState<'annual' | 'quarterly'>('annual');

  useEffect(() => {
    let active = true;
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.getDetailedFinancials(ticker);
        if (active) {
          if (result.available === false) {
            setError(result.reason || 'Financial data unavailable');
          } else {
            setData(result);
          }
        }
      } catch (err: any) {
        if (active) {
          setError(err.message || 'Failed to fetch financial statements');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    fetchData();
    return () => {
      active = false;
    };
  }, [ticker]);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '10px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#9ca3af', fontSize: '0.9rem' }}>
          <div className="spinner" style={{ width: '16px', height: '16px', borderLeftColor: '#10b981' }} />
          <span>Fetching live financials from yfinance...</span>
        </div>
        {/* Loading skeletons */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '14px' }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} className="glass-panel" style={{ height: '80px', animation: 'pulse 1.5s infinite' }} />
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px' }}>
          <div className="glass-panel" style={{ height: '240px', animation: 'pulse 1.5s infinite' }} />
          <div className="glass-panel" style={{ height: '240px', animation: 'pulse 1.5s infinite' }} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel" style={{
        borderLeft: '4px solid #ef4444',
        padding: '16px 20px',
        color: '#ef4444',
        backgroundColor: 'rgba(239, 68, 68, 0.04)',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        marginTop: '10px'
      }}>
        <AlertOctagon size={20} />
        <div>
          <h4 style={{ margin: 0, fontWeight: 700, fontSize: '0.92rem' }}>Financial Data Unavailable</h4>
          <p style={{ margin: '4px 0 0', fontSize: '0.8rem', color: '#fca5a5' }}>
            Ticker: {ticker} (resolved via yfinance) | Reason: {error}
          </p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const currentCurrency = data.currency || 'USD';
  const periods = periodType === 'annual' ? data.annual || [] : data.quarterly || [];
  
  const chartData = [...periods]
    .reverse()
    .map((p: any) => ({
      period: p.period,
      revenue: p.revenue || 0,
      ebitda: p.ebitda || 0,
      netIncome: p.net_income || 0,
    }));

  const renderYoYBadge = (val: number | null | undefined) => {
    if (val === null || val === undefined || val === 0) return null;
    const isPositive = val >= 0;
    return (
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '2px',
        fontSize: '0.72rem',
        fontWeight: 600,
        marginLeft: '8px',
        padding: '1px 5px',
        borderRadius: '4px',
        backgroundColor: isPositive ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
        color: isPositive ? '#10b981' : '#ef4444',
      }}>
        {isPositive ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
        {isPositive ? '+' : ''}{val.toFixed(1)}%
      </span>
    );
  };

  const renderValueCell = (val: number | null | undefined) => {
    if (val === null || val === undefined) return <span style={{ color: '#4b5563' }}>—</span>;
    return formatMarketCap(val, currentCurrency);
  };

  const renderEpsCell = (val: number | null | undefined) => {
    if (val === null || val === undefined) return <span style={{ color: '#4b5563' }}>—</span>;
    const symbol = getCurrencySymbol(currentCurrency);
    return `${symbol}${val.toFixed(2)}`;
  };

  const formatRatioVal = (val: number | null | undefined, isPercent: boolean) => {
    if (val === null || val === undefined) return '—';
    return isPercent ? formatPercent(val) : `${(val / 100).toFixed(2)}x`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* 1. Header controls */}
      <div className="flex-between" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)', paddingBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Calendar size={15} color="#10b981" />
          <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
            Currency: <strong style={{ color: '#f3f4f6' }}>{currentCurrency}</strong>
            {data.fiscal_year_end && (
              <> | Fiscal Year End: <strong style={{ color: '#f3f4f6' }}>{data.fiscal_year_end.split('T')[0]}</strong></>
            )}
          </span>
        </div>
        
        {/* Toggle Switch */}
        <div style={{
          display: 'inline-flex',
          backgroundColor: 'rgba(255,255,255,0.03)',
          padding: '2px',
          borderRadius: '6px',
          border: '1px solid rgba(255,255,255,0.05)'
        }}>
          <button
            onClick={() => setPeriodType('annual')}
            style={{
              padding: '4px 10px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: periodType === 'annual' ? '#10b981' : 'transparent',
              color: periodType === 'annual' ? '#060a0f' : '#9ca3af',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              transition: 'var(--transition-smooth)'
            }}
          >
            Annual
          </button>
          <button
            onClick={() => setPeriodType('quarterly')}
            style={{
              padding: '4px 10px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: periodType === 'quarterly' ? '#10b981' : 'transparent',
              color: periodType === 'quarterly' ? '#060a0f' : '#9ca3af',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              transition: 'var(--transition-smooth)'
            }}
          >
            Quarterly
          </button>
        </div>
      </div>

      {/* 2. Ratios Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '14px' }}>
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '12px 14px' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.3px' }}>Return on Equity</span>
          <span style={{ fontSize: '1.05rem', fontWeight: 700, color: '#10b981' }}>
            {formatRatioVal(data.ratios.roe_pct, true)}
          </span>
        </div>
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '12px 14px' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.3px' }}>Return on Assets</span>
          <span style={{ fontSize: '1.05rem', fontWeight: 700, color: '#10b981' }}>
            {formatRatioVal(data.ratios.roa_pct, true)}
          </span>
        </div>
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '12px 14px' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.3px' }}>Gross Margin</span>
          <span style={{ fontSize: '1.05rem', fontWeight: 700, color: '#10b981' }}>
            {formatRatioVal(data.ratios.gross_margin_pct, true)}
          </span>
        </div>
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '12px 14px' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.3px' }}>Operating Margin</span>
          <span style={{ fontSize: '1.05rem', fontWeight: 700, color: '#10b981' }}>
            {formatRatioVal(data.ratios.operating_margin_pct, true)}
          </span>
        </div>
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '12px 14px' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.3px' }}>Net Margin</span>
          <span style={{ fontSize: '1.05rem', fontWeight: 700, color: '#10b981' }}>
            {formatRatioVal(data.ratios.net_margin_pct, true)}
          </span>
        </div>
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '12px 14px' }}>
          <span style={{ fontSize: '0.72rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.3px' }}>Debt to Equity</span>
          <span style={{ fontSize: '1.05rem', fontWeight: 700, color: '#06b6d4' }}>
            {formatRatioVal(data.ratios.debt_to_equity, false)}
          </span>
        </div>
      </div>

      {/* 3. Table and Chart Split Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px' }}>
        
        {/* Table Column */}
        <div>
          <h3 style={{ fontSize: '0.85rem', color: '#10b981', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '10px' }}>
            Income Statement Metrics
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table className="sensitivity-table" style={{ textAlign: 'left', width: '100%', fontSize: '0.8rem' }}>
              <thead>
                <tr>
                  <th>Metric</th>
                  {periods.map((p: any) => (
                    <th key={p.period} style={{ textAlign: 'right' }}>{p.period}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600 }}>Total Revenue</td>
                  {periods.map((p: any) => (
                    <td key={p.period} style={{ textAlign: 'right' }}>
                      {renderValueCell(p.revenue)}
                      {renderYoYBadge(p.revenue_yoy_pct)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Gross Profit</td>
                  {periods.map((p: any) => (
                    <td key={p.period} style={{ textAlign: 'right' }}>
                      {renderValueCell(p.gross_profit)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Operating Income</td>
                  {periods.map((p: any) => (
                    <td key={p.period} style={{ textAlign: 'right' }}>
                      {renderValueCell(p.operating_income)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>EBITDA</td>
                  {periods.map((p: any) => (
                    <td key={p.period} style={{ textAlign: 'right' }}>
                      {renderValueCell(p.ebitda)}
                      {renderYoYBadge(p.ebitda_yoy_pct)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Net Income</td>
                  {periods.map((p: any) => (
                    <td key={p.period} style={{ textAlign: 'right' }}>
                      {renderValueCell(p.net_income)}
                      {renderYoYBadge(p.net_income_yoy_pct)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Basic EPS</td>
                  {periods.map((p: any) => (
                    <td key={p.period} style={{ textAlign: 'right' }}>
                      {renderEpsCell(p.eps_basic)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Diluted EPS</td>
                  {periods.map((p: any) => (
                    <td key={p.period} style={{ textAlign: 'right' }}>
                      {renderEpsCell(p.eps_diluted)}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Chart Column */}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <h3 style={{ fontSize: '0.85rem', color: '#10b981', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '10px' }}>
            Revenue &amp; EBITDA Trends
          </h3>
          <div className="glass-panel" style={{ flex: 1, minHeight: '260px', padding: '16px 12px 6px' }}>
            <ResponsiveContainer width="100%" height="95%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: -5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="period" stroke="#6b7280" style={{ fontSize: '0.72rem' }} />
                <YAxis
                  stroke="#6b7280"
                  style={{ fontSize: '0.72rem' }}
                  tickFormatter={(val) => {
                    if (val === 0) return '0';
                    const isINR = currentCurrency === 'INR';
                    const unit = isINR ? 'Cr' : 'B';
                    const factor = isINR ? 1e7 : 1e9;
                    return `${val >= 0 ? '' : '-'}${Math.abs(val / factor).toFixed(0)}${unit}`;
                  }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0a0f18',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '8px',
                    fontSize: '0.75rem'
                  }}
                  labelStyle={{ color: '#10b981', fontWeight: 600 }}
                  formatter={(val: any, name: any) => {
                    const label = name === 'revenue' ? 'Revenue' : name === 'ebitda' ? 'EBITDA' : 'Net Income';
                    return [formatMarketCap(val, currentCurrency), label];
                  }}
                />
                <Legend wrapperStyle={{ fontSize: '0.72rem', color: '#9ca3af' }} />
                <Bar dataKey="revenue" fill="#10b981" name="revenue" radius={[4, 4, 0, 0]} />
                <Bar dataKey="ebitda" fill="#06b6d4" name="ebitda" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>

      {/* 4. Caption */}
      <div style={{ display: 'flex', justifyContent: 'space-between', color: '#6b7280', fontSize: '0.72rem', marginTop: '10px' }}>
        <span>Data source: yfinance live feed API</span>
        <span>Data as of {new Date(data.as_of).toLocaleString()}</span>
      </div>

    </div>
  );
};
