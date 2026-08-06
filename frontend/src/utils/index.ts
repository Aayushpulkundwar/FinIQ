/**
 * Format large dollar figures (e.g. 245,000,000,000) into abbreviated strings (e.g. $245.00B)
 */
export function formatCurrency(value: number): string {
  if (value === 0 || !value) return '$0.00';
  
  const isNegative = value < 0;
  const absValue = Math.abs(value);
  
  let formatted = '';
  if (absValue >= 1e12) {
    formatted = `$${(absValue / 1e12).toFixed(2)}T`;
  } else if (absValue >= 1e9) {
    formatted = `$${(absValue / 1e9).toFixed(2)}B`;
  } else if (absValue >= 1e6) {
    formatted = `$${(absValue / 1e6).toFixed(2)}M`;
  } else {
    formatted = `$${absValue.toLocaleString()}`;
  }
  
  return isNegative ? `-${formatted}` : formatted;
}

/**
 * Format fractional values (e.g. 0.0825) into percentage strings (e.g. 8.25%)
 */
export function formatPercent(value: number): string {
  if (value === 0 || !value) return '0.0%';
  
  // Check if value is already expressed as a whole number (e.g. 8.25 instead of 0.0825)
  // Standard formatting assumes values are decimals (e.g. 0.0825 = 8.25%)
  const percentValue = Math.abs(value) < 1.0 ? value * 100 : value;
  return `${percentValue.toFixed(1)}%`;
}

/**
 * Format large INR figures using the Indian numbering convention (Lakh / Crore).
 * 1 Crore = 10,000,000 (1e7)
 * 1 Lakh  = 100,000   (1e5)
 *
 * Examples:
 *   24_500_000_000  → "₹2,450 Cr"
 *   149_160_000_000 → "₹14,916 Cr"
 *   500_000         → "₹5 L"
 */
export function formatINR(value: number): string {
  if (value === 0 || !value) return '₹0';

  const isNegative = value < 0;
  const abs = Math.abs(value);

  let formatted: string;
  if (abs >= 1e7) {
    // Crore (1 Cr = 1e7)
    const crore = abs / 1e7;
    formatted = `₹${crore.toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`;
  } else if (abs >= 1e5) {
    // Lakh (1 L = 1e5)
    const lakh = abs / 1e5;
    formatted = `₹${lakh.toLocaleString('en-IN', { maximumFractionDigits: 1 })} L`;
  } else {
    formatted = `₹${abs.toLocaleString('en-IN')}`;
  }

  return isNegative ? `-${formatted}` : formatted;
}

/** Map ISO currency codes to display symbols for common currencies. */
export function getCurrencySymbol(currency: string | null | undefined): string {
  const map: Record<string, string> = {
    INR: '₹', USD: '$', GBP: '£', EUR: '€',
    CAD: 'C$', AUD: 'A$', JPY: '¥', HKD: 'HK$', SGD: 'S$',
  };
  return map[(currency ?? '').toUpperCase()] ?? '';
}

/**
 * Format a raw market-cap or financial value using the correct convention for its currency:
 *  - INR  → Indian Crore notation (₹14,916 Cr)
 *  - USD, GBP, EUR, others → Western Billion/Million ($3.20T, $149.16B, £42M)
 */
export function formatMarketCap(value: number | null, currency: string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const sym = getCurrencySymbol(currency);
  const cur = (currency ?? '').toUpperCase();

  if (cur === 'INR') {
    // Indian convention: divide by 1 Crore (1e7)
    const crore = value / 1e7;
    if (crore >= 1_00_000) {
      return `${sym}${(crore / 1_00_000).toLocaleString('en-IN', { maximumFractionDigits: 2 })} L Cr`;
    }
    return `${sym}${Math.round(crore).toLocaleString('en-IN')} Cr`;
  }

  // Western: Trillion / Billion / Million
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${sym}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${sym}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sym}${(abs / 1e6).toFixed(2)}M`;
  return `${sym}${abs.toLocaleString()}`;
}

const INVALID_PLACEHOLDERS = new Set(['string', 'test', 'placeholder', 'none', 'null', 'n/a', 'undefined']);

/**
 * Checks if a company object contains valid, real metadata (filters out placeholder strings).
 */
export function isValidCompany(company: any): boolean {
  if (!company || typeof company !== 'object') return false;
  const { ticker_symbol, company_name, exchange, isin } = company;
  if (!ticker_symbol || !company_name || !exchange || !isin) return false;
  
  if (
    INVALID_PLACEHOLDERS.has(String(ticker_symbol).trim().toLowerCase()) ||
    INVALID_PLACEHOLDERS.has(String(company_name).trim().toLowerCase()) ||
    INVALID_PLACEHOLDERS.has(String(exchange).trim().toLowerCase()) ||
    INVALID_PLACEHOLDERS.has(String(isin).trim().toLowerCase())
  ) {
    return false;
  }
  return true;
}
