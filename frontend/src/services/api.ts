import type {
  Company,
  DocumentMetadata,
  ChatQueryResponse,
  FinancialAnalyzeResponse,
  EventAnalyzeResponse,
  InvestmentAnalyzeResponse,
  MarketAnalyzeResponse,
  MarketDataResponse,
  FinancialSummaryResponse,
  RecommendationResponse,
  LivePriceResponse,
  HistoricalPricePoint,
} from '../types';

import { logNetwork } from '../utils/debugLogger';

const API_BASE_URL = 'http://localhost:8000/api/v1';

async function loggedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const start = performance.now();
  const method = init?.method || 'GET';
  const url = input.toString();
  
  try {
    const res = await fetch(input, init);
    const duration = Math.round(performance.now() - start);
    
    if (!res.ok) {
      let errBody: any = null;
      try {
        const cloned = res.clone();
        errBody = await cloned.json();
      } catch {
        try {
          const cloned = res.clone();
          errBody = await cloned.text();
        } catch {
          // ignore
        }
      }
      logNetwork(method, url, res.status, duration, errBody);
    } else {
      logNetwork(method, url, res.status, duration);
    }
    return res;
  } catch (err: any) {
    const duration = Math.round(performance.now() - start);
    logNetwork(method, url, 0, duration, err.message || err);
    throw err;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetail = 'API Request Failed';
    try {
      const errorData = await response.json();
      errorDetail = errorData.detail || errorDetail;
    } catch {
      // Ignore if body is not JSON
    }
    throw new Error(errorDetail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  // Health
  checkHealth: async () => {
    const res = await loggedFetch(`${API_BASE_URL}/health`);
    return handleResponse<{ status: string; postgres: string; redis: string }>(res);
  },

  // Companies
  listCompanies: async (): Promise<Company[]> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies?limit=100`);
    return handleResponse<Company[]>(res);
  },

  getCompany: async (id: string): Promise<Company> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/${id}`);
    return handleResponse<Company>(res);
  },

  createCompany: async (company: Omit<Company, 'id' | 'created_at' | 'updated_at'>): Promise<Company> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(company),
    });
    return handleResponse<Company>(res);
  },

  // Documents
  listDocuments: async (): Promise<DocumentMetadata[]> => {
    const res = await loggedFetch(`${API_BASE_URL}/documents?limit=100`);
    return handleResponse<DocumentMetadata[]>(res);
  },

  uploadDocument: async (
    companyId: string,
    title: string,
    documentType: string,
    fiscalYear: number,
    quarter: number | null,
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<DocumentMetadata> => {
    const formData = new FormData();
    formData.append('company_id', companyId);
    formData.append('title', title);
    formData.append('document_type', documentType);
    formData.append('fiscal_year', String(fiscalYear));
    if (quarter !== null) {
      formData.append('quarter', String(quarter));
    }
    formData.append('file', file);

    // Using XMLHttpRequest to support upload progress reporting with logging
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const start = performance.now();
      xhr.open('POST', `${API_BASE_URL}/documents`);

      if (onProgress) {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percent = Math.round((event.loaded / event.total) * 100);
            onProgress(percent);
          }
        };
      }

      xhr.onload = () => {
        const duration = Math.round(performance.now() - start);
        if (xhr.status >= 200 && xhr.status < 300) {
          logNetwork('POST', `${API_BASE_URL}/documents`, xhr.status, duration);
          try {
            resolve(JSON.parse(xhr.responseText) as DocumentMetadata);
          } catch (e) {
            reject(new Error('Failed to parse upload response'));
          }
        } else {
          logNetwork('POST', `${API_BASE_URL}/documents`, xhr.status, duration, xhr.responseText);
          try {
            const err = JSON.parse(xhr.responseText);
            reject(new Error(err.detail || 'Upload failed'));
          } catch {
            reject(new Error(`Upload failed with status ${xhr.status}`));
          }
        }
      };

      xhr.onerror = () => {
        const duration = Math.round(performance.now() - start);
        logNetwork('POST', `${API_BASE_URL}/documents`, 0, duration, 'Network error during upload');
        reject(new Error('Network error during upload'));
      };

      xhr.send(formData);
    });
  },

  deleteDocument: async (id: string): Promise<DocumentMetadata> => {
    const res = await loggedFetch(`${API_BASE_URL}/documents/${id}`, {
      method: 'DELETE',
    });
    return handleResponse<DocumentMetadata>(res);
  },

  // AI Chat
  queryChat: async (query: string, sessionId?: string | null): Promise<ChatQueryResponse> => {
    const res = await loggedFetch(`${API_BASE_URL}/chat/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, session_id: sessionId }),
    });
    return handleResponse<ChatQueryResponse>(res);
  },

  // Chat Sessions
  createChatSession: async (ticker?: string | null): Promise<{ session_id: string }> => {
    const res = await loggedFetch(`${API_BASE_URL}/chat/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker }),
    });
    return handleResponse<{ session_id: string }>(res);
  },

  getChatHistory: async (sessionId: string): Promise<any[]> => {
    const res = await loggedFetch(`${API_BASE_URL}/chat/sessions/${sessionId}/history`);
    return handleResponse<any[]>(res);
  },

  deleteChatSession: async (sessionId: string): Promise<any> => {
    const res = await loggedFetch(`${API_BASE_URL}/chat/sessions/${sessionId}`, {
      method: 'DELETE',
    });
    return handleResponse<any>(res);
  },

  // Financial Intelligence
  analyzeFinancial: async (companyId: string, fiscalYear: number, periodType: string): Promise<FinancialAnalyzeResponse> => {
    const res = await loggedFetch(`${API_BASE_URL}/financial/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_id: companyId,
        fiscal_year: fiscalYear,
        period_type: periodType,
      }),
    });
    return handleResponse<FinancialAnalyzeResponse>(res);
  },

  // Event Intelligence
  analyzeEvent: async (title: string, description: string): Promise<EventAnalyzeResponse> => {
    const res = await loggedFetch(`${API_BASE_URL}/events/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });
    return handleResponse<EventAnalyzeResponse>(res);
  },

  // Investment Analysis
  analyzeInvestment: async (
    companyId: string,
    fiscalYear: number,
    onProgress?: (msg: string) => void
  ): Promise<InvestmentAnalyzeResponse> => {
    // 1. Enqueue the task
    const res = await loggedFetch(`${API_BASE_URL}/investment/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_id: companyId,
        fiscal_year: fiscalYear,
      }),
    });
    
    const enqueueData = await handleResponse<{ task_id: string; status: string }>(res);
    const taskId = enqueueData.task_id;

    // 2. Poll the task status until completion
    return new Promise<InvestmentAnalyzeResponse>((resolve, reject) => {
      const intervalId = setInterval(async () => {
        try {
          const pollRes = await loggedFetch(`${API_BASE_URL}/investment/tasks/${taskId}`);
          const taskData = await handleResponse<{
            task_id: string;
            status: string;
            message?: string;
            result?: InvestmentAnalyzeResponse;
            error?: string;
          }>(pollRes);

          if (taskData.status === 'SUCCESS' && taskData.result) {
            clearInterval(intervalId);
            resolve(taskData.result);
          } else if (taskData.status === 'FAILURE') {
            clearInterval(intervalId);
            reject(new Error(taskData.error || 'Investment analysis task failed.'));
          } else if (taskData.status === 'PROGRESS') {
            if (onProgress && taskData.message) {
              onProgress(taskData.message);
            }
          }
        } catch (err) {
          clearInterval(intervalId);
          reject(err);
        }
      }, 2000);
    });
  },

  // Market Intelligence
  analyzeMarket: async (companyId: string | null, industry: string | null, limit: number = 10): Promise<MarketAnalyzeResponse> => {
    const res = await loggedFetch(`${API_BASE_URL}/market/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_id: companyId,
        industry: industry,
        limit: limit,
      }),
    });
    return handleResponse<MarketAnalyzeResponse>(res);
  },

  // Live Market Data (Yahoo Finance via backend)
  getMarketData: async (companyId: string): Promise<MarketDataResponse> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/${companyId}/market-data`);
    return handleResponse<MarketDataResponse>(res);
  },

  // Financial Summary — live Yahoo Finance data (Revenue, EBITDA, Net Profit, ROE)
  getFinancialSummary: async (companyId: string): Promise<FinancialSummaryResponse> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/${companyId}/financial-summary`);
    return handleResponse<FinancialSummaryResponse>(res);
  },

  // DCF Recommendation — live Buy/Hold/Sell signal via Yahoo Finance + DCF
  getRecommendation: async (companyId: string): Promise<RecommendationResponse> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/${companyId}/recommendation`);
    return handleResponse<RecommendationResponse>(res);
  },

  // Detailed Financials — live Yahoo Finance financials and ratios
  getDetailedFinancials: async (ticker: string): Promise<any> => {
    const res = await loggedFetch(`http://localhost:8000/api/company/${ticker}/financials`);
    return handleResponse<any>(res);
  },

  // Company Search
  searchCompanies: async (q: string): Promise<Company[]> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/search?q=${encodeURIComponent(q)}`);
    return handleResponse<Company[]>(res);
  },

  // Recent Selected Companies
  getRecentCompanies: async (): Promise<Company[]> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/recent`);
    return handleResponse<Company[]>(res);
  },

  // Select Company Registration
  selectCompany: async (id: string): Promise<any> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/${id}/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<any>(res);
  },

  // Live Price & Sparkline
  getLivePrice: async (id: string): Promise<LivePriceResponse> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/${id}/live-price`);
    return handleResponse<LivePriceResponse>(res);
  },

  // Historical OHLC Timeframe Data
  getHistory: async (id: string, range: string): Promise<HistoricalPricePoint[]> => {
    const res = await loggedFetch(`${API_BASE_URL}/companies/${id}/history?range=${range}`);
    return handleResponse<HistoricalPricePoint[]>(res);
  },
};
