export interface Company {
  id: string;
  company_name: string;
  ticker_symbol: string;
  exchange: string;
  sector: string;
  industry: string;
  isin: string;
  website?: string;
  created_at: string;
  updated_at: string;
}

export type DocumentType = 'annual_report' | 'quarterly_report' | 'earnings_transcript' | 'investor_presentation' | 'sec_filing';

export type IngestionStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface DocumentMetadata {
  id: string;
  company_id: string;
  title: string;
  document_type: DocumentType;
  fiscal_year: number;
  quarter?: number;
  file_path: string;
  status: IngestionStatus;
  chunk_count: number;
  message?: string;
  created_at: string;
  updated_at: string;
}

export interface AIResponse {
  executive_summary: string;
  tabular_analysis?: string;       // Markdown table string, new field from updated prompt
  key_insights: string[];
  supporting_evidence: string[];
  risks_limitations: string[];
  sources: string[];
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response?: AIResponse;
  retrieved_chunks?: any[];
  execution_history?: string[];
}

export interface FinancialStatement {
  id: string;
  period_id: string;
  company_id: string;
  revenue: number;
  ebitda: number;
  operating_income: number;
  net_profit: number;
  eps: number;
  total_assets: number;
  total_liabilities: number;
  shareholders_equity: number;
  operating_cash_flow: number;
  free_cash_flow: number;
  capex: number;
}

export interface FinancialMetric {
  id: string;
  statement_id: string;
  company_id: string;
  revenue_growth_yoy: number;
  ebitda_margin: number;
  operating_margin: number;
  net_profit_margin: number;
  roe: number;
  roce: number;
  asset_turnover: number;
  debt_to_equity: number;
  current_ratio: number;
}

export interface FinancialAnalyzeResponse {
  company_name: string;
  ticker_symbol: string;
  fiscal_year: number;
  period_type: string;
  statements: FinancialStatement;
  metrics: FinancialMetric;
  financial_evidence: Record<string, any>;
  metric_provenance: Record<string, any>;
  reporting_status?: string | null;
}


export interface SensitivityPoint {
  wacc: number;
  growth_rate: number;
  intrinsic_price: number;
}

export interface WaccDetails {
  cost_of_equity: number;
  cost_of_debt: number;
  wacc: number;
  equity_weight: number;
  debt_weight: number;
}

export interface DcfDetails {
  terminal_value: number;
  enterprise_value: number;
  equity_value: number;
  shares_outstanding: number;
  intrinsic_share_price: number;
  baseline_fcf: number;
  fcf_growth_rate: number;
  projected_fcfs: number[];
  terminal_growth_rate: number;
}

export interface ValuationSummary {
  wacc_details: WaccDetails;
  dcf_details: DcfDetails;
  sensitivity_grid: SensitivityPoint[];
  confidence_score: number;
  beta: number | null;
  risk_free_rate: number | null;
  equity_risk_premium: number | null;
  tax_rate: number | null;
  cash: number | null;
  debt: number | null;
  market_cap: number | null;
  cost_of_debt_estimated: boolean;
  tax_rate_estimated: boolean;
  fcf_growth_estimated: boolean;
  as_of: string | null;
  currency?: string | null;
  /** Diagnostic flags from the valuation wrapper. Empty array = no anomalies. */
  valuation_flags?: string[];
}

export interface InvestmentAnalyzeResponse {
  company_id: string;
  company_name: string;
  valuation_summary: ValuationSummary;
  intrinsic_value: number;
  sensitivity_analysis: SensitivityPoint[];
  research_report: string;
}

export interface EventImpact {
  company_id: string;
  company_name: string;
  ticker_symbol: string;
  confidence_score: number;
  impact_direction: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  impact_explanation: string;
}

export interface EventAnalyzeResponse {
  id?: string;
  title: string;
  description: string;
  event_type: string;
  severity: string;
  event_date: string;
  affected_industries: string[];
  potentially_impacted_companies: EventImpact[];
  retrieved_evidence: any[];
  explanation: string;
}

