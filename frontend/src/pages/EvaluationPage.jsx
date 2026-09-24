import React, { useState } from 'react';
import apiService from '../services/apiService';
import './EvaluationPage.css';

function EvaluationPage({ user }) {
  const [file, setFile] = useState(null);
  const [runs, setRuns] = useState(2);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  // Generation state
  const [generateMaxChunks, setGenerateMaxChunks] = useState(30);
  const [generateLoading, setGenerateLoading] = useState(false);
  const [generateTaskId, setGenerateTaskId] = useState('');
  const [generateStatus, setGenerateStatus] = useState('');
  const [generateError, setGenerateError] = useState('');

  // Status check state
  const [statusTaskId, setStatusTaskId] = useState('');
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusResult, setStatusResult] = useState(null);
  const [statusError, setStatusError] = useState('');

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleStartEvaluation = async (e) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a file');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await apiService.startEvaluation(file, runs);
      setTaskId(response.task_id);
      setStatus(`✅ Evaluation started! Task ID: ${response.task_id}`);
      setFile(null);
    } catch (err) {
      setError(err.message || 'Failed to start evaluation');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateDataset = async (e) => {
    e.preventDefault();
    setGenerateLoading(true);
    setGenerateError('');
    setGenerateStatus('');
    setGenerateTaskId('');

    try {
      const response = await apiService.generateEvalDataset(generateMaxChunks);
      setGenerateTaskId(response.task_id);
      setGenerateStatus(`✅ Generation started! Task ID: ${response.task_id}`);
    } catch (err) {
      setGenerateError(err.message || 'Failed to start generation');
    } finally {
      setGenerateLoading(false);
    }
  };

  const handleCheckStatus = async (e) => {
    e.preventDefault();
    if (!statusTaskId) return;

    setStatusLoading(true);
    setStatusError('');
    setStatusResult(null);

    try {
      const response = await apiService.getEvaluationStatus(statusTaskId);
      setStatusResult(response);
    } catch (err) {
      setStatusError(err.message || 'Failed to get status');
    } finally {
      setStatusLoading(false);
    }
  };

  return (
    <div className="evaluation-page">
      <div className="evaluation-header">
        <h1>📊 Evaluate RAG Pipeline</h1>
        <p>Generate datasets, evaluate pipelines, and track background tasks</p>
      </div>

      <div className="evaluation-container">
        {/* Generate Dataset Form */}
        <form onSubmit={handleGenerateDataset} className="evaluation-form">
          <h3>1. Auto-Generate Evaluation Dataset</h3>
          <div className="form-group">
            <label htmlFor="maxChunks">Max Document Chunks</label>
            <input
              type="number"
              id="maxChunks"
              value={generateMaxChunks}
              onChange={(e) => setGenerateMaxChunks(parseInt(e.target.value))}
              min="1"
              max="500"
            />
            <small>Number of chunks to fetch for generation.</small>
          </div>

          <button type="submit" disabled={generateLoading} className="btn-primary">
            {generateLoading ? '⏳ Starting...' : '🏭 Generate Dataset'}
          </button>
        </form>
        {generateStatus && <div className="success-message">{generateStatus}</div>}
        {generateError && <div className="error-message">{generateError}</div>}
        {generateTaskId && (
          <div className="task-info">
            <p>Task ID: <code>{generateTaskId}</code></p>
            <p>Copy this Task ID to check its status below.</p>
          </div>
        )}

        {/* Evaluation Form */}
        <form onSubmit={handleStartEvaluation} className="evaluation-form">
          <h3>2. Run Pipeline Evaluation</h3>
          <div className="form-group">
            <label htmlFor="evalFile">Evaluation Dataset (JSON)</label>
            <input
              type="file"
              id="evalFile"
              onChange={handleFileChange}
              accept=".json"
              required
            />
            <small>Upload a JSON file with evaluation questions and ground truth</small>
          </div>

          <div className="form-group">
            <label htmlFor="runs">Number of Evaluation Runs</label>
            <input
              type="number"
              id="runs"
              value={runs}
              onChange={(e) => setRuns(parseInt(e.target.value))}
              min="1"
              max="10"
            />
          </div>

          <button type="submit" disabled={loading || !file} className="btn-primary">
            {loading ? '⏳ Starting...' : '▶️ Start Evaluation'}
          </button>
        </form>

        {status && <div className="success-message">{status}</div>}
        {error && <div className="error-message">{error}</div>}

        {taskId && (
          <div className="task-info">
            <p>Task ID: <code>{taskId}</code></p>
            <p>Copy this Task ID to check its status below, or check MLflow for results.</p>
          </div>
        )}

        {/* Check Task Status Form */}
        <form onSubmit={handleCheckStatus} className="evaluation-form">
          <h3>3. Check Task Status</h3>
          <div className="form-group">
             <label htmlFor="statusTaskId">Task ID</label>
             <input
               type="text"
               id="statusTaskId"
               value={statusTaskId}
               onChange={(e) => setStatusTaskId(e.target.value)}
               placeholder="Enter Celery Task ID"
               required
             />
          </div>
          <button type="submit" disabled={statusLoading || !statusTaskId} className="btn-primary">
            {statusLoading ? '⏳ Checking...' : '🔍 Check Status'}
          </button>
        </form>

        {statusError && <div className="error-message">{statusError}</div>}
        {statusResult && (
          <div className="task-info status-result">
            <h3>Status: {statusResult.status}</h3>
            {statusResult.result && (
              <div className="result-details">
                <pre>{JSON.stringify(statusResult.result, null, 2)}</pre>
              </div>
            )}
            {!statusResult.result && <p>Result: Pending or Not Available</p>}
          </div>
        )}

        <div className="evaluation-metrics">
          <h3>📈 Metrics Evaluated</h3>
          <ul>
            <li>Precision@K - Fraction of retrieved documents that are relevant</li>
            <li>Recall@K - Fraction of relevant documents that were retrieved</li>
            <li>F1 Score - Harmonic mean of precision and recall</li>
            <li>MRR - How early the first relevant result appears</li>
            <li>Jaccard Stability - Consistency across repeated queries</li>
            <li>Token F1 - Keyword overlap with ground truth answers</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default EvaluationPage;
