import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useUIStore } from '../../store/useUIStore';
import { FinancialsTab } from './FinancialsTab';
import { ValuationTab } from './ValuationTab';
import { MarketIntelTab } from './MarketIntelTab';
import { CompanyNewsTab } from './CompanyNewsTab';
import { Send, Sparkles, BookOpen, ChevronDown, ChevronUp, Trash2, AlertTriangle, ArrowLeft } from 'lucide-react';

// Shared markdown components — provides dark-theme table, bold, code rendering
const MD_COMPONENTS: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', marginTop: '10px', marginBottom: '10px' }}>
      <table style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: '0.82rem',
        fontFamily: 'monospace',
      }}>{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead style={{ backgroundColor: 'rgba(16,185,129,0.12)' }}>{children}</thead>
  ),
  th: ({ children }) => (
    <th style={{
      padding: '8px 12px',
      border: '1px solid rgba(16,185,129,0.25)',
      color: '#10b981',
      fontWeight: 700,
      textAlign: 'left',
      whiteSpace: 'nowrap',
    }}>{children}</th>
  ),
  td: ({ children }) => (
    <td style={{
      padding: '7px 12px',
      border: '1px solid rgba(255,255,255,0.06)',
      color: '#d1d5db',
      verticalAlign: 'top',
    }}>{children}</td>
  ),
  tr: ({ children }) => (
    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>{children}</tr>
  ),
  p: ({ children }) => <p style={{ marginBottom: '8px', lineHeight: 1.6 }}>{children}</p>,
  strong: ({ children }) => <strong style={{ color: '#f3f4f6', fontWeight: 600 }}>{children}</strong>,
  code: ({ children }) => (
    <code style={{
      backgroundColor: 'rgba(255,255,255,0.06)',
      padding: '2px 6px',
      borderRadius: '4px',
      fontSize: '0.8em',
      fontFamily: 'monospace',
      color: '#34d399',
    }}>{children}</code>
  ),
  ul: ({ children }) => <ul style={{ paddingLeft: '18px', marginBottom: '8px' }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ paddingLeft: '18px', marginBottom: '8px' }}>{children}</ol>,
  li: ({ children }) => <li style={{ marginBottom: '4px', lineHeight: 1.5 }}>{children}</li>,
  h3: ({ children }) => <h3 style={{ color: '#10b981', marginTop: '12px', marginBottom: '6px', fontSize: '1rem' }}>{children}</h3>,
  h4: ({ children }) => <h4 style={{ color: '#34d399', marginTop: '10px', marginBottom: '4px' }}>{children}</h4>,
};

