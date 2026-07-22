import React from 'react';
import { useUIStore } from '../../store/useUIStore';
import { SensitivityGrid } from '../UI/SensitivityGrid';
import { AlertTriangle } from 'lucide-react';
import { formatPercent, formatMarketCap, getCurrencySymbol } from '../../utils';

export const ValuationTab: React.FC = () => {
  const {
    investmentAnalysis,
    isLoadingAnalysis,
    analysisError,
    analysisLoadingMessage,
    runDomainAnalysis,
  } = useUIStore();

  return (
    <div>
      {isLoadingAnalysis && !investmentAnalysis ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#9ca3af', fontSize: '0.9rem' }}>
          <div className="spinner" style={{ width: '16px', height: '16px', borderLeftColor: '#10b981' }} />
          <span>{analysisLoadingMessage || 'Running Investment Analysis...'}</span>
        </div>
      ) : analysisError ? (
        <div className="glass-panel" style={{
          borderLeft: '4px solid #ef4444',
          padding: '16px 20px',
          color: '#ef4444',
          backgroundColor: 'rgba(239, 68, 68, 0.04)',
          borderRadius: '8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          marginTop: '10px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <AlertTriangle size={20} />
            <div>
              <h4 style={{ margin: 0, fontWeight: 700, fontSize: '0.92rem' }}>Couldn't load valuation data</h4>
              <p style={{ margin: '4px 0 0', fontSize: '0.8rem', color: '#fca5a5' }}>
                Reason: {analysisError}
              </p>
            </div>
          </div>
          <button
            onClick={() => runDomainAnalysis('investment')}
            style={{
              alignSelf: 'flex-start',
              padding: '6px 14px',
              backgroundColor: '#1f2937',
              border: '1px solid #4b5563',
              color: '#f3f4f6',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.8rem',
              fontWeight: 600,
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#374151'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#1f2937'; }}
          >
            Retry
          </button>
        </div>
      ) : investmentAnalysis ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1.5fr', gap: '20px' }}>
          <div>
            <h3 style={{ fontSize: '0.95rem', color: '#10b981', textTransform: 'uppercase', marginBottom: '10px' }}>
              DCF Model Assumptions
            </h3>
            {investmentAnalysis.valuation_summary.valuation_flags && investmentAnalysis.valuation_summary.valuation_flags.length > 0 && (
              <div style={{
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                borderRadius: '8px',
                padding: '12px',
                marginBottom: '15px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
              }}>
                {investmentAnalysis.valuation_summary.valuation_flags.includes('double_clamp_detected') && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', color: '#f87171', fontSize: '0.78rem', lineHeight: 1.4 }}>
                    <AlertTriangle size={14} style={{ marginTop: '2px', flexShrink: 0 }} />
                    <div>
                      <strong>Double-Clamp Warning:</strong> Both WACC (6.0%) and FCF Growth (-15.0%) hit their floors. Intrinsic value output is driven by structural floor limits and may be anomalous.
                    </div>
                  </div>
                )}
                {investmentAnalysis.valuation_summary.valuation_flags.includes('extreme_deviation_flagged') && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', color: '#f87171', fontSize: '0.78rem', lineHeight: 1.4 }}>
                    <AlertTriangle size={14} style={{ marginTop: '2px', flexShrink: 0 }} />
                    <div>
                      <strong>High Price Deviation:</strong> Computed intrinsic value deviates by &gt;80% from the current market price. Please interpret this valuation with caution.
                    </div>
                  </div>
                )}
              </div>
            )}
            <table className="sensitivity-table" style={{ textAlign: 'left', marginBottom: '10px', fontSize: '0.8rem' }}>
              <tbody>
                <tr>
                  <td>Risk-Free Rate</td>
                  <td>{formatPercent(investmentAnalysis.valuation_summary.risk_free_rate ?? 0)}</td>
                </tr>
                <tr>
                  <td>Beta</td>
                  <td>{investmentAnalysis.valuation_summary.beta !== null && investmentAnalysis.valuation_summary.beta !== undefined ? investmentAnalysis.valuation_summary.beta.toFixed(2) : '—'}</td>
                </tr>
                <tr>
                  <td>Equity Risk Premium</td>
                  <td>{formatPercent(investmentAnalysis.valuation_summary.equity_risk_premium ?? 0)}</td>
                </tr>
                <tr>
                  <td>Cost of Equity</td>
                  <td style={{ color: '#e5e7eb' }}>{formatPercent(investmentAnalysis.valuation_summary.wacc_details.cost_of_equity)}</td>
                </tr>
                <tr>
                  <td>Cost of Debt (after tax)</td>
                  <td style={{ color: '#e5e7eb' }}>{formatPercent(investmentAnalysis.valuation_summary.wacc_details.cost_of_debt)}</td>
                </tr>
                <tr>
                  <td>Effective Tax Rate</td>
                  <td>{formatPercent(investmentAnalysis.valuation_summary.tax_rate ?? 0)}</td>
                </tr>
                <tr>
                  <td>Weighted Avg Cost of Capital (WACC)</td>
                  <td style={{ fontWeight: 'bold', color: '#10b981' }}>
                    {formatPercent(investmentAnalysis.valuation_summary.wacc_details.wacc)}
                  </td>
                </tr>
                <tr>
                  <td>Terminal Growth Rate</td>
                  <td style={{ color: '#e5e7eb' }}>{formatPercent(investmentAnalysis.valuation_summary.dcf_details.terminal_growth_rate)}</td>
                </tr>
                <tr>
                  <td>Shares Outstanding</td>
                  <td>{investmentAnalysis.valuation_summary.dcf_details.shares_outstanding !== null && investmentAnalysis.valuation_summary.dcf_details.shares_outstanding !== undefined ? (investmentAnalysis.valuation_summary.dcf_details.shares_outstanding / 1e6).toFixed(1) + 'M' : '—'}</td>
                </tr>
                <tr>
                  <td>Total Debt</td>
                  <td>{formatMarketCap(investmentAnalysis.valuation_summary.debt, investmentAnalysis.valuation_summary.currency)}</td>
                </tr>
                <tr>
                  <td>Cash &amp; Equivalents</td>
                  <td>{formatMarketCap(investmentAnalysis.valuation_summary.cash, investmentAnalysis.valuation_summary.currency)}</td>
                </tr>
                <tr>
                  <td>Enterprise Value</td>
                  <td>{formatMarketCap(investmentAnalysis.valuation_summary.dcf_details.enterprise_value, investmentAnalysis.valuation_summary.currency)}</td>
                </tr>
                <tr>
                  <td>Equity Value</td>
                  <td>{formatMarketCap(investmentAnalysis.valuation_summary.dcf_details.equity_value, investmentAnalysis.valuation_summary.currency)}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 'bold' }}>Intrinsic Share Price</td>
                  <td style={{ fontWeight: 'bold', color: '#06b6d4' }}>
                    {getCurrencySymbol(investmentAnalysis.valuation_summary.currency)}
                    {investmentAnalysis.valuation_summary.dcf_details.intrinsic_share_price?.toFixed(2) ?? '—'}
                  </td>
                </tr>
              </tbody>
            </table>
            
            {/* Warnings and Timestamp Caption */}
            <div style={{ color: '#6b7280', fontSize: '0.72rem', display: 'flex', flexDirection: 'column', gap: '4px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '8px' }}>
              {investmentAnalysis.valuation_summary.as_of && (
                <div>Valuation calculation as of {new Date(investmentAnalysis.valuation_summary.as_of).toLocaleString()}</div>
              )}
              {investmentAnalysis.valuation_summary.cost_of_debt_estimated && (
                <div style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span>⚠️</span> Cost of debt estimated — interest expense or debt data was missing or out of bounds.
                </div>
              )}
              {investmentAnalysis.valuation_summary.tax_rate_estimated && (
                <div style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span>⚠️</span> Effective tax rate estimated — fallback to default rate applied.
                </div>
              )}
              {investmentAnalysis.valuation_summary.fcf_growth_estimated && (
                <div style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span>⚠️</span> FCF CAGR growth rate estimated — historical statement data was insufficient.
                </div>
              )}
            </div>
          </div>

          <div>
            <h3 style={{ fontSize: '0.95rem', color: '#10b981', textTransform: 'uppercase', marginBottom: '10px' }}>
              WACC vs Terminal Growth Sensitivity Analysis
            </h3>
            <SensitivityGrid
              data={investmentAnalysis.sensitivity_analysis}
              baseWacc={investmentAnalysis.valuation_summary.wacc_details.wacc}
              baseGrowth={investmentAnalysis.valuation_summary.dcf_details.terminal_growth_rate}
              currency={investmentAnalysis.valuation_summary.currency}
            />
          </div>
        </div>
      ) : (
        <p style={{ color: '#6b7280', fontSize: '0.9rem' }}>Investment analysis data unavailable.</p>
      )}
    </div>
  );
};
