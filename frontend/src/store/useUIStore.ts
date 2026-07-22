import { create } from 'zustand';
import type {
  Company,
  DocumentMetadata,
  ChatMessage,
  FinancialAnalyzeResponse,
  EventAnalyzeResponse,
  InvestmentAnalyzeResponse,
  MarketAnalyzeResponse,
  MarketDataResponse,
  FinancialSummaryResponse,
  RecommendationResponse,
} from '../types';
import { api } from '../services/api';
import { isValidCompany } from '../utils';

interface UIState {
  selectedCompany: Company | null;
  companies: Company[];
  activeTab: 'chat' | 'financials' | 'valuation' | 'market';
  conversations: ChatMessage[];
  isGenerating: boolean;
  error: string | null;
  healthStatus: { status: string; postgres: string; redis: string } | null;
  documents: DocumentMetadata[];
  uploadProgress: number;
  uploadStatus: 'idle' | 'uploading' | 'processing' | 'completed' | 'failed';
  uploadError: string | null;

  // Chat Session ID State
  sessionId: string | null;

  // Domain intelligence data context
  financialAnalysis: FinancialAnalyzeResponse | null;
  eventAnalysis: EventAnalyzeResponse | null;
  investmentAnalysis: InvestmentAnalyzeResponse | null;
  marketAnalysis: MarketAnalyzeResponse | null;
  isLoadingAnalysis: boolean;
  analysisError: string | null;
  analysisLoadingMessage: string | null;

  // Live market data (Yahoo Finance)
  liveMarketData: MarketDataResponse | null;
  isLoadingMarketData: boolean;

  // Live financial summary (Yahoo Finance)
  financialSummary: FinancialSummaryResponse | null;
  isLoadingFinancialSummary: boolean;

  // DCF Recommendation (Yahoo Finance + DCF)
  recommendation: RecommendationResponse | null;
  isLoadingRecommendation: boolean;
  recommendationError: string | null;

  setSelectedCompany: (company: Company | null) => void;
  setCompanies: (companies: Company[]) => void;
  setActiveTab: (tab: 'chat' | 'financials' | 'valuation' | 'market') => void;
  fetchMarketData: (companyId: string) => Promise<void>;
  fetchFinancialSummary: (companyId: string) => Promise<void>;
  fetchRecommendation: (companyId: string) => Promise<void>;
  addMessage: (message: ChatMessage) => void;
  clearChat: () => void;
  fetchCompanies: () => Promise<void>;
  fetchDocuments: () => Promise<void>;
  checkHealth: () => Promise<void>;
  setUploadProgress: (progress: number) => void;
  setUploadStatus: (status: 'idle' | 'uploading' | 'processing' | 'completed' | 'failed') => void;
  deleteDocument: (id: string) => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  runDomainAnalysis: (actionType: 'financial' | 'investment' | 'market' | 'event', context?: { title?: string; description?: string }) => Promise<void>;
  
  // Chat History Specific Actions
  loadChatHistory: (sessionId: string) => Promise<void>;
  clearSession: () => void;

  // Recent & Search selections
  recentCompanies: Company[];
  isLoadingRecent: boolean;
  searchResults: Company[];
  isLoadingSearch: boolean;
  fetchRecentCompanies: () => Promise<void>;
  searchCompanies: (query: string) => Promise<void>;
  selectCompany: (company: Company) => Promise<void>;
}