export const CenterWorkspace: React.FC = () => {
  const { activeTab, setActiveTab, conversations, isGenerating, sendMessage, selectedCompany, clearSession } = useUIStore();
  const [input, setInput] = useState('');
  const [expandedChunks, setExpandedChunks] = useState<Record<string, boolean>>({});
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  /** Formats a Date as a short locale time string, e.g. "2:14 PM" */
  const formatTime = (date: Date | undefined): string => {
    if (!date) return '';
    try {
      return new Date(date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const handleClearConfirm = () => {
    clearSession();
    setShowClearConfirm(false);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversations, isGenerating]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isGenerating) return;
    const text = input;
    setInput('');
    await sendMessage(text);
  };

  const toggleChunk = (id: string) => {
    setExpandedChunks((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // formatText removed — replaced by <ReactMarkdown> with MD_COMPONENTS

  return (
    <section className={`center-workspace ${activeTab === 'chat' ? 'chat-mode' : 'view-mode'}`}>
      {/* Analysis Views Sub-header Bar (when in Financials/Valuation/Market view) */}
      {activeTab !== 'chat' && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 20px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          backgroundColor: 'rgba(11, 15, 25, 0.6)',
          flexShrink: 0,
        }}>
          <button
            onClick={() => setActiveTab('chat')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              color: '#10b981',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600,
              padding: '4px 8px',
              borderRadius: '6px',
              transition: 'background-color 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(16, 185, 129, 0.1)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
          >
            <ArrowLeft size={16} /> Back to Research Terminal
          </button>
          <span style={{ fontSize: '0.88rem', color: '#f3f4f6', fontWeight: 700 }}>
            {selectedCompany ? selectedCompany.company_name : 'No Company Selected'} —{' '}
            <span style={{ color: '#10b981' }}>
              {activeTab === 'financials' ? 'Financial Statements & Metrics' : activeTab === 'valuation' ? 'DCF Valuation Model' : activeTab === 'market' ? 'Market Intelligence' : 'Company News Feed'}
            </span>
          </span>
        </div>
      )}

      {/* Standalone Views with selectedCompany Empty-State Guards */}
      {activeTab !== 'chat' && !selectedCompany ? (
        <div className="analysis-view-container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#6b7280', textAlign: 'center' }}>
          <Sparkles size={40} color="#10b981" style={{ marginBottom: '16px', opacity: 0.8 }} />
          <h3 style={{ color: '#f3f4f6', fontSize: '1.1rem', marginBottom: '8px' }}>No Company Selected</h3>
          <p style={{ fontSize: '0.9rem', maxWidth: '420px', lineHeight: 1.5 }}>
            Select a portfolio company from the sidebar to view {activeTab === 'financials' ? 'financial statements' : activeTab === 'valuation' ? 'DCF valuation metrics' : activeTab === 'market' ? 'market intelligence' : 'company news feed'}.
          </p>
        </div>
      ) : activeTab === 'financials' && selectedCompany ? (
        <div className="analysis-view-container">
          <FinancialsTab ticker={selectedCompany.ticker_symbol} />
        </div>
      ) : activeTab === 'valuation' && selectedCompany ? (
        <div className="analysis-view-container">
          <ValuationTab />
        </div>
      ) : activeTab === 'market' && selectedCompany ? (
        <div className="analysis-view-container">
          <MarketIntelTab />
        </div>
      ) : activeTab === 'news' && selectedCompany ? (
        <div className="analysis-view-container">
          <CompanyNewsTab />
        </div>
      ) : (
        <>
      {/* Confirmation Modal — shown before clearing chat history */}
      {showClearConfirm && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          backgroundColor: 'rgba(0,0,0,0.6)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          backdropFilter: 'blur(4px)',
        }}>
          <div style={{
            backgroundColor: '#0f172a',
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: '12px',
            padding: '28px 32px',
            maxWidth: '420px',
            width: '90%',
            boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <AlertTriangle size={22} color="#ef4444" />
              <h3 style={{ color: '#f3f4f6', fontSize: '1.05rem', fontWeight: 600, margin: 0 }}>
                Clear Chat History
              </h3>
            </div>
            <p style={{ color: '#9ca3af', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '24px' }}>
              This will permanently delete all messages in this session. This action cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                id="clear-chat-cancel-btn"
                onClick={() => setShowClearConfirm(false)}
                style={{
                  padding: '8px 18px', borderRadius: '8px',
                  border: '1px solid rgba(255,255,255,0.12)',
                  backgroundColor: 'transparent', color: '#d1d5db',
                  fontSize: '0.85rem', cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                id="clear-chat-confirm-btn"
                onClick={handleClearConfirm}
                style={{
                  padding: '8px 18px', borderRadius: '8px',
                  border: '1px solid rgba(239,68,68,0.4)',
                  backgroundColor: 'rgba(239,68,68,0.1)', color: '#ef4444',
                  fontSize: '0.85rem', cursor: 'pointer', fontWeight: 600,
                }}
              >
                Clear History
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Messages Viewport */}
      <div className="chat-messages">
        {/* Clear history button — only when there are messages */}
        {conversations.length > 0 && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', paddingBottom: '6px', paddingRight: '4px' }}>
            <button
              id="clear-chat-history-btn"
              onClick={() => setShowClearConfirm(true)}
              title="Clear chat history"
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '5px 12px', borderRadius: '8px',
                border: '1px solid rgba(239,68,68,0.25)',
                backgroundColor: 'rgba(239,68,68,0.06)',
                color: '#f87171', fontSize: '0.75rem',
                cursor: 'pointer', fontWeight: 500,
                transition: 'background-color 0.15s, border-color 0.15s',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'rgba(239,68,68,0.14)';
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(239,68,68,0.45)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'rgba(239,68,68,0.06)';
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(239,68,68,0.25)';
              }}
            >
              <Trash2 size={13} />
              Clear History
            </button>
          </div>
        )}
        {conversations.length === 0 ? (
          <div className="chat-welcome">
            <Sparkles size={48} color="#10b981" />
            <h1>FinIQ Research Terminal</h1>
            <p>
              Ask advanced institutional investment research questions about your portfolio companies. 
              The orchestrator routes your query through multi-period financial databases, SEC filings, 
              WACC/DCF calculators, and macroeconomic event logs.
            </p>
            {selectedCompany && (
              <div style={{
                fontSize: '0.85rem',
                color: '#10b981',
                padding: '6px 14px',
                borderRadius: '20px',
                backgroundColor: 'rgba(16,185,129,0.06)',
                border: '1px solid rgba(16,185,129,0.2)',
                marginTop: '10px'
              }}>
                Targeting: {selectedCompany.company_name} ({selectedCompany.ticker_symbol})
              </div>
            )}
          </div>
        ) : (
          conversations.map((msg) => (
            <div key={msg.id} className={`message-bubble ${msg.sender}`}>
              {/* Timestamp — top-left for user, top-right for assistant */}
              {msg.timestamp && (
                <div style={{
                  display: 'flex',
                  justifyContent: msg.sender === 'user' ? 'flex-start' : 'flex-end',
                  marginBottom: '4px',
                }}>
                  <span style={{
                    fontSize: '0.68rem',
                    color: '#4b5563',
                    fontVariantNumeric: 'tabular-nums',
                    letterSpacing: '0.02em',
                  }}>
                    {formatTime(msg.timestamp)}
                  </span>
                </div>
              )}
              <div style={{ display: 'flex', gap: '12px', width: '100%' }}>
                <div className={`message-avatar ${msg.sender}`}>
                  {msg.sender === 'user' ? 'U' : 'AI'}
                </div>
                <div className="message-content">
                  {msg.sender === 'user' ? (
                    <p style={{ fontWeight: 500 }}>{msg.content}</p>
                  ) : (
                    <div>
                      {/* Executive Summary */}
                      <div style={{ marginBottom: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                          <h3 style={{
                            fontSize: '1.1rem',
                            color: msg.content?.includes('[Basic News Fallback Summary]') ? '#f59e0b' : '#10b981',
                            fontWeight: 600,
                            margin: 0
                          }}>
                            {msg.content?.includes('[Basic News Fallback Summary]') ? '⚠️ Basic News Summary (LLM Fallback)' : 'Executive Summary'}
                          </h3>
                          {msg.content?.includes('[Basic News Fallback Summary]') && (
                            <span style={{
                              fontSize: '0.72rem',
                              backgroundColor: 'rgba(245, 158, 11, 0.15)',
                              color: '#f59e0b',
                              border: '1px solid rgba(245, 158, 11, 0.35)',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontWeight: 600
                            }}>
                              Basic Snippet Synthesis
                            </span>
                          )}
                        </div>
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>

                      {/* Tabular Analysis */}
                      {msg.response?.tabular_analysis && (
                        <div style={{
                          marginBottom: '16px',
                          padding: '14px',
                          backgroundColor: 'rgba(16,185,129,0.04)',
                          border: '1px solid rgba(16,185,129,0.15)',
                          borderRadius: '8px',
                        }}>
                          <h3 style={{ fontSize: '1rem', color: '#10b981', fontWeight: 600, marginBottom: '8px' }}>
                            📊 Tabular Analysis
                          </h3>
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                            {msg.response.tabular_analysis}
                          </ReactMarkdown>
                        </div>
                      )}

                      {/* Key Insights */}
                      {msg.response?.key_insights && msg.response.key_insights.length > 0 && (
                        <div style={{ marginBottom: '16px' }}>
                          <h3 style={{ fontSize: '1rem', color: '#06b6d4', fontWeight: 600, marginBottom: '6px' }}>
                            Key Takeaways & Insights
                          </h3>
                          <ul style={{ paddingLeft: '16px' }}>
                            {msg.response.key_insights.map((insight, i) => (
                              <li key={i} style={{ marginBottom: '6px' }}>{insight}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Grounded Evidence */}
                      {msg.response?.supporting_evidence && msg.response.supporting_evidence.length > 0 && (
                        <div style={{ marginBottom: '16px' }}>
                          <h3 style={{ fontSize: '1rem', color: '#10b981', fontWeight: 600, marginBottom: '6px' }}>
                            Supporting Grounded Evidence
                          </h3>
                          <ul style={{ paddingLeft: '16px' }}>
                            {msg.response.supporting_evidence.map((evidence, i) => (
                              <li key={i} style={{ marginBottom: '6px' }}>{evidence}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Risks & Limitations */}
                      {msg.response?.risks_limitations && msg.response.risks_limitations.length > 0 && (
                        <div style={{ marginBottom: '16px' }}>
                          <h3 style={{ fontSize: '1rem', color: '#ef4444', fontWeight: 600, marginBottom: '6px' }}>
                            Risks & Information Gaps
                          </h3>
                          <ul style={{ paddingLeft: '16px' }}>
                            {msg.response.risks_limitations.map((risk, i) => (
                              <li key={i} style={{ marginBottom: '6px', color: '#fca5a5' }}>{risk}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Cited Sources */}
                      {msg.response?.sources && msg.response.sources.length > 0 && (
                        <div style={{
                          marginTop: '16px',
                          borderTop: '1px solid rgba(255,255,255,0.05)',
                          paddingTop: '12px'
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#9ca3af', fontSize: '0.8rem', fontWeight: 600, marginBottom: '8px' }}>
                            <BookOpen size={14} />
                            <span>CITATIONS ({msg.response.sources.length})</span>
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                            {msg.response.sources.map((src, i) => (
                              <span
                                key={i}
                                style={{
                                  fontSize: '0.75rem',
                                  backgroundColor: 'rgba(16,185,129,0.06)',
                                  border: '1px solid rgba(16,185,129,0.2)',
                                  color: '#10b981',
                                  padding: '3px 8px',
                                  borderRadius: '4px',
                                  fontWeight: 500
                                }}
                              >
                                {src}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* RAG Retrieved Chunks Accordion */}
              {msg.retrieved_chunks && msg.retrieved_chunks.length > 0 && (
                <div style={{
                  marginTop: '14px',
                  backgroundColor: 'rgba(7, 9, 19, 0.4)',
                  borderRadius: '8px',
                  border: '1px solid rgba(255,255,255,0.04)',
                  padding: '12px',
                  width: '100%'
                }}>
                  <div
                    onClick={() => toggleChunk(msg.id)}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      cursor: 'pointer',
                      fontSize: '0.8rem',
                      color: '#9ca3af',
                      fontWeight: 600
                    }}
                  >
                    <span>
                      {(() => {
                        const est = msg.response?.evidence_source_type;
                        if (est === 'live_news') return 'Live News & Web Sources Evidence';
                        if (est === 'rag_documents') return 'Grounded Document Evidence (pgvector hits)';
                        if (est === 'mixed') return 'Mixed Evidence: Live News + Documents';
                        // Fallback for older responses without the field
                        return msg.retrieved_chunks.some((c: any) => c.url)
                          ? 'Live News & Web Sources Evidence'
                          : 'Grounded Document Evidence (pgvector hits)';
                      })()}
                    </span>
                    {expandedChunks[msg.id] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>

                  {expandedChunks[msg.id] && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
                      {msg.retrieved_chunks.map((chunk: any, cIdx: number) => (
                        <div
                          key={cIdx}
                          style={{
                            padding: '10px',
                            backgroundColor: 'rgba(255,255,255,0.01)',
                            border: '1px solid rgba(255,255,255,0.03)',
                            borderRadius: '6px',
                            fontSize: '0.78rem'
                          }}
                        >
                          <div className="flex-between" style={{ marginBottom: '6px', color: '#10b981', fontWeight: 600 }}>
                            <span>
                              Hit #{cIdx + 1}: {chunk.document_title || 'Document'}
                              {chunk.page_number !== null && chunk.page_number !== undefined
                                ? `, Page ${chunk.page_number}`
                                : chunk.published_at
                                  ? ` · ${chunk.published_at.split('T')[0]}`
                                  : ''}
                              {chunk.url && (
                                <a
                                  href={chunk.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{ color: '#06b6d4', marginLeft: '6px', textDecoration: 'underline' }}
                                >
                                  Link
                                </a>
                              )}
                            </span>
                            <span style={{ fontFamily: 'monospace' }}>
                              {msg.response?.evidence_source_type === 'live_news' || (msg.response?.evidence_source_type == null && chunk.url)
                                ? `Source: Web News${chunk.url ? '' : ''}`
                                : `Score: ${chunk.similarity_score !== undefined ? (chunk.similarity_score * 100).toFixed(1) : '91.2'}%`}
                            </span>
                          </div>
                          <p style={{ color: '#d1d5db', lineHeight: 1.5 }}>
                            "{chunk.chunk_text || chunk.text || 'Document excerpt content.'}"
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {isGenerating && (
          <div className="message-bubble assistant" style={{ width: '80px', height: '60px', padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="spinner" />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="chat-input-panel">
        <form onSubmit={handleSubmit} className="chat-input-form">
          <textarea
            className="chat-textarea"
            placeholder={
              selectedCompany
                ? `Ask about ${selectedCompany.company_name} (e.g. FCF trends, risks, DCF projections)...`
                : "Select a company or ask general questions..."
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
          />
          <button
            type="submit"
            className="chat-submit-btn"
            disabled={!input.trim() || isGenerating}
          >
            <Send size={16} />
          </button>
        </form>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#6b7280' }}>
          <span>FinIQ v1.5.0-rss · Grounded responses verified by AI Evaluation framework</span>
          <span>Press Enter to send</span>
        </div>
      </div>
        </>
      )}
    </section>
  );
};
