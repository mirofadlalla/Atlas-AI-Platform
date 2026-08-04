import React, { useState, useRef, useEffect } from 'react';
import apiService from '../services/apiService';
import './AgentPage.css';

const AgentPage = () => {
  const [question, setQuestion] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [thoughts, setThoughts] = useState([]);
  const [currentThought, setCurrentThought] = useState('');
  const [finalAnswer, setFinalAnswer] = useState('');
  const [toolStatus, setToolStatus] = useState(null);
  const [stepCount, setStepCount] = useState(0);
  const [totalCost, setTotalCost] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [recommendedQA, setRecommendedQA] = useState([]);
  const messagesEndRef = useRef(null);

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
    setQuestion(qa.question);
    if (qa.answer) {
      setFinalAnswer(qa.answer);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentThought, finalAnswer, toolStatus]);

  const resetState = () => {
    setThoughts([]);
    setCurrentThought('');
    setFinalAnswer('');
    setToolStatus(null);
    setStepCount(0);
    setTotalCost(0);
    setError('');
  };

  const handleStreamingResponse = async () => {
    if (!question.trim()) {
      setError('Please enter a question');
      return;
    }

    resetState();
    setIsStreaming(true);
    setLoading(true);

    try {
      const user = JSON.parse(localStorage.getItem('user'));
      const tenantId = parseInt(user?.tenant_id, 10);

      if (!tenantId || isNaN(tenantId)) {
        setError('Tenant ID not found or invalid. Please log in again.');
        setLoading(false);
        return;
      }

      const response = await apiService.askAgent(question, tenantId);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              // Helper to safely convert to string
              const toString = (val) => {
                if (typeof val === 'string') return val;
                if (typeof val === 'object' && val !== null && val.content) return val.content;
                if (typeof val === 'object') return JSON.stringify(val);
                return String(val || '');
              };

              switch (data.type) {
                case 'thought':
                  setCurrentThought((prev) => prev + toString(data.content));
                  break;

                case 'tool_start':
                  setToolStatus({
                    status: 'running',
                    tool: data.tool,
                    name: data.name,
                  });
                  break;

                case 'tool_end':
                  setToolStatus({
                    status: 'completed',
                    tool: data.tool,
                  });
                  setTimeout(() => setToolStatus(null), 2000);
                  break;

                case 'answer':
                  if (currentThought && thoughts.length === 0) {
                    setThoughts((prev) => [...prev, currentThought]);
                    setCurrentThought('');
                  }
                  setFinalAnswer((prev) => prev + toString(data.content));
                  break;

                case 'complete':
                  setFinalAnswer(toString(data.final_answer) || finalAnswer);
                  break;

                case 'node_complete':
                  setStepCount((prev) => prev + 1);
                  break;

                case 'done':
                  setStepCount((prev) => prev + 1);
                  break;

                case 'error':
                  setError(`Agent Error: ${data.error}`);
                  break;

                default:
                  console.log('Unknown event type:', data.type);
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }

      // Add final thought to history if not already added
      if (currentThought && thoughts.length === 0) {
        setThoughts((prev) => [...prev, currentThought]);
      }
    } catch (err) {
      setError(`Error: ${err.message}`);
      console.error('Streaming error:', err);
    } finally {
      setIsStreaming(false);
      setLoading(false);
    }
  };

  const handleBatchResponse = async () => {
    if (!question.trim()) {
      setError('Please enter a question');
      return;
    }

    resetState();
    setLoading(true);

    try {
      const user = JSON.parse(localStorage.getItem('user'));
      const tenantId = parseInt(user?.tenant_id, 10);

      if (!tenantId || isNaN(tenantId)) {
        setError('Tenant ID not found or invalid. Please log in again.');
        setLoading(false);
        return;
      }

      const response = await apiService.askAgentBatch(question, tenantId);

      if (response.success) {
        setFinalAnswer(String(response.final_answer || ''));
        setThoughts(Array.isArray(response.thoughts) ? response.thoughts.map(t => String(t)) : []);
        setStepCount(response.step_count || 0);
        setTotalCost(response.total_cost || 0);
      } else {
        setError(`Error: ${response.error || 'Unknown error'}`);
      }
    } catch (err) {
      setError(`Error: ${err.message}`);
      console.error('Batch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (isBatchMode) {
      handleBatchResponse();
    } else {
      handleStreamingResponse();
    }
  };

  return (
    <div className="agent-page">
      <div className="agent-container">
        <div className="agent-header">
          <h1>Agent Query</h1>
          <p className="agent-subtitle">
            Ask questions and get intelligent answers powered by AI agent with SQL and document retrieval
          </p>
        </div>

        <div className="agent-mode-toggle">
          <label>
            <input
              type="checkbox"
              checked={isBatchMode}
              onChange={(e) => setIsBatchMode(e.target.checked)}
              disabled={loading}
            />
            Batch Mode (Get full response at once)
          </label>
          {isBatchMode && (
            <span className="mode-badge">Batch</span>
          )}
        </div>

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

        <form onSubmit={handleSubmit} className="agent-form">
          <div className="form-group">
            <label htmlFor="question">Your Question</label>
            <textarea
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask me anything about your data..."
              rows="4"
              disabled={loading}
              className="question-textarea"
            />
          </div>

          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="submit-button"
          >
            {loading ? 'Processing...' : isBatchMode ? 'Get Answer' : 'Start Streaming'}
          </button>
        </form>

        {error && (
          <div className="error-message">
            <strong>Error:</strong> {error}
            <button onClick={() => setError('')} className="close-error">×</button>
          </div>
        )}

        <div className="agent-output">
          {/* Current Status */}
          {(isStreaming || loading) && (
            <div className="status-section">
              <h3>Status</h3>
              <div className="status-info">
                <div className="status-item">
                  <span className="label">Step Count:</span>
                  <span className="value">{stepCount}</span>
                </div>
                {toolStatus && (
                  <div className="tool-status">
                    <span className={`status-badge ${toolStatus.status}`}>
                      {toolStatus.status === 'running' ? '⚙️ Running' : '✓ Completed'}
                    </span>
                    <span className="tool-name">{toolStatus.tool}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Thoughts/Reasoning */}
          {(currentThought || thoughts.length > 0) && (
            <div className="thoughts-section">
              <h3>Agent Reasoning</h3>
              <div className="thoughts-container">
                {thoughts.map((thought, idx) => (
                  <div key={idx} className="thought-item">
                    <span className="thought-label">Thought {idx + 1}:</span>
                    <p className="thought-content">{thought}</p>
                  </div>
                ))}
                {currentThought && (
                  <div className="thought-item current">
                    <span className="thought-label">Current Thought:</span>
                    <p className="thought-content">{currentThought}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Final Answer */}
          {finalAnswer && (
            <div className="answer-section">
              <h3>Answer</h3>
              <div className="answer-content">
                <p>{finalAnswer}</p>
              </div>
              {stepCount > 0 && (
                <div className="answer-metadata">
                  <span>Steps: {stepCount}</span>
                  {totalCost > 0 && <span>Cost: ${totalCost.toFixed(4)}</span>}
                </div>
              )}
            </div>
          )}

          {!loading && !finalAnswer && !error && (
            <div className="empty-state">
              <p>Ask a question to get started</p>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>
    </div>
  );
};

export default AgentPage;
