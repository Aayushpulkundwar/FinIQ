import React from 'react';
import { formatPercent, getCurrencySymbol } from '../../utils';

interface SensitivityPoint {
  wacc: number;
  growth_rate: number;
  intrinsic_price: number;
}

interface SensitivityGridProps {
  data: SensitivityPoint[];
  baseWacc?: number;
  baseGrowth?: number;
  currency?: string | null;
}

export const SensitivityGrid: React.FC<SensitivityGridProps> = ({ data, baseWacc, baseGrowth, currency }) => {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return <p style={{ color: '#6b7280', fontSize: '0.8rem' }}>No sensitivity matrix points available.</p>;
  }

  // Extract unique sorted WACC and Growth Rate values from the list
  const uniqueWaccs = Array.from(new Set(data.map(p => p.wacc))).sort((a, b) => a - b);
  const uniqueGrowths = Array.from(new Set(data.map(p => p.growth_rate))).sort((a, b) => a - b);

  // Helper to find a cell value for a specific wacc & growth
  const getCellValue = (wacc: number, growth: number): number | undefined => {
    // We can use a tolerance check since floats might have minor differences
    const pt = data.find(p => Math.abs(p.wacc - wacc) < 0.0001 && Math.abs(p.growth_rate - growth) < 0.0001);
    return pt?.intrinsic_price;
  };

  // Helper to determine cell background color (heatmap style)
  const getCellColor = (val: number) => {
    const prices = data.map(p => p.intrinsic_price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const ratio = (val - min) / range;
    
    // Emerald green scale: opacity from 0.05 to 0.45
    const opacity = 0.05 + ratio * 0.40;
    return `rgba(16, 185, 129, ${opacity})`;
  };

  // Check if a cell represents the base case (matches baseWacc and baseGrowth)
  const isBaseCase = (wacc: number, growth: number) => {
    if (baseWacc === undefined || baseGrowth === undefined) return false;
    return Math.abs(wacc - baseWacc) < 0.0001 && Math.abs(growth - baseGrowth) < 0.0001;
  };

  return (
    <div className="sensitivity-matrix-container">
      <table className="sensitivity-table">
        <thead>
          <tr>
            <th style={{ backgroundColor: 'transparent', border: 'none', color: '#9ca3af', fontWeight: 600 }}>
              WACC \ Growth
            </th>
            {uniqueGrowths.map(g => (
              <th key={g} style={{ color: '#e5e7eb', textAlign: 'right' }}>
                {formatPercent(g)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {uniqueWaccs.map(w => (
            <tr key={w}>
              <td style={{ fontWeight: 'bold', color: '#e5e7eb', backgroundColor: 'rgba(255,255,255,0.02)' }}>
                {formatPercent(w)}
              </td>
              {uniqueGrowths.map(g => {
                const val = getCellValue(w, g);
                const isBase = isBaseCase(w, g);
                
                return (
                  <td
                    key={g}
                    className="sensitivity-cell"
                    style={{
                      backgroundColor: isBase ? 'rgba(6, 182, 212, 0.25)' : (val !== undefined ? getCellColor(val) : undefined),
                      border: isBase ? '2px solid #06b6d4' : undefined,
                      color: isBase ? '#22d3ee' : '#f3f4f6',
                      fontWeight: isBase ? 'bold' : 'normal',
                      textAlign: 'right'
                    }}
                  >
                    {val !== undefined ? `${getCurrencySymbol(currency)}${val.toFixed(2)}` : '—'}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#6b7280' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ display: 'inline-block', width: '12px', height: '12px', backgroundColor: 'rgba(6, 182, 212, 0.25)', border: '1px solid #06b6d4', borderRadius: '2px' }} />
          Base Case Model
        </span>
        <div style={{ display: 'flex', gap: '12px' }}>
          <span>← Lower Value (Darker Green)</span>
          <span>Higher Value (Brighter Green) →</span>
        </div>
      </div>
    </div>
  );
};
