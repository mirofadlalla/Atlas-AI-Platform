import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import apiService from '../services/apiService';
import Spinner from '../components/Spinner';
import EmptyState from '../components/EmptyState';
import TenantEditModal from '../components/TenantEditModal';
import TenantDeleteModal from '../components/TenantDeleteModal';
import TenantApproveModal from '../components/TenantApproveModal';
import TenantRejectModal from '../components/TenantRejectModal';
import { useToast } from '../components/Toast';
import './SuperAdminDashboardPage.css';

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
}

function SuperAdminDashboardPage({ user }) {
  const toast = useToast();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Modals for tenant actions
  const [editModal, setEditModal] = useState({ isOpen: false, tenant: null });
  const [deleteModal, setDeleteModal] = useState({ isOpen: false, tenant: null });
  const [approveModal, setApproveModal] = useState({ isOpen: false, tenant: null });
  const [rejectModal, setRejectModal] = useState({ isOpen: false, tenant: null });

  const loadStats = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiService.getSuperAdminStats();
      setStats(data);
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to load Super Admin dashboard stats.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const handleApproveConfirm = async (tenantId, note) => {
    try {
      await apiService.approveSuperAdminTenant(tenantId, note);
      toast.success('Organization workspace approved and activated successfully!');
      loadStats();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to approve tenant.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleRejectConfirm = async (tenantId, reason) => {
    try {
      await apiService.rejectSuperAdminTenant(tenantId, reason);
      toast.success('Organization registration declined.');
      loadStats();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to reject tenant.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleEditSave = async (tenantId, payload) => {
    try {
      await apiService.updateSuperAdminTenant(tenantId, payload);
      toast.success('Tenant updated successfully!');
      loadStats();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update tenant.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleDeleteConfirm = async (tenantId) => {
    try {
      await apiService.deleteSuperAdminTenant(tenantId);
      toast.success('Tenant and all associated users deleted successfully!');
      loadStats();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to delete tenant.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const tenants = stats?.tenants || [];
  const recentTenants = tenants.slice(0, 5);

  return (
    <main className="super-admin-page">
      <div className="super-admin-header">
        <div className="super-admin-header-title">
          <div className="super-admin-tag">
            <span className="sparkle-icon" aria-hidden="true">⚡</span> Super Admin Portal
          </div>
          <h1>Platform Overview</h1>
          <p>Global multi-tenant governance, organization controls, and user directory</p>
        </div>
        <div className="super-admin-header-actions">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={loadStats}
            disabled={loading}
            title="Refresh statistics"
          >
            {loading ? <Spinner size="sm" /> : '↻ Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <div className="error-content">
            <span className="error-icon">⚠️</span>
            <span>{error}</span>
          </div>
          <button type="button" className="btn-secondary btn-sm" onClick={loadStats}>
            Retry
          </button>
        </div>
      )}

      {loading && !stats ? (
        <div className="super-admin-loading">
          <Spinner size="lg" label="Loading dashboard metrics…" />
          <p>Aggregating platform statistics…</p>
        </div>
      ) : (
        <>
          {/* Pending Approvals Notice Banner if any */}
          {stats?.pending_tenants > 0 && (
            <div
              style={{
                background: 'rgba(245, 158, 11, 0.15)',
                border: '1px solid rgba(245, 158, 11, 0.5)',
                borderRadius: 'var(--radius-xl)',
                padding: '16px 20px',
                marginBottom: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '1.5rem' }}>⏳</span>
                <div>
                  <strong style={{ color: 'var(--text-warning, #f59e0b)', fontSize: '1rem' }}>
                    {stats.pending_tenants} Organization{stats.pending_tenants === 1 ? '' : 's'} Awaiting Approval
                  </strong>
                  <p style={{ margin: '2px 0 0 0', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                    New registrations are blocked from member login until you approve them.
                  </p>
                </div>
              </div>
              <Link
                to="/super-admin/tenants?status=pending"
                className="btn-primary btn-sm"
                style={{
                  background: 'var(--color-warning, #f59e0b)',
                  borderColor: 'var(--color-warning, #f59e0b)',
                  color: '#000',
                  fontWeight: 'bold',
                }}
              >
                Review Pending ({stats.pending_tenants})
              </Link>
            </div>
          )}

          {/* Key Metric Cards */}
          <div className="super-admin-stats-grid">
            <div className="stat-overview-card">
              <div className="stat-card-top">
                <span className="stat-card-title">Total Organizations</span>
                <span className="stat-card-icon" aria-hidden="true">🏢</span>
              </div>
              <div className="stat-card-value">{stats?.total_tenants ?? 0}</div>
              <div className="stat-card-meta">
                <span>Registered platform tenants</span>
              </div>
            </div>

            <div
              className="stat-overview-card"
              style={
                stats?.pending_tenants > 0
                  ? { borderColor: 'rgba(245, 158, 11, 0.6)', background: 'rgba(245, 158, 11, 0.05)' }
                  : {}
              }
            >
              <div className="stat-card-top">
                <span className="stat-card-title">Pending Approvals</span>
                <span className="stat-card-icon" aria-hidden="true">⏳</span>
              </div>
              <div
                className="stat-card-value"
                style={stats?.pending_tenants > 0 ? { color: '#f59e0b' } : {}}
              >
                {stats?.pending_tenants ?? 0}
              </div>
              <div className="stat-card-meta">
                <span>Awaiting Super Admin review</span>
              </div>
            </div>

            <div className="stat-overview-card">
              <div className="stat-card-top">
                <span className="stat-card-title">Total Users</span>
                <span className="stat-card-icon" aria-hidden="true">👥</span>
              </div>
              <div className="stat-card-value">{stats?.total_users ?? 0}</div>
              <div className="stat-card-meta">
                <span>Across all organizations</span>
              </div>
            </div>

            <div className="stat-overview-card">
              <div className="stat-card-top">
                <span className="stat-card-title">Avg Users / Tenant</span>
                <span className="stat-card-icon" aria-hidden="true">📊</span>
              </div>
              <div className="stat-card-value">
                {stats?.total_tenants && stats?.total_tenants > 0
                  ? (stats.total_users / stats.total_tenants).toFixed(1)
                  : '0.0'}
              </div>
              <div className="stat-card-meta">
                <span>Tenant density ratio</span>
              </div>
            </div>

            <div className="stat-overview-card">
              <div className="stat-card-top">
                <span className="stat-card-title">Role Privileges</span>
                <span className="stat-card-icon" aria-hidden="true">🛡️</span>
              </div>
              <div className="stat-card-value stat-value-highlight">Full Access</div>
              <div className="stat-card-meta">
                <span>Super Admin (Global Scope)</span>
              </div>
            </div>
          </div>

          {/* Quick Navigation Cards */}
          <div className="super-admin-quick-links">
            <Link to="/super-admin/tenants" className="quick-link-card">
              <div className="quick-link-icon">🏢</div>
              <div className="quick-link-content">
                <h3>Manage Tenants</h3>
                <p>View all {stats?.total_tenants ?? 0} tenants, approve pending registrations, or manage plans</p>
              </div>
              <span className="quick-link-arrow">→</span>
            </Link>

            <Link to="/super-admin/users" className="quick-link-card">
              <div className="quick-link-icon">👥</div>
              <div className="quick-link-content">
                <h3>Global User Management</h3>
                <p>View all platform users, promote/demote roles, and adjust approval status</p>
              </div>
              <span className="quick-link-arrow">→</span>
            </Link>
          </div>

          {/* Recent Tenants Section */}
          <div className="super-admin-section">
            <div className="section-header">
              <div>
                <h2>Tenant Directory Overview</h2>
                <p className="section-subtitle">
                  Showing {recentTenants.length} of {tenants.length} registered tenants
                </p>
              </div>
              {tenants.length > 5 && (
                <Link to="/super-admin/tenants" className="btn-secondary btn-sm">
                  View All ({tenants.length})
                </Link>
              )}
            </div>

            {tenants.length === 0 ? (
              <EmptyState
                icon="🏢"
                title="No tenants registered yet"
                description="When organizations register on the platform, they will appear here."
              />
            ) : (
              <div className="table-responsive">
                <table className="super-admin-table">
                  <thead>
                    <tr>
                      <th scope="col">Tenant Name</th>
                      <th scope="col">Status</th>
                      <th scope="col">Plan</th>
                      <th scope="col">Users</th>
                      <th scope="col">Created Date</th>
                      <th scope="col" className="text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentTenants.map((tenant) => {
                      const isPending = tenant.status === 'pending';
                      return (
                        <tr key={tenant.id} style={isPending ? { background: 'rgba(245, 158, 11, 0.05)' } : {}}>
                          <td className="tenant-name-col">
                            <Link
                              to={`/super-admin/tenants/${tenant.id}`}
                              className="tenant-link"
                            >
                              <strong>{tenant.name}</strong>
                            </Link>
                            <div className="tenant-id-text">{tenant.id}</div>
                          </td>
                          <td>
                            <span
                              className={`status-badge status-${tenant.status || 'active'}`}
                              style={{
                                display: 'inline-block',
                                padding: '3px 8px',
                                borderRadius: 'var(--radius-full)',
                                fontSize: '0.75rem',
                                fontWeight: '600',
                                textTransform: 'uppercase',
                                letterSpacing: '0.03em',
                                background:
                                  tenant.status === 'active'
                                    ? 'rgba(16, 185, 129, 0.15)'
                                    : tenant.status === 'pending'
                                    ? 'rgba(245, 158, 11, 0.15)'
                                    : 'rgba(239, 68, 68, 0.15)',
                                color:
                                  tenant.status === 'active'
                                    ? '#10b981'
                                    : tenant.status === 'pending'
                                    ? '#f59e0b'
                                    : '#ef4444',
                                border: `1px solid ${
                                  tenant.status === 'active'
                                    ? 'rgba(16, 185, 129, 0.3)'
                                    : tenant.status === 'pending'
                                    ? 'rgba(245, 158, 11, 0.3)'
                                    : 'rgba(239, 68, 68, 0.3)'
                                }`,
                              }}
                            >
                              {tenant.status || 'active'}
                            </span>
                          </td>
                          <td>
                            <span className="plan-badge">{tenant.plan || 'Free'}</span>
                          </td>
                          <td>
                            <span className="user-count-chip">
                              {tenant.user_count ?? 0} {tenant.user_count === 1 ? 'user' : 'users'}
                            </span>
                          </td>
                          <td className="tenant-date-col">{formatDate(tenant.created_at)}</td>
                          <td className="text-right">
                            <div className="table-action-btns">
                              {isPending ? (
                                <>
                                  <button
                                    type="button"
                                    className="btn-action"
                                    style={{
                                      background: 'rgba(16, 185, 129, 0.15)',
                                      color: '#10b981',
                                      borderColor: 'rgba(16, 185, 129, 0.3)',
                                      fontWeight: '600',
                                    }}
                                    onClick={() => setApproveModal({ isOpen: true, tenant })}
                                    title="Approve organization"
                                  >
                                    Approve
                                  </button>
                                  <button
                                    type="button"
                                    className="btn-action btn-action-danger"
                                    onClick={() => setRejectModal({ isOpen: true, tenant })}
                                    title="Reject organization"
                                  >
                                    Reject
                                  </button>
                                </>
                              ) : null}
                              <Link
                                to={`/super-admin/tenants/${tenant.id}`}
                                className="btn-action btn-action-view"
                                title="View details and users"
                              >
                                View
                              </Link>
                              <button
                                type="button"
                                className="btn-action"
                                onClick={() => setEditModal({ isOpen: true, tenant })}
                                title="Edit tenant"
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                className="btn-action btn-action-danger"
                                onClick={() => setDeleteModal({ isOpen: true, tenant })}
                                title="Delete tenant"
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* Approve Tenant Modal */}
      <TenantApproveModal
        isOpen={approveModal.isOpen}
        tenant={approveModal.tenant}
        onClose={() => setApproveModal({ isOpen: false, tenant: null })}
        onConfirm={handleApproveConfirm}
      />

      {/* Reject Tenant Modal */}
      <TenantRejectModal
        isOpen={rejectModal.isOpen}
        tenant={rejectModal.tenant}
        onClose={() => setRejectModal({ isOpen: false, tenant: null })}
        onConfirm={handleRejectConfirm}
      />

      {/* Edit Tenant Modal */}
      <TenantEditModal
        isOpen={editModal.isOpen}
        tenant={editModal.tenant}
        onClose={() => setEditModal({ isOpen: false, tenant: null })}
        onSave={handleEditSave}
      />

      {/* Delete Tenant Modal */}
      <TenantDeleteModal
        isOpen={deleteModal.isOpen}
        tenant={deleteModal.tenant}
        onClose={() => setDeleteModal({ isOpen: false, tenant: null })}
        onConfirm={handleDeleteConfirm}
      />
    </main>
  );
}

export default SuperAdminDashboardPage;
