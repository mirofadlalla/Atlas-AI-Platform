import React, { useEffect, useState } from 'react';
import apiService from '../services/apiService';
import Modal from '../components/Modal';
import { useToast } from '../components/Toast';
import './AdminPanel.css';

const INITIAL_FORM = {
  database_type: 'postgresql',
  host: '',
  port: 5432,
  database_name: '',
  username: '',
  password: '',
  default_schema: 'public',
  ssl_enabled: true,
  ssl_mode: 'require',
  connection_timeout: 10,
};

export default function TenantDatabasePage() {
  const toast = useToast();
  const [form, setForm] = useState(INITIAL_FORM);
  const [status, setStatus] = useState(null);
  const [schema, setSchema] = useState(null);
  const [busy, setBusy] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);

  const loadStatus = async () => {
    try {
      setStatus(await apiService.getTenantDatabaseStatus());
    } catch {
      setStatus({ connected: false });
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleFieldChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      await apiService.connectTenantDatabase({
        ...form,
        port: Number(form.port),
        connection_timeout: Number(form.connection_timeout),
      });
      setForm((prev) => ({ ...prev, password: '' }));
      await loadStatus();
      toast.success('Database connected successfully!');
    } catch (error) {
      toast.error(error.message || 'Connection failed');
    } finally {
      setBusy(false);
    }
  };

  const handleTest = async () => {
    setBusy(true);
    try {
      const result = await apiService.testTenantDatabase();
      toast.success(result?.message || 'Connection test passed!');
    } catch (error) {
      toast.error(error.message || 'Database test failed');
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshSchema = async () => {
    setBusy(true);
    try {
      const result = await apiService.getTenantDatabaseSchema(true);
      setSchema(result);
      toast.success('Schema refreshed.');
    } catch (error) {
      toast.error(error.message || 'Failed to refresh schema');
    } finally {
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    setBusy(true);
    try {
      await apiService.disconnectTenantDatabase();
      setSchema(null);
      await loadStatus();
      toast.success('Database disconnected.');
    } catch (error) {
      toast.error(error.message || 'Disconnect failed');
    } finally {
      setBusy(false);
    }
  };

  const isConnected = status?.connected === true;

  return (
    <main className="admin-panel">
      {/* Disconnect confirmation modal */}
      <Modal
        isOpen={disconnectOpen}
        onClose={() => setDisconnectOpen(false)}
        title="Disconnect Database"
        confirmText="Disconnect"
        confirmVariant="danger"
        onConfirm={handleDisconnect}
        cancelText="Cancel"
      >
        <p>
          Are you sure you want to disconnect this database? Agent SQL queries will stop working
          until you reconnect.
        </p>
      </Modal>

      <div className="admin-header">
        <h1>Tenant Database</h1>
        <p>Admin-only external SQL connection for agent queries.</p>
      </div>

      <div className="admin-container">
        <div className="tab-content">
          {/* ===== STATUS BAR ===== */}
          <section aria-label="Connection status" style={{ marginBottom: '24px' }}>
            <h3 style={{ margin: '0 0 12px 0', color: 'var(--text-primary)' }}>Connection Status</h3>
            {status ? (
              <div
                className={`status-badge ${isConnected ? 'status-accepted' : 'status-rejected'}`}
                style={{ fontSize: 'var(--text-sm)', padding: '6px 16px' }}
              >
                {isConnected ? '● Connected' : '○ Not connected'}
                {isConnected && status.host ? ` — ${status.host}` : ''}
              </div>
            ) : (
              <span className="status-badge status-pending">Checking…</span>
            )}
          </section>

          {/* ===== CONNECTION FORM ===== */}
          <div className="send-invitation-form">
            <h3>Configure Database Connection</h3>
            <form onSubmit={handleSubmit} noValidate>
              <div className="form-group">
                <label htmlFor="db-type">Database Type</label>
                <select
                  id="db-type"
                  name="database_type"
                  value={form.database_type}
                  onChange={handleFieldChange}
                >
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mysql">MySQL</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="db-host">Host</label>
                <input
                  id="db-host"
                  name="host"
                  required
                  value={form.host}
                  onChange={handleFieldChange}
                  placeholder="e.g. db.example.com or localhost"
                  autoComplete="off"
                />
              </div>

              <div className="form-group">
                <label htmlFor="db-port">Port</label>
                <input
                  id="db-port"
                  name="port"
                  type="number"
                  value={form.port}
                  onChange={handleFieldChange}
                  min={1}
                  max={65535}
                />
              </div>

              <div className="form-group">
                <label htmlFor="db-name">Database Name</label>
                <input
                  id="db-name"
                  name="database_name"
                  required
                  value={form.database_name}
                  onChange={handleFieldChange}
                  placeholder="e.g. mydb"
                  autoComplete="off"
                />
              </div>

              <div className="form-group">
                <label htmlFor="db-user">Username</label>
                <input
                  id="db-user"
                  name="username"
                  required
                  value={form.username}
                  onChange={handleFieldChange}
                  placeholder="e.g. readonly_user"
                  autoComplete="username"
                />
              </div>

              <div className="form-group">
                <label htmlFor="db-pass">Password</label>
                <input
                  id="db-pass"
                  name="password"
                  required
                  type="password"
                  value={form.password}
                  onChange={handleFieldChange}
                  autoComplete="new-password"
                  placeholder="Database password"
                />
              </div>

              <div className="form-group">
                <label htmlFor="db-schema">Default Schema</label>
                <input
                  id="db-schema"
                  name="default_schema"
                  value={form.default_schema}
                  onChange={handleFieldChange}
                  placeholder="public"
                />
              </div>

              <div className="form-group">
                <label htmlFor="db-timeout">Connection Timeout (seconds)</label>
                <input
                  id="db-timeout"
                  name="connection_timeout"
                  type="number"
                  value={form.connection_timeout}
                  onChange={handleFieldChange}
                  min={1}
                  max={60}
                />
              </div>

              <button className="btn-primary" disabled={busy} type="submit">
                {busy ? 'Working…' : isConnected ? 'Update Connection' : 'Connect Database'}
              </button>
            </form>
          </div>

          {/* ===== ACTIONS ===== */}
          {isConnected && (
            <div className="invitations-list">
              <h3>Database Actions</h3>
              <div className="item-actions" style={{ flexWrap: 'wrap', gap: '12px', marginBottom: '24px' }}>
                <button
                  className="btn-primary"
                  disabled={busy}
                  onClick={handleTest}
                  aria-label="Test the database connection"
                >
                  Test Connection
                </button>
                <button
                  className="btn-primary"
                  disabled={busy}
                  onClick={handleRefreshSchema}
                  aria-label="Refresh database schema"
                >
                  Refresh Schema
                </button>
                <button
                  className="btn-danger"
                  disabled={busy}
                  onClick={() => setDisconnectOpen(true)}
                  aria-label="Disconnect from the database"
                >
                  Disconnect
                </button>
              </div>

              {/* Schema display */}
              {schema && (
                <section aria-label="Database schema">
                  {schema.relationships?.length > 0 && (
                    <>
                      <h4 style={{ color: 'var(--text-primary)', margin: '0 0 12px 0' }}>
                        Table Relationships
                      </h4>
                      <ul style={{ paddingLeft: '20px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                        {schema.relationships.map((r, i) => (
                          <li key={i}>
                            <code className="token-value">
                              {r.from_table}.{r.from_columns.join(', ')}
                            </code>
                            {' → '}
                            <code className="token-value">
                              {r.to_table}.{r.to_columns.join(', ')}
                            </code>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                  <h4 style={{ color: 'var(--text-primary)', margin: '0 0 8px 0' }}>
                    Full Schema (JSON)
                  </h4>
                  <pre className="result-details" style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '16px',
                    overflowX: 'auto',
                    color: 'var(--text-secondary)',
                    fontSize: 'var(--text-sm)',
                  }}>
                    {JSON.stringify(schema, null, 2)}
                  </pre>
                </section>
              )}
            </div>
          )}

          {/* Raw status (always visible for debugging) */}
          {status && (
            <details style={{ marginTop: '24px' }}>
              <summary style={{ color: 'var(--text-muted)', cursor: 'pointer', fontSize: 'var(--text-sm)' }}>
                Raw status JSON
              </summary>
              <pre style={{
                background: 'var(--bg-elevated)',
                padding: '12px',
                borderRadius: 'var(--radius-lg)',
                color: 'var(--text-secondary)',
                fontSize: 'var(--text-xs)',
                marginTop: '8px',
                overflowX: 'auto',
              }}>
                {JSON.stringify(status, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </div>
    </main>
  );
}
