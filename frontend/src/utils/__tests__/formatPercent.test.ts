import { formatPercent } from '../index';

describe('formatPercent utility', () => {
  it('formats whole number percentage values correctly', () => {
    expect(formatPercent(6.0)).toBe('6.0%');
    expect(formatPercent(21.27)).toBe('21.3%');
    expect(formatPercent(5.62)).toBe('5.6%');
    expect(formatPercent(100.0)).toBe('100.0%');
  });

  it('formats raw decimal fraction percentage values correctly', () => {
    expect(formatPercent(0.06)).toBe('6.0%');
    expect(formatPercent(0.2127)).toBe('21.3%');
  });

  it('handles null, undefined, and zero correctly', () => {
    expect(formatPercent(0)).toBe('0.0%');
    // @ts-ignore
    expect(formatPercent(null)).toBe('0.0%');
    // @ts-ignore
    expect(formatPercent(undefined)).toBe('0.0%');
  });
});