export const useUIStore = create<UIState>((set, get) => ({
  selectedCompany: null,
  companies: [],
  activeTab: 'chat',
  conversations: [],
  isGenerating: false,
  error: null,
  healthStatus: null,
  documents: [],
  uploadProgress: 0,
  uploadStatus: 'idle',
  uploadError: null,

  sessionId: null,

  financialAnalysis: null,
  eventAnalysis: null,
  investmentAnalysis: null,
  marketAnalysis: null,
  isLoadingAnalysis: false,
  analysisError: null,
  analysisLoadingMessage: null,



  liveMarketData: null,
  isLoadingMarketData: false,

  financialSummary: null,
  isLoadingFinancialSummary: false,

  recommendation: null,
  isLoadingRecommendation: false,
  recommendationError: null,

  setSelectedCompany: (company) => {
    set({
      selectedCompany: company,
      liveMarketData: null,
      financialAnalysis: null,
      investmentAnalysis: null,
      marketAnalysis: null,
      eventAnalysis: null,
      recommendation: null,
      analysisError: null,
    });
    if (company) {
      // 1. Retrieve cached chat session_id for active ticker from localStorage
      const ticker = company.ticker_symbol;
      const cachedSessionId = localStorage.getItem(`finiq_session_${ticker}`);
      set({ sessionId: cachedSessionId });

      if (cachedSessionId) {
        get().loadChatHistory(cachedSessionId);
      } else {
        set({ conversations: [] });
      }

      // Trigger a default analysis fetch for the new company (e.g. 2026 default)
      get().runDomainAnalysis('financial');
      get().runDomainAnalysis('market');
      get().runDomainAnalysis('investment');
      // Fetch live market data from Yahoo Finance
      get().fetchMarketData(company.id);
      // Fetch live financial summary from Yahoo Finance
      get().fetchFinancialSummary(company.id);
      // Fetch DCF recommendation from Yahoo Finance
      get().fetchRecommendation(company.id);
    } else {
      // Clear data when no company is selected
      set({
        sessionId: null,
        conversations: [],
        financialAnalysis: null,
        investmentAnalysis: null,
        marketAnalysis: null,
        liveMarketData: null,
        financialSummary: null,
        recommendation: null,
        recommendationError: null,
      });
    }
  },

  setCompanies: (companies) => set({ companies }),
  setActiveTab: (tab) => set({ activeTab: tab, analysisError: null }),

  fetchMarketData: async (companyId: string) => {
    set({ isLoadingMarketData: true });
    try {
      const data = await api.getMarketData(companyId);
      set({ liveMarketData: data, isLoadingMarketData: false });
    } catch (e: any) {
      console.warn(`yfinance Market Data fetch failed or rate-limited for company ${companyId}: ${e.message || e}`);
      set({
        liveMarketData: { ticker: '', available: false, reason: 'Failed to reach market data endpoint', current_price: null, currency: null, market_cap: null, day_change_pct: null, day_change_abs: null, previous_close: null, week_52_high: null, week_52_low: null, pe_ratio: null, volume: null, avg_volume: null },
        isLoadingMarketData: false,
      });
    }
  },

  fetchFinancialSummary: async (companyId: string) => {
    set({ isLoadingFinancialSummary: true });
    try {
      const data = await api.getFinancialSummary(companyId);
      set({ financialSummary: data, isLoadingFinancialSummary: false });
    } catch (e: any) {
      console.warn(`yfinance Financial Summary fetch failed or rate-limited for company ${companyId}: ${e.message || e}`);
      set({
        financialSummary: { ticker: '', available: false, reason: 'Failed to reach financial summary endpoint', fiscal_year: null, currency: null, revenue: null, revenue_source: null, ebitda: null, ebitda_source: null, net_profit: null, net_profit_source: null, roe: null, roe_source: null },
        isLoadingFinancialSummary: false,
      });
    }
  },

  fetchRecommendation: async (companyId: string) => {
    set({ isLoadingRecommendation: true, recommendationError: null });
    try {
      const data = await api.getRecommendation(companyId);
      set({ recommendation: data, isLoadingRecommendation: false });
    } catch (e: any) {
      console.error(`DCF Recommendation fetch failed or rate-limited for company ${companyId}: ${e.message || e}`);
      set({
        recommendation: null,
        isLoadingRecommendation: false,
        recommendationError: e.message || 'Failed to fetch recommendation',
      });
    }
  },

  addMessage: (message) => set((state) => ({ conversations: [...state.conversations, message] })),
  clearChat: () => set({ conversations: [] }),

  fetchCompanies: async () => {
    try {
      const data = await api.listCompanies();
      const validCompanies = data.filter(isValidCompany);
      set({ companies: validCompanies });

      // Auto-select fallback order:
      // 1. Keep existing selectedCompany if already valid
      const current = get().selectedCompany;
      if (current && isValidCompany(current)) return;

      // 2. Pick first valid company from recentCompanies
      const recentValid = get().recentCompanies.find(isValidCompany);
      if (recentValid) {
        get().setSelectedCompany(recentValid);
      } else if (validCompanies.length > 0) {
        // 3. Pick first valid company from listCompanies
        get().setSelectedCompany(validCompanies[0]);
      } else {
        // 4. Fallback to null
        get().setSelectedCompany(null);
      }
    } catch (e: any) {
      set({ error: e.message || 'Failed to fetch companies' });
    }
  },

  fetchDocuments: async () => {
    try {
      const docs = await api.listDocuments();
      set({ documents: docs });
    } catch (e: any) {
      set({ error: e.message || 'Failed to fetch documents' });
    }
  },

  checkHealth: async () => {
    try {
      const health = await api.checkHealth();
      set({ healthStatus: health });
    } catch (e) {
      set({ healthStatus: { status: 'unhealthy', postgres: 'failed', redis: 'failed' } });
    }
  },

  setUploadProgress: (progress) => set({ uploadProgress: progress }),
  setUploadStatus: (status) => set({ uploadStatus: status }),

  deleteDocument: async (id: string) => {
    try {
      await api.deleteDocument(id);
      await get().fetchDocuments();
    } catch (e: any) {
      set({ error: e.message || 'Failed to delete document' });
    }
  },

  sendMessage: async (text: string) => {
    if (!text.trim()) return;
    const { selectedCompany, sessionId } = get();
    const ticker = selectedCompany?.ticker_symbol || null;

    const userMsg: ChatMessage = {
      id: Math.random().toString(36).substring(7),
      sender: 'user',
      content: text,
      timestamp: new Date(),
    };

    set((state) => ({
      conversations: [...state.conversations, userMsg],
      isGenerating: true,
      error: null,
    }));

    try {
      let activeSessionId = sessionId;
      if (!activeSessionId) {
        try {
          const sessionRes = await api.createChatSession(ticker);
          activeSessionId = sessionRes.session_id;
          set({ sessionId: activeSessionId });
          if (ticker) {
            localStorage.setItem(`finiq_session_${ticker}`, activeSessionId);
          }
          console.log(`Chat session successfully initialized for ticker ${ticker}: ${activeSessionId}`);
        } catch (err: any) {
          console.warn(`Chat session creation failed for ticker ${ticker}, proceeding in stateless fallback mode:`, err);
          activeSessionId = null;
        }
      }

      const res = await api.queryChat(text, activeSessionId);
      
      // If session was created on the fly by the backend, save it locally
      if (res.session_id && !get().sessionId) {
        set({ sessionId: res.session_id });
        if (ticker) {
          localStorage.setItem(`finiq_session_${ticker}`, res.session_id);
        }
      }

      const assistantMsg: ChatMessage = {
        id: Math.random().toString(36).substring(7),
        sender: 'assistant',
        content: res.response?.executive_summary || 'No summary response generated by LLM.',
        timestamp: new Date(),
        response: res.response || undefined,
        retrieved_chunks: res.retrieved_chunks,
        execution_history: res.execution_history,
      };

      set((state) => ({
        conversations: [...state.conversations, assistantMsg],
        isGenerating: false,
      }));

      // Update right context details if query execution returns company info
      if (res.company_details) {
        const found = get().companies.find(
          (c) => c.ticker_symbol.toLowerCase() === (res.company_details?.ticker_symbol || '').toLowerCase()
        );
        if (found && found.id !== get().selectedCompany?.id) {
          set({ selectedCompany: found });
        }
      }
    } catch (e: any) {
      console.error(`Query execution failed: ${e.message || e}`);
      const errorMsg: ChatMessage = {
        id: Math.random().toString(36).substring(7),
        sender: 'assistant',
        content: `Error executing query: ${e.message || 'Unknown orchestrator error.'}`,
        timestamp: new Date(),
      };
      set((state) => ({
        conversations: [...state.conversations, errorMsg],
        isGenerating: false,
      }));
    }
  },

  runDomainAnalysis: async (actionType, context) => {
    const { selectedCompany } = get();
    if (actionType !== 'event' && !selectedCompany) {
      set({ analysisError: 'No company selected for analysis' });
      return;
    }

    set({ isLoadingAnalysis: true, analysisError: null, analysisLoadingMessage: null });
    try {
      if (actionType === 'financial' && selectedCompany) {
        const res = await api.analyzeFinancial(selectedCompany.id, 2026, 'annual');
        set({ financialAnalysis: res });
      } else if (actionType === 'investment' && selectedCompany) {
        try {
          const res = await api.analyzeInvestment(selectedCompany.id, 2026, (msg) => {
            set({ analysisLoadingMessage: msg });
          });
          set({ investmentAnalysis: res });
        } catch (err: any) {
          console.error(`DCF Investment Analysis failed for company ${selectedCompany.company_name} (ID: ${selectedCompany.id}): ${err.message || err}`);
          throw err;
        }
      } else if (actionType === 'market' && selectedCompany) {
        const res = await api.analyzeMarket(selectedCompany.id, null);
        set({ marketAnalysis: res });
      } else if (actionType === 'event') {
        const title = context?.title || 'Macro Economic Shift';
        const description = context?.description || 'Rising interest rates and supply chain bottlenecks.';
        const res = await api.analyzeEvent(title, description);
        set({ eventAnalysis: res });
      }
    } catch (e: any) {
      set({ analysisError: e.message || `Failed to run ${actionType} analysis.` });
    } finally {
      set({ isLoadingAnalysis: false, analysisLoadingMessage: null });
    }
  },

  loadChatHistory: async (sessionId: string) => {
    set({ isGenerating: true, error: null });
    try {
      const history = await api.getChatHistory(sessionId);
      const mapped: ChatMessage[] = history.map((msg: any) => ({
        id: msg.id,
        sender: msg.role === 'user' ? 'user' : 'assistant',
        content: msg.content,
        timestamp: new Date(msg.created_at),
        response: msg.metadata?.response || undefined,
        retrieved_chunks: msg.metadata?.retrieved_chunks || undefined,
        execution_history: msg.metadata?.execution_history || undefined,
      }));
      set({ conversations: mapped, isGenerating: false });
    } catch (e: any) {
      console.error(`Failed to load chat history for session ${sessionId}: ${e.message || e}`);
      set({ error: e.message || 'Failed to load conversation history', isGenerating: false });
    }
  },

  clearSession: () => {
    const { selectedCompany, sessionId } = get();
    // 1. Optimistic clear
    set({ sessionId: null, conversations: [] });
    if (selectedCompany) {
      localStorage.removeItem(`finiq_session_${selectedCompany.ticker_symbol}`);
    }

    // 2. Background delete request
    if (sessionId) {
      api.deleteChatSession(sessionId).catch((err: any) => {
        console.error(`Failed to delete chat session ${sessionId} in background: ${err.message || err}`);
      });
    }
  },

  recentCompanies: [],
  isLoadingRecent: false,
  searchResults: [],
  isLoadingSearch: false,

  fetchRecentCompanies: async () => {
    set({ isLoadingRecent: true });
    try {
      const data = await api.getRecentCompanies();
      const validRecent = data.filter(isValidCompany);
      set({ recentCompanies: validRecent, isLoadingRecent: false });

      // If no company selected yet, select the most recent valid one
      if (!get().selectedCompany && validRecent.length > 0) {
        get().setSelectedCompany(validRecent[0]);
      }
    } catch (e) {
      console.warn('Failed to fetch recent companies:', e);
      set({ isLoadingRecent: false });
    }
  },

  searchCompanies: async (query: string) => {
    if (!query.trim()) {
      set({ searchResults: [] });
      return;
    }
    set({ isLoadingSearch: true });
    try {
      const data = await api.searchCompanies(query);
      set({ searchResults: data.filter(isValidCompany), isLoadingSearch: false });
    } catch (e) {
      console.warn('Failed to search companies:', e);
      set({ isLoadingSearch: false });
    }
  },

  selectCompany: async (company: Company) => {
    get().setSelectedCompany(company);
    try {
      await api.selectCompany(company.id);
      await get().fetchRecentCompanies();
    } catch (e) {
      console.warn('Failed to register recent selection:', e);
    }
  },
}));

