import React from 'react';
import { useUIStore } from '../../store/useUIStore';
import {
  formatPercent,
  formatMarketCap,
  getCurrencySymbol,
} from '../../utils';
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Award,
  Users,
  Activity,
  Flame,
  CheckCircle,
} from 'lucide-react';

export const MarketIntelTab: React.FC = () => {
  const { marketAnalysis, isLoadingAnalysis, analysisError } = useUIStore();

  if (isLoadingAnalysis) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '10px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#9ca3af', fontSize: '0.9rem' }}>
          <div className="spinner" style={{ width: '16px', height: '16px', borderLeftColor: '#10b981' }} />
          <span>Running Market Intelligence scan...</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <div className="glass-panel" style={{ height: '220px', animation: 'pulse 1.5s infinite' }} />
          <div className="glass-panel" style={{ height: '220px', animation: 'pulse 1.5s infinite' }} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: '20px' }}>
          <div className="glass-panel" style={{ height: '260px', animation: 'pulse 1.5s infinite' }} />
          <div className="glass-panel" style={{ height: '260px', animation: 'pulse 1.5s infinite' }} />
        </div>
      </div>
    );
  }

  if (analysisError) {
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
        <AlertTriangle size={20} />
        <div>
          <h4 style={{ margin: 0, fontWeight: 700, fontSize: '0.92rem' }}>Failed to load market intelligence</h4>
          <p style={{ margin: '4px 0 0', fontSize: '0.8rem', color: '#fca5a5' }}>
            Reason: {analysisError}
          </p>
        </div>
      </div>
    );
  }

  if (!marketAnalysis || !marketAnalysis.market_intel) {
    return (
      <div className="glass-panel" style={{ padding: '24px', textAlign: 'center', color: '#6b7280' }}>
        <p style={{ fontSize: '0.9rem', margin: 0 }}>Market intelligence data is unavailable for this company.</p>
      </div>
    );
  }

  const { market_intel } = marketAnalysis;
  const currency = market_intel.currency || 'USD';
  const symbol = getCurrencySymbol(currency);
  const currentPrice = market_intel.current_price;

  const renderSectionHeader = (title: string, icon: React.ReactNode) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '8px' }}>
      {icon}
      <h3 style={{ fontSize: '0.9rem', color: '#10b981', textTransform: 'uppercase', fontWeight: 700, margin: 0, letterSpacing: '0.5px' }}>
        {title}
      </h3>
    </div>
  );

  const renderUnavailable = (reason?: string | null) => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100px', backgroundColor: 'rgba(255,255,255,0.01)', border: '1px dashed rgba(255,255,255,0.05)', borderRadius: '6px' }}>
      <span style={{ fontSize: '0.8rem', color: '#4b5563', fontStyle: 'italic' }}>
        {reason || 'Not available for this ticker'}
      </span>
    </div>
  );

  const getRecommendationBadgeColor = (key?: string) => {
    const k = (key || '').toLowerCase();
    if (k.includes('buy') || k.includes('strong_buy') || k.includes('outperform')) return { bg: 'rgba(16,185,129,0.1)', text: '#10b981' };
    if (k.includes('sell') || k.includes('underperform')) return { bg: 'rgba(239,68,68,0.1)', text: '#ef4444' };
    return { bg: 'rgba(245,158,11,0.1)', text: '#f59e0b' };
  };

  const getRecommendationLabel = (key?: string) => {
    const k = (key || '').toLowerCase();
    if (k.includes('buy')) return 'Buy';
    if (k.includes('sell')) return 'Sell';
    if (k.includes('hold')) return 'Hold';
    return key || 'N/A';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* 2-Column Upper Section */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        
        {/* CARD 1: Analyst Consensus */}
        <div className="glass-panel" style={{ padding: '16px 20px', borderRadius: '8px' }}>
          {renderSectionHeader('Analyst Consensus', <Award size={16} color="#10b981" />)}
          {!market_intel.analyst_consensus.available ? (
            renderUnavailable(market_intel.analyst_consensus.reason)
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>Consensus Rating</span>
                {market_intel.analyst_consensus.recommendation_key ? (
                  <span style={{
                    fontSize: '0.78rem',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    fontWeight: 700,
                    backgroundColor: getRecommendationBadgeColor(market_intel.analyst_consensus.recommendation_key).bg,
                    color: getRecommendationBadgeColor(market_intel.analyst_consensus.recommendation_key).text,
                    textTransform: 'uppercase',
                  }}>
                    {getRecommendationLabel(market_intel.analyst_consensus.recommendation_key)}
                  </span>
                ) : (
                  <span style={{ fontSize: '0.82rem', color: '#f3f4f6', fontWeight: 600 }}>N/A</span>
                )}
              </div>

              {market_intel.analyst_consensus.recommendation_mean && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>Mean Rating (1-5 scale)</span>
                  <span style={{ fontSize: '0.82rem', color: '#f3f4f6', fontWeight: 600 }}>
                    {market_intel.analyst_consensus.recommendation_mean.toFixed(2)}
                  </span>
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>Analyst Opinions Count</span>
                <span style={{ fontSize: '0.82rem', color: '#f3f4f6', fontWeight: 600 }}>
                  {market_intel.analyst_consensus.number_of_analyst_opinions ?? 'N/A'}
                </span>
              </div>

              {/* Target Price Range Bar Indicator */}
              {market_intel.analyst_consensus.target_low_price && market_intel_has_targets(market_intel.analyst_consensus) && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#9ca3af' }}>
                    <span>Target Range Indicator</span>
                    <span style={{ color: '#06b6d4' }}>
                      Current: {symbol}{currentPrice?.toFixed(2)}
                    </span>
                  </div>
                  <div style={{ position: 'relative', height: '6px', backgroundColor: '#1f2937', borderRadius: '3px', margin: '8px 0 16px' }}>
                    {/* The bar spans from low to high */}
                    <div style={{
                      position: 'absolute',
                      left: '0%',
                      right: '0%',
                      height: '100%',
                      backgroundColor: 'rgba(16,185,129,0.3)',
                      borderRadius: '3px'
                    }} />
                    {/* Current Price Marker */}
                    {currentPrice && (
                      <div
                        style={{
                          position: 'absolute',
                          left: `${calculatePositionPercentage(
                            currentPrice,
                            market_intel.analyst_consensus.target_low_price,
                            market_intel.analyst_consensus.target_high_price
                          )}%`,
                          top: '-4px',
                          width: '14px',
                          height: '14px',
                          borderRadius: '50%',
                          backgroundColor: '#06b6d4',
                          border: '2px solid #111827',
                          transform: 'translateX(-50%)',
                          zIndex: 2,
                        }}
                        title={`Current Price: ${symbol}${currentPrice}`}
                      />
                    )}
                    {/* Mean Target Marker */}
                    {market_intel.analyst_consensus.target_mean_price && (
                      <div
                        style={{
                          position: 'absolute',
                          left: `${calculatePositionPercentage(
                            market_intel.analyst_consensus.target_mean_price,
                            market_intel.analyst_consensus.target_low_price,
                            market_intel.analyst_consensus.target_high_price
                          )}%`,
                          top: '-4px',
                          width: '4px',
                          height: '14px',
                          backgroundColor: '#10b981',
                          transform: 'translateX(-50%)',
                          zIndex: 1,
                        }}
                        title={`Mean Target: ${symbol}${market_intel.analyst_consensus.target_mean_price}`}
                      />
                    )}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#6b7280' }}>
                    <span>Low: {symbol}{market_intel.analyst_consensus.target_low_price.toFixed(2)}</span>
                    <span style={{ color: '#10b981' }}>Mean: {symbol}{market_intel.analyst_consensus.target_mean_price?.toFixed(2)}</span>
                    <span>High: {symbol}{market_intel.analyst_consensus.target_high_price?.toFixed(2)}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* CARD 2: Trading & Momentum */}
        <div className="glass-panel" style={{ padding: '16px 20px', borderRadius: '8px' }}>
          {renderSectionHeader('Trading & Momentum', <Activity size={16} color="#10b981" />)}
          {!market_intel.trading_momentum.available ? (
            renderUnavailable(market_intel.trading_momentum.reason)
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '4px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>50-Day Moving Avg</span>
                  <span style={{ fontSize: '0.85rem', color: '#f3f4f6', fontWeight: 600 }}>
                    {market_intel.trading_momentum.fifty_day_average ? `${symbol}${market_intel.trading_momentum.fifty_day_average.toFixed(2)}` : '—'}
                  </span>
                  {renderDeltaBadge(market_intel.trading_momentum.price_vs_fifty_day_pct)}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>200-Day Moving Avg</span>
                  <span style={{ fontSize: '0.85rem', color: '#f3f4f6', fontWeight: 600 }}>
                    {market_intel.trading_momentum.two_hundred_day_average ? `${symbol}${market_intel.trading_momentum.two_hundred_day_average.toFixed(2)}` : '—'}
                  </span>
                  {renderDeltaBadge(market_intel.trading_momentum.price_vs_two_hundred_day_pct)}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.03)', paddingTop: '6px' }}>
                <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>Beta (Market Volatility)</span>
                <span style={{ fontSize: '0.82rem', color: '#f3f4f6', fontWeight: 600 }}>
                  {market_intel.trading_momentum.beta !== null && market_intel.trading_momentum.beta !== undefined ? market_intel.trading_momentum.beta.toFixed(2) : '—'}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>Short % of Float</span>
                <span style={{ fontSize: '0.82rem', color: '#f3f4f6', fontWeight: 600 }}>
                  {market_intel.trading_momentum.short_percent_of_float !== null && market_intel.trading_momentum.short_percent_of_float !== undefined ? formatPercent(market_intel.trading_momentum.short_percent_of_float) : '—'}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>Shares Short</span>
                <span style={{ fontSize: '0.82rem', color: '#f3f4f6', fontWeight: 600 }}>
                  {market_intel.trading_momentum.shares_short ? (market_intel.trading_momentum.shares_short / 1e6).toFixed(2) + 'M' : '—'}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.82rem', color: '#9ca3af' }}>Short Ratio (Days to Cover)</span>
                <span style={{ fontSize: '0.82rem', color: '#f3f4f6', fontWeight: 600 }}>
                  {market_intel.trading_momentum.short_ratio !== null && market_intel.trading_momentum.short_ratio !== undefined ? market_intel.trading_momentum.short_ratio.toFixed(1) : '—'}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 2-Column Lower Section */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr', gap: '20px' }}>
        
        {/* CARD 3: Ownership Structure */}
        <div className="glass-panel" style={{ padding: '16px 20px', borderRadius: '8px' }}>
          {renderSectionHeader('Ownership Structure', <Users size={16} color="#10b981" />)}
          {!market_intel.ownership.available ? (
            renderUnavailable(market_intel.ownership.reason)
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {/* Stacked Bar Percentage */}
              {(market_intel.ownership.held_percent_institutions !== null || market_intel.ownership.held_percent_insiders !== null) && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#9ca3af' }}>
                    <span>Stakeholder Breakdown</span>
                    <span style={{ color: '#6b7280' }}>Institutional vs Insider</span>
                  </div>
                  <div style={{ display: 'flex', height: '16px', borderRadius: '4px', overflow: 'hidden', backgroundColor: '#1f2937' }}>
                    {market_intel.ownership.held_percent_institutions !== null && (
                      <div
                        style={{
                          width: `${market_intel.ownership.held_percent_institutions}%`,
                          backgroundColor: '#10b981',
                        }}
                        title={`Institutional: ${(market_intel.ownership.held_percent_institutions ?? 0).toFixed(1)}%`}
                      />
                    )}
                    {market_intel.ownership.held_percent_insiders !== null && (
                      <div
                        style={{
                          width: `${market_intel.ownership.held_percent_insiders}%`,
                          backgroundColor: '#06b6d4',
                        }}
                        title={`Insider: ${(market_intel.ownership.held_percent_insiders ?? 0).toFixed(1)}%`}
                      />
                    )}
                    {/* Remaining Float */}
                    <div
                      style={{
                        flex: 1,
                        backgroundColor: '#374151',
                      }}
                      title="Retail & Others"
                    />
                  </div>
                  <div style={{ display: 'flex', gap: '14px', fontSize: '0.7rem', color: '#9ca3af', marginTop: '2px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#10b981' }} />
                      <span>Institutions ({market_intel.ownership.held_percent_institutions?.toFixed(1) ?? '0.0'}%)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#06b6d4' }} />
                      <span>Insiders ({market_intel.ownership.held_percent_insiders?.toFixed(1) ?? '0.0'}%)</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Top Institutional Holders list */}
              {market_intel.ownership.top_institutional_holders && market_intel.ownership.top_institutional_holders.length > 0 ? (
                <div>
                  <h4 style={{ fontSize: '0.78rem', color: '#10b981', textTransform: 'uppercase', marginBottom: '8px', fontWeight: 600 }}>
                    Top Institutional Holders
                  </h4>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="sensitivity-table" style={{ width: '100%', fontSize: '0.72rem', borderCollapse: 'collapse', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#6b7280' }}>
                          <th style={{ padding: '4px' }}>Holder</th>
                          <th style={{ padding: '4px', textAlign: 'right' }}>Shares</th>
                          <th style={{ padding: '4px', textAlign: 'right' }}>% Out</th>
                          <th style={{ padding: '4px', textAlign: 'right' }}>Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {market_intel.ownership.top_institutional_holders.map((holder, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)', color: '#f3f4f6' }}>
                            <td style={{ padding: '6px 4px', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', maxWidth: '120px' }} title={holder.holder}>
                              {holder.holder}
                            </td>
                            <td style={{ padding: '6px 4px', textAlign: 'right' }}>
                              {holder.shares ? (holder.shares / 1e6).toFixed(1) + 'M' : '—'}
                            </td>
                            <td style={{ padding: '6px 4px', textAlign: 'right' }}>
                              {holder.pct_out ? holder.pct_out.toFixed(2) + '%' : '—'}
                            </td>
                            <td style={{ padding: '6px 4px', textAlign: 'right' }}>
                              {holder.value ? formatMarketCap(holder.value, currency) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: '0.75rem', color: '#6b7280', fontStyle: 'italic', textAlign: 'center', marginTop: '10px' }}>
                  No institutional holding records available.
                </div>
              )}
            </div>
          )}
        </div>

        {/* CARD 4: Peer/Sector Comparison */}
        <div className="glass-panel" style={{ padding: '16px 20px', borderRadius: '8px' }}>
          {renderSectionHeader('Peer/Sector Comparison', <Flame size={16} color="#10b981" />)}
          {!market_intel.peer_comparison.available || market_intel.peer_comparison.peers.length === 0 ? (
            renderUnavailable(market_intel.peer_comparison.reason)
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ overflowX: 'auto' }}>
                <table className="sensitivity-table" style={{ width: '100%', fontSize: '0.75rem', borderCollapse: 'collapse', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#6b7280' }}>
                      <th style={{ padding: '6px 4px' }}>Ticker</th>
                      <th style={{ padding: '6px 4px', textAlign: 'right' }}>P/E Ratio</th>
                      <th style={{ padding: '6px 4px', textAlign: 'right' }}>Gross Marg.</th>
                      <th style={{ padding: '6px 4px', textAlign: 'right' }}>Oper. Marg.</th>
                      <th style={{ padding: '6px 4px', textAlign: 'right' }}>Net Marg.</th>
                      <th style={{ padding: '6px 4px', textAlign: 'right' }}>ROE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {market_intel.peer_comparison.peers.map((peer, idx) => {
                      const isTarget = peer.ticker === market_intel.ticker;
                      return (
                        <tr
                          key={idx}
                          style={{
                            borderBottom: '1px solid rgba(255,255,255,0.02)',
                            color: isTarget ? '#10b981' : '#f3f4f6',
                            backgroundColor: isTarget ? 'rgba(16,185,129,0.05)' : 'transparent',
                            fontWeight: isTarget ? 700 : 400,
                          }}
                        >
                          <td style={{ padding: '8px 4px' }}>
                            {peer.ticker}
                            {isTarget && (
                              <span style={{ fontSize: '0.62rem', fontWeight: 600, padding: '1px 4px', backgroundColor: 'rgba(16,185,129,0.15)', color: '#10b981', borderRadius: '3px', marginLeft: '6px' }}>
                                TARGET
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '8px 4px', textAlign: 'right' }}>
                            {peer.pe_ratio !== null && peer.pe_ratio !== undefined ? peer.pe_ratio.toFixed(1) : '—'}
                          </td>
                          <td style={{ padding: '8px 4px', textAlign: 'right' }}>
                            {peer.gross_margin !== null && peer.gross_margin !== undefined ? formatPercent(peer.gross_margin) : '—'}
                          </td>
                          <td style={{ padding: '8px 4px', textAlign: 'right' }}>
                            {peer.operating_margin !== null && peer.operating_margin !== undefined ? formatPercent(peer.operating_margin) : '—'}
                          </td>
                          <td style={{ padding: '8px 4px', textAlign: 'right' }}>
                            {peer.net_margin !== null && peer.net_margin !== undefined ? formatPercent(peer.net_margin) : '—'}
                          </td>
                          <td style={{ padding: '8px 4px', textAlign: 'right' }}>
                            {peer.roe !== null && peer.roe !== undefined ? formatPercent(peer.roe) : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div style={{ fontSize: '0.7rem', color: '#6b7280', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '6px' }}>
                <CheckCircle size={10} color="#10b981" />
                <span>Target company margins and ROE are sourced directly from corporate filings DB records for 100% internal consistency.</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Data as of timestamp caption */}
      <div style={{ color: '#6b7280', fontSize: '0.72rem', display: 'flex', flexDirection: 'column', gap: '4px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '8px' }}>
        <div>Market Intelligence data as of {new Date(market_intel.as_of).toLocaleString()}</div>
      </div>

    </div>
  );
};

/* Helper Functions */

function calculatePositionPercentage(value: number, min: number | null | undefined, max: number | null | undefined): number {
  const minVal = min ?? 0;
  const maxVal = max ?? 0;
  if (maxVal === minVal) return 50;
  const pct = ((value - minVal) / (maxVal - minVal)) * 100;
  return Math.max(0, Math.min(100, pct));
}

function market_intel_has_targets(consensus: any): boolean {
  return (
    consensus.target_low_price !== null &&
    consensus.target_high_price !== null &&
    consensus.target_low_price !== undefined &&
    consensus.target_high_price !== undefined
  );
}

function renderDeltaBadge(val: number | null | undefined) {
  if (val === null || val === undefined || val === 0) return null;
  const isPositive = val >= 0;
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '2px',
      fontSize: '0.72rem',
      fontWeight: 600,
      width: 'fit-content',
      marginTop: '2px',
      color: isPositive ? '#10b981' : '#ef4444',
    }}>
      {isPositive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
      {isPositive ? '+' : ''}{val.toFixed(1)}% vs avg
    </span>
  );
}
