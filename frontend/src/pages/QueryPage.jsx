import React, { useState, useRef, useEffect } from 'react';
import apiService from '../services/apiService';
import './QueryPage.css';

function QueryPage({ user }) {
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState('');
  const [retrievedDocs, setRetrievedDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('answer');
  const [error, setError] = useState('');
  const [recommendedQA, setRecommendedQA] = useState([]);
  const answerBoxRef = useRef(null);
  const sessionIdRef = useRef(sessionStorage.getItem('atlas-query-session-id'));

  if (!sessionIdRef.current) {
    sessionIdRef.current = crypto.randomUUID();
    sessionStorage.setItem('atlas-query-session-id', sessionIdRef.current);
  }

  useEffect(() => {
    const fetchRecommended = async () => {
      try {
        const res = await apiService.getRecommendedQuestions();
        if (res && res.recommended_qa) {
          setRecommendedQA(res.recommended_qa);
        }
      } catch (err) {
        console.warn('Failed to load recommended questions:', err);
      }
    };
    fetchRecommended();
  }, []);

  const handleSelectRecommended = (qa) => {
    setQuery(qa.question);
    if (qa.answer) {
      setAnswer(qa.answer);
      setActiveTab('answer');
    }
  };

  const handleAskQuestion = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError('');
    setAnswer('');
    setRetrievedDocs([]);

    try {
      // Get the streaming response
      const streamResponse = await apiService.askQuestion(query, sessionIdRef.current);
      
      if (!streamResponse.ok) {
        throw new Error(`Error: ${streamResponse.status}`);
      }

      // Read the stream
      const reader = streamResponse.body.getReader();
      const decoder = new TextDecoder();
      let fullAnswer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        fullAnswer += decoder.decode(value, { stream: true });
        setAnswer(fullAnswer);
        
        // Auto-scroll to bottom
        if (answerBoxRef.current) {
          answerBoxRef.current.scrollTop = answerBoxRef.current.scrollHeight;
        }
      }

      // Also retrieve related documents
      const docsResponse = await apiService.retrieveDocuments(query);
      if (docsResponse.documents) {
        setRetrievedDocs(docsResponse.documents);
      }

    } catch (err) {
      setError(err.message || 'Failed to get answer');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setQuery('');
    setAnswer('');
    setRetrievedDocs([]);
    setError('');
  };

  return (
    <div className="query-page">
      <div className="query-header">
        <h1>❓ Ask Your Documents</h1>
        <p>Ask questions about your ingested documents and get AI-powered answers</p>
      </div>

      <div className="query-container">
        <div className="query-input-section">
          {recommendedQA.length > 0 && (
            <div className="recommended-section" style={{ marginBottom: '15px' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 'bold', color: '#94a3b8', marginBottom: '8px' }}>
                💡 Recommended Questions (Tenant Loaded):
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {recommendedQA.map((qa) => (
                  <button
                    key={qa.id}
                    type="button"
                    onClick={() => handleSelectRecommended(qa)}
                    style={{
                      background: 'rgba(99, 102, 241, 0.15)',
                      border: '1px solid rgba(99, 102, 241, 0.3)',
                      color: '#c7d2fe',
                      padding: '6px 12px',
                      borderRadius: '16px',
                      fontSize: '0.85rem',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      textAlign: 'left'
                    }}
                  >
                    ❓ {qa.question}
                  </button>
                ))}
              </div>
            </div>
          )}

          <form onSubmit={handleAskQuestion}>
            <div className="query-input-group">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="What do you want to know? e.g., 'What was the revenue in 2023?'"
                disabled={loading}
                rows={4}
              />
              <div className="query-buttons">
                <button 
                  type="submit" 
                  disabled={loading || !query.trim()}
                  className="btn-primary"
                >
                  {loading ? '🔄 Searching...' : '🚀 Ask Question'}
                </button>
                <button
                  type="button"
                  onClick={handleClear}
                  className="btn-secondary"
                  disabled={loading}
                >
                  🔄 Clear
                </button>
              </div>
            </div>
          </form>

          {error && <div className="error-banner">{error}</div>}
        </div>

        {answer || retrievedDocs.length > 0 ? (
          <div className="results-section">
            <div className="tab-buttons">
              <button
                className={`tab-btn ${activeTab === 'answer' ? 'active' : ''}`}
                onClick={() => setActiveTab('answer')}
              >
                💬 Answer
              </button>
              <button
                className={`tab-btn ${activeTab === 'documents' ? 'active' : ''}`}
                onClick={() => setActiveTab('documents')}
              >
                📄 Source Documents ({retrievedDocs.length})
              </button>
            </div>

            {activeTab === 'answer' && (
              <div className="answer-box" ref={answerBoxRef}>
                {answer ? (
                  <div className="answer-content">
                    {answer}
                  </div>
                ) : (
                  <div className="placeholder">Waiting for answer...</div>
                )}
              </div>
            )}

            {activeTab === 'documents' && (
              <div className="documents-box">
                {retrievedDocs.length > 0 ? (
                  <div className="documents-list">
                    {retrievedDocs.map((doc, idx) => (
                      <div key={idx} className="document-item">
                        <div className="doc-header">
                          <h4>📄 Document {idx + 1}</h4>
                          <div className="doc-scores">
                            <span className="score-badge">
                              Rerank: {(doc.rerank_score * 100).toFixed(1)}%
                            </span>
                            <span className="score-badge">
                              Combined: {(doc.combined_score * 100).toFixed(1)}%
                            </span>
                          </div>
                        </div>
                        <div className="doc-content">
                          {doc.content.substring(0, 500)}...
                        </div>
                        {doc.metadata.source && (
                          <div className="doc-source">
                            📌 Source: {doc.metadata.source}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="placeholder">No documents retrieved</div>
                )}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default QueryPage;
