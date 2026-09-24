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
  const sessionIdRef = useRef(sessionStorage.getItem('atlas-agent-session-id'));

  if (!sessionIdRef.current) {
    sessionIdRef.current = crypto.randomUUID();
    sessionStorage.setItem('atlas-agent-session-id', sessionIdRef.current);
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
    setQuestion(qa.question);
    if (qa.answer) {
      setFinalAnswer(qa.answer);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    // Skip the very first run: on mount there's nothing to show yet, and
    // scrolling to an empty output area pulls the whole page (nav included)
    // out of view before the user has asked anything.
    if (!currentThought && !finalAnswer && !toolStatus) return;
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
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      const tenantId = user?.tenant_id;

      const response = await apiService.askAgent(question, tenantId, sessionIdRef.current);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      // State setters are asynchronous, so values captured by this streaming
      // function become stale while answer chunks arrive. Keep the current
      // request's aggregates locally to avoid adding the same thought once for
      // every answer chunk.
      let streamedThought = '';
      let streamedAnswer = '';
      let thoughtCommitted = false;

      // Helper declared outside the loop to prevent ESLint no-loop-func closure warning
      const commitThought = (thought) => {
        setThoughts((prev) => [...prev, thought]);
        setCurrentThought('');
      };

      // Helper to safely convert SSE payload to string, declared outside loop
      const toString = (val) => {
        if (typeof val === 'string') return val;
        if (typeof val === 'object' && val !== null && val.content) return val.content;
        if (typeof val === 'object') return JSON.stringify(val);
        return String(val || '');
      };

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

              switch (data.type) {
                case 'thought':
                  streamedThought += toString(data.content);
                  setCurrentThought(streamedThought);
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
                  if (streamedThought && !thoughtCommitted) {
                    commitThought(streamedThought);
                    thoughtCommitted = true;
                  }
                  streamedAnswer += toString(data.content);
                  setFinalAnswer(streamedAnswer);
                  break;

                case 'complete':
                  streamedAnswer = toString(data.final_answer) || streamedAnswer;
                  setFinalAnswer(streamedAnswer);
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
      if (streamedThought && !thoughtCommitted) {
        commitThought(streamedThought);
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
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      const tenantId = user?.tenant_id;

      const response = await apiService.askAgentBatch(question, tenantId, sessionIdRef.current);

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

  const handleClearMemory = async () => {
    try {
      await apiService.clearMemory();
      sessionIdRef.current = crypto.randomUUID();
      sessionStorage.setItem('atlas-agent-session-id', sessionIdRef.current);
      resetState();
    } catch (err) {
      setError(`Failed to clear memory: ${err.message}`);
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
    <main className="agent-page">
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
              aria-label="Batch mode: get the full response at once instead of streaming"
            />
            Batch Mode (Get full response at once)
          </label>
          {isBatchMode && (
            <span className="mode-badge">Batch</span>
          )}
        </div>

        {recommendedQA.length > 0 && (
          <div className="recommended-section">
            <p className="recommended-label">Suggested Questions</p>
            <div className="recommended-buttons">
              {recommendedQA.map((qa) => (
                <button
                  key={qa.id}
                  type="button"
                  onClick={() => handleSelectRecommended(qa)}
                  className="recommended-btn"
                >
                  {qa.question}
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
              aria-label="Your question for the AI agent"
            />
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="submit-button"
            >
              {loading ? 'Processing…' : isBatchMode ? 'Get Answer' : 'Start Streaming'}
            </button>
            <button
              type="button"
              onClick={handleClearMemory}
              disabled={loading}
              className="submit-button"
              style={{ background: 'var(--surface-color, #374151)' }}
              title="Clear conversation memory for your user account"
            >
              🧹 Clear Memory
            </button>
          </div>
        </form>

        {error && (
          <div className="error-message" role="alert" aria-live="assertive">
            <strong>Error:</strong> {error}
            <button
              onClick={() => setError('')}
              className="close-error"
              aria-label="Close error message"
            >
              ×
            </button>
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
    </main>
  );
};

export default AgentPage;
