import React, { useState, useEffect } from 'react';
import apiService from '../services/apiService';
import './CostAnalyticsPage.css';

function CostAnalyticsPage({ user }) {
  const [costs, setCosts] = useState(null);
  const [runs, setRuns] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    loadAnalytics();
  }, []);

  const loadAnalytics = async () => {
    setLoading(true);
    setError('');
    try {
      const [costsData, runsData] = await Promise.all([
        apiService.getCostAnalytics(),
        apiService.getRuns()
      ]);
      setCosts(costsData);
      setRuns(runsData);
    } catch (err) {
      setError(err.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <main className="analytics-page">
        <div className="analytics-loading" role="status">
          <span>Loading analytics…</span>
        </div>
      </main>
    );
  }

  return (
    <main className="analytics-page">
      <div className="analytics-header">
        <h1>Cost Analytics &amp; Usage</h1>
        <p>Monitor spending and usage trends</p>
        <button onClick={loadAnalytics} className="btn-refresh" aria-label="Refresh analytics">↻ Refresh</button>
      </div>

      {error && <div className="analytics-page error-message" role="alert">{error}</div>}

      <div className="analytics-container">
        {costs && (
          <>
            {/* Cost Summary */}
            <div className="analytics-section">
              <h2>📊 Cost Summary</h2>
              <div className="metric-cards">
                <div className="metric-card">
                  <div className="metric-label">Total Cost</div>
                  <div className="metric-value">${(costs.total_cost || 0).toFixed(2)}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Average Query Cost</div>
                  <div className="metric-value">${(costs.average_cost || 0).toFixed(4)}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Total Input Tokens</div>
                  <div className="metric-value">{(costs.total_input_tokens || 0).toLocaleString()}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Total Output Tokens</div>
                  <div className="metric-value">{(costs.total_output_tokens || 0).toLocaleString()}</div>
                </div>
              </div>
            </div>

            {/* Cost Breakdown by Model */}
            <div className="analytics-section">
              <h2>🤖 Cost by Model</h2>
              <div className="model-costs">
                {costs.by_model ? (
                  Object.entries(costs.by_model).map(([model, data]) => (
                    <div key={model} className="model-cost-row">
                      <div className="model-name">{model}</div>
                      <div className="cost-breakdown">
                        <span className="cost-value">${(data.total || 0).toFixed(2)}</span>
                        <span className="token-info">
                          ({data.input_tokens || 0}↓ / {data.output_tokens || 0}↑)
                        </span>
                      </div>
                    </div>
                  ))
                ) : (
                  <p>No model cost data available</p>
                )}
              </div>
            </div>

            {/* Usage Trends */}
            {runs && (
              <div className="analytics-section">
                <h2>📈 Usage Metrics</h2>
                <div className="usage-metrics">
                  <div className="metric-row">
                    <span>Total Queries</span>
                    <strong>{runs.total_runs || 0}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Average Latency</span>
                    <strong>{((runs.average_latency || 0) / 1000).toFixed(2)}s</strong>
                  </div>
                  <div className="metric-row">
                    <span>Cache Hit Rate</span>
                    <strong>{((runs.cache_hit_rate || 0) * 100).toFixed(1)}%</strong>
                  </div>
                  <div className="metric-row">
                    <span>Cost per Query</span>
                    <strong>${((costs.total_cost || 0) / (runs.total_runs || 1)).toFixed(4)}</strong>
                  </div>
                </div>
              </div>
            )}

            {/* Optimization Tips */}
            <div className="analytics-section tips">
              <h2>💡 Optimization Tips</h2>
              <ul>
                <li>Increase cache hit rate by reusing similar queries</li>
                <li>Use ReRANK strategy for faster, cheaper initial retrieval</li>
                <li>Monitor token usage and optimize prompt engineering</li>
                <li>Consider batch processing for bulk evaluations</li>
                <li>Review low-confidence results for query optimization</li>
              </ul>
            </div>
          </>
        )}
      </div>

      <div className="analytics-footer">
        <small>For detailed cost breakdowns and charts, visit the MLflow dashboard</small>
      </div>
    </main>
  );
}

export default CostAnalyticsPage;
