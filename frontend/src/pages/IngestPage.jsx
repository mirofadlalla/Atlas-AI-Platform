import React, { useState } from 'react';
import apiService from '../services/apiService';
import './IngestPage.css';

function IngestPage({ user }) {
  const [file, setFile] = useState(null);
  const [source, setSource] = useState('');
  const [author, setAuthor] = useState(user?.email || '');
  const [recursive, setRecursive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [taskId, setTaskId] = useState('');
  const [chunkSuggestion, setChunkSuggestion] = useState('');

  // Status check state
  const [statusTaskId, setStatusTaskId] = useState('');
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusResult, setStatusResult] = useState(null);
  const [statusError, setStatusError] = useState('');

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setChunkSuggestion('');
  };

  const suggestChunking = () => {
    if (!file) return;
    const extension = file.name.split('.').pop().toLowerCase();
    const structured = ['csv', 'xlsx', 'xls', 'json'];
    setChunkSuggestion(structured.includes(extension)
      ? 'Suggested: structured chunks. Headers are preserved and rows/records stay together with overlap.'
      : 'Suggested: semantic chunks. Atlas will use embeddings to split unstructured prose by meaning.');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!file) {
      setError('Please select a file');
      return;
    }
    
    if (!source) {
      setError('Please enter a source name');
      return;
    }

    setLoading(true);
    setError('');
    setStatus('');

    try {
      const res = await apiService.uploadFile(file, source, author, recursive);
      setTaskId(res.task_id);
      setStatus(`✅ File ingestion started! Task ID: ${res.task_id}`);
      setFile(null);
      setSource('');
    } catch (err) {
      setError(err.message || 'Failed to ingest file');
    } finally {
      setLoading(false);
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
    <div className="ingest-page">
      <div className="ingest-header">
        <h1>📤 Ingest Documents</h1>
        <p>Upload files to your knowledge base and track progress</p>
      </div>

      <div className="ingest-container">
        <form onSubmit={handleSubmit} className="ingest-form">
          <div className="form-group">
            <label htmlFor="docFile">Document File (PDF, TXT, MD)</label>
            <input
              type="file"
              id="docFile"
              onChange={handleFileChange}
              accept=".pdf,.txt,.md,.csv,.json"
              required
            />
            <small>Select a document to upload and process</small>
            <button type="button" className="btn-primary" disabled={!file} onClick={suggestChunking} style={{ marginTop: '10px' }}>
              Suggest chunking strategy
            </button>
            {chunkSuggestion && <small style={{ display: 'block', marginTop: '8px' }}>{chunkSuggestion}</small>}
            {file && <div className="file-selected">✅ Selected: {file.name}</div>}
          </div>

          <div className="form-group">
            <label htmlFor="source">Source Name</label>
            <input
              type="text"
              id="source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="Annual Report 2023"
              required
            />
            <small>Descriptive name for tracking</small>
          </div>

          <div className="form-group">
            <label htmlFor="author">Author</label>
            <input
              type="text"
              id="author"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Your name"
            />
          </div>

          <div className="form-group checkbox">
            <input
              type="checkbox"
              id="recursive"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
            />
            <label htmlFor="recursive">Process subdirectories recursively</label>
          </div>

          <button type="submit" disabled={loading || !file} className="btn-primary">
            {loading ? '⏳ Ingesting...' : '📤 Ingest File'}
          </button>
        </form>

        {status && <div className="success-message">{status}</div>}
        {error && <div className="error-message">{error}</div>}

        {taskId && (
          <div className="task-info" style={{background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', padding: '20px', borderRadius: 'var(--radius-xl)', marginBottom: '30px'}}>
            <p>Task ID: <code>{taskId}</code></p>
            <p>Copy this Task ID to check its status below.</p>
          </div>
        )}

        {/* Check Task Status Form */}
        <form onSubmit={handleCheckStatus} className="ingest-form" style={{marginTop: '20px'}}>
          <h3>🔍 Check Ingestion Status</h3>
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
          <div className="task-info" style={{background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', padding: '20px', borderRadius: 'var(--radius-xl)', marginBottom: '30px', marginTop: '20px'}}>
            <h3>Status: {statusResult.status}</h3>
            {statusResult.result && (
              <div className="result-details">
                <pre>{JSON.stringify(statusResult.result, null, 2)}</pre>
              </div>
            )}
            {!statusResult.result && <p>Result: Pending or Not Available</p>}
          </div>
        )}

        <div className="ingest-info">
          <h3>ℹ️ Information</h3>
          <ul>
            <li>Supported formats: PDF, TXT, MD</li>
            <li>Files are automatically chunked and embedded</li>
            <li>Duplicate files are skipped to save computation</li>
            <li>Documents are isolated per-tenant</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default IngestPage;