export interface NewsArticle {
  id: string;
  title: string;
  content: string;
  source: string;
  url?: string;
  sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  confidence_score: number;
  published_at: string;
  category: string;
  companies_mentioned: string[];
  industries_mentioned: string[];
}

export interface SentimentBreakdown {
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  total: number;
  overall_sentiment: string;
  positive_pct: number;
  negative_pct: number;
  neutral_pct: number;
}

export interface AnalystConsensus {
  available: boolean;
  reason?: string | null;
  recommendation_key?: string | null;
  recommendation_mean?: number | null;
  target_mean_price?: number | null;
  target_high_price?: number | null;
  target_low_price?: number | null;
  target_median_price?: number | null;
  number_of_analyst_opinions?: number | null;
}

export interface InstitutionalHolder {
  holder: string;
  shares?: number | null;
  date_reported?: string | null;
  pct_out?: number | null;
  value?: number | null;
}

export interface OwnershipStructure {
  available: boolean;
  reason?: string | null;
  held_percent_institutions?: number | null;
  held_percent_insiders?: number | null;
  top_institutional_holders: InstitutionalHolder[];
  major_holders_breakdown: Record<string, any>;
}

export interface TradingMomentum {
  available: boolean;
  reason?: string | null;
  short_percent_of_float?: number | null;
  shares_short?: number | null;
  short_ratio?: number | null;
  fifty_day_average?: number | null;
  two_hundred_day_average?: number | null;
  beta?: number | null;
  price_vs_fifty_day_pct?: number | null;
  price_vs_two_hundred_day_pct?: number | null;
}

export interface PeerMetric {
  ticker: string;
  pe_ratio?: number | null;
  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  roe?: number | null;
}

export interface PeerComparison {
  available: boolean;
  reason?: string | null;
  peers: PeerMetric[];
}

export interface MarketIntelResponse {
  ticker: string;
  currency: string;
  current_price?: number | null;
  analyst_consensus: AnalystConsensus;
  ownership: OwnershipStructure;
  trading_momentum: TradingMomentum;
  peer_comparison: PeerComparison;
  as_of: string;
}

export interface MarketAnalyzeResponse {
  market_summary: string;
  related_news: any[];
  related_events: string[];
  impacted_companies: string[];
  impacted_industries: string[];
  sentiment_analysis: SentimentBreakdown;
  supporting_evidence: string[];
  market_intel?: MarketIntelResponse | null;
}


export interface ChatQueryResponse {
  user_query: string;
  retrieved_chunks: any[];
  company_details?: Record<string, any>;
  document_metadata: any[];
  execution_history: string[];
  final_context: Record<string, any>;
  response?: AIResponse;
  session_id?: string;
}

export interface MarketDataResponse {
  ticker: string;
  available: boolean;
  reason: string | null;
  current_price: number | null;
  currency: string | null;
  market_cap: number | null;
  day_change_pct: number | null;
  day_change_abs: number | null;
  previous_close: number | null;
  week_52_high: number | null;
  week_52_low: number | null;
  pe_ratio: number | null;
  volume: number | null;
  avg_volume: number | null;
}

export interface FinancialSummaryResponse {
  ticker: string;
  available: boolean;
  reason: string | null;
  fiscal_year: string | null;       // e.g. "FY2025"
  currency: string | null;
  revenue: number | null;
  revenue_source: string | null;    // "yahoo_direct" | "calculated" | null
  ebitda: number | null;
  ebitda_source: string | null;
  net_profit: number | null;
  net_profit_source: string | null;
  roe: number | null;
  roe_source: string | null;
}

export interface RecommendationResponse {
  signal: 'Buy' | 'Sell' | 'Hold' | 'Unavailable';
  current_price: number | null;
  intrinsic_value: number | null;
  upside_pct: number | null;
  currency: string | null;
  reason?: string | null;  // only present when signal === 'Unavailable'
  wacc?: number | null;
  terminal_growth_rate?: number | null;
}

export interface SparklinePoint {
  time: string;
  price: number;
}

export interface LivePriceResponse {
  ticker: string;
  current_price: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  sparkline: SparklinePoint[];
  as_of: string;
}

export interface HistoricalPricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

