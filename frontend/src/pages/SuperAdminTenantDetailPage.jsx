import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import apiService from '../services/apiService';
import Spinner from '../components/Spinner';
import UserManagementTable from '../components/UserManagementTable';
import TenantEditModal from '../components/TenantEditModal';
import TenantDeleteModal from '../components/TenantDeleteModal';
import TenantApproveModal from '../components/TenantApproveModal';
import TenantRejectModal from '../components/TenantRejectModal';
import { useToast } from '../components/Toast';
import './SuperAdminTenantDetailPage.css';

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

function SuperAdminTenantDetailPage({ user: currentUser }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [tenantData, setTenantData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Modals
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [approveModalOpen, setApproveModalOpen] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);

  const loadTenant = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError('');
    try {
      const data = await apiService.getSuperAdminTenantDetail(id);
      setTenantData(data);
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to fetch tenant details.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadTenant();
  }, [loadTenant]);

  const handleCopyId = async () => {
    try {
      await navigator.clipboard?.writeText(id);
      toast.success('Tenant ID copied to clipboard!');
    } catch {
      toast.warning('Could not copy automatically.');
    }
  };

  const handleApproveConfirm = async (tenantId, note) => {
    try {
      await apiService.approveSuperAdminTenant(tenantId, note);
      toast.success('Organization workspace approved and activated successfully!');
      loadTenant();
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
      loadTenant();
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
      loadTenant();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update tenant.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleDeleteConfirm = async (tenantId) => {
    try {
      await apiService.deleteSuperAdminTenant(tenantId);
      toast.success('Tenant deleted successfully!');
      navigate('/super-admin/tenants');
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to delete tenant.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleRoleChange = async (targetUser, newRole) => {
    try {
      await apiService.updateSuperAdminUserRole(targetUser.id, newRole);
      toast.success(`Role for ${targetUser.name || targetUser.email} updated to ${newRole}!`);
      loadTenant();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update user role.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleStatusChange = async (targetUser, newStatus) => {
    try {
      await apiService.updateSuperAdminUserStatus(targetUser.id, newStatus);
      toast.success(`Status for ${targetUser.name || targetUser.email} updated to ${newStatus}!`);
      loadTenant();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update user status.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleDeleteUser = async (targetUser) => {
    try {
      await apiService.deleteSuperAdminUser(targetUser.id);
      toast.success(`User ${targetUser.name || targetUser.email} deleted.`);
      loadTenant();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to delete user.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const tenant = tenantData?.tenant;
  const users = tenantData?.users || [];
  const isPending = tenant?.status === 'pending';
  const isRejected = tenant?.status === 'rejected';

  return (
    <main className="super-admin-page">
      <div className="super-admin-header">
        <div className="super-admin-header-title">
          <div className="super-admin-breadcrumbs">
            <Link to="/super-admin" className="breadcrumb-link">
              Super Admin
            </Link>
            <span className="breadcrumb-sep">/</span>
            <Link to="/super-admin/tenants" className="breadcrumb-link">
              Tenants
            </Link>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">{tenant?.name || id}</span>
          </div>
          <h1>{tenant?.name || 'Tenant Details'}</h1>
          <p>Inspect organization profile, subscription tier, and member roster</p>
        </div>
        <div className="super-admin-header-actions">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={loadTenant}
            disabled={loading}
            title="Refresh tenant data"
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
          <button type="button" className="btn-secondary btn-sm" onClick={loadTenant}>
            Retry
          </button>
        </div>
      )}

      {loading && !tenantData ? (
        <div className="super-admin-loading" aria-live="polite">
          <Spinner size="lg" label="Loading tenant details…" />
          <p>Fetching organization information…</p>
        </div>
      ) : tenant ? (
        <>
          {/* Status Alert Banner if Pending or Rejected */}
          {isPending && (
            <div
              style={{
                background: 'rgba(245, 158, 11, 0.15)',
                border: '1px solid rgba(245, 158, 11, 0.5)',
                borderRadius: 'var(--radius-xl)',
                padding: '18px 24px',
                marginBottom: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '14px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                <span style={{ fontSize: '1.8rem' }}>⏳</span>
                <div>
                  <h3 style={{ margin: '0 0 4px 0', color: 'var(--text-warning, #f59e0b)', fontSize: '1.05rem' }}>
                    Registration Awaiting Super Admin Approval
                  </h3>
                  <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                    This organization is pending review. Member and administrator logins remain blocked until approved.
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  style={{ background: '#10b981', borderColor: '#10b981', fontWeight: 'bold' }}
                  onClick={() => setApproveModalOpen(true)}
                >
                  ✓ Approve Workspace
                </button>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  style={{ borderColor: 'rgba(239, 68, 68, 0.5)', color: '#ef4444' }}
                  onClick={() => setRejectModalOpen(true)}
                >
                  ✕ Decline Registration
                </button>
              </div>
            </div>
          )}

          {isRejected && (
            <div
              style={{
                background: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                borderRadius: 'var(--radius-xl)',
                padding: '16px 20px',
                marginBottom: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '1.5rem' }}>❌</span>
                <div>
                  <strong style={{ color: 'var(--text-error, #ef4444)', fontSize: '1rem' }}>
                    Organization Registration Declined
                  </strong>
                  <p style={{ margin: '2px 0 0 0', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                    This workspace was rejected by a Super Admin. Logins are currently disabled.
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="btn-secondary btn-sm"
                style={{ borderColor: '#10b981', color: '#10b981' }}
                onClick={() => setApproveModalOpen(true)}
              >
                Re-activate Workspace
              </button>
            </div>
          )}

          {/* Tenant Profile Card */}
          <div className="tenant-profile-card">
            <div className="tenant-profile-main">
              <div className="tenant-avatar" aria-hidden="true">
                🏢
              </div>
              <div className="tenant-profile-info">
                <div className="tenant-title-row">
                  <h2>{tenant.name}</h2>
                  <span
                    className={`status-badge status-${tenant.status || 'active'}`}
                    style={{
                      display: 'inline-block',
                      padding: '4px 10px',
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
                    {tenant.status === 'pending' ? 'Pending Review' : tenant.status || 'Active'}
                  </span>
                  <span className="plan-badge">{tenant.plan || 'Free'}</span>
                </div>
                <div className="tenant-id-row">
                  <span className="tenant-id-label">Tenant ID:</span>
                  <code className="tenant-id-code">{tenant.id}</code>
                  <button
                    type="button"
                    className="btn-copy"
                    onClick={handleCopyId}
                    title="Copy Tenant UUID"
                  >
                    Copy
                  </button>
                </div>
                <div className="tenant-meta-row">
                  <span>Created: {formatDate(tenant.created_at)}</span>
                  <span>·</span>
                  <span>{users.length} {users.length === 1 ? 'Registered User' : 'Registered Users'}</span>
                </div>
              </div>
            </div>

            <div className="tenant-profile-actions">
              {isPending && (
                <>
                  <button
                    type="button"
                    className="btn-primary btn-sm"
                    style={{ background: '#10b981', borderColor: '#10b981', fontWeight: '600' }}
                    onClick={() => setApproveModalOpen(true)}
                  >
                    ✓ Approve
                  </button>
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#ef4444' }}
                    onClick={() => setRejectModalOpen(true)}
                  >
                    ✕ Decline
                  </button>
                </>
              )}
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => setEditModalOpen(true)}
              >
                ✏️ Edit Tenant
              </button>
              <button
                type="button"
                className="btn-danger btn-sm"
                onClick={() => setDeleteModalOpen(true)}
              >
                🗑️ Delete Tenant
              </button>
            </div>
          </div>

          {/* Tenant Users Section */}
          <div className="super-admin-section">
            <div className="section-header">
              <div>
                <h2>Organization Users ({users.length})</h2>
                <p className="section-subtitle">
                  Users affiliated with {tenant.name}. Manage roles, approval states, or remove accounts.
                </p>
              </div>
            </div>

            <UserManagementTable
              users={users}
              currentUser={currentUser}
              isSuperAdmin={true}
              showTenantColumn={false}
              loading={loading}
              onRoleChange={handleRoleChange}
              onStatusChange={handleStatusChange}
              onDelete={handleDeleteUser}
            />
          </div>

          {/* Approve Tenant Modal */}
          <TenantApproveModal
            isOpen={approveModalOpen}
            tenant={tenant}
            onClose={() => setApproveModalOpen(false)}
            onConfirm={handleApproveConfirm}
          />

          {/* Reject Tenant Modal */}
          <TenantRejectModal
            isOpen={rejectModalOpen}
            tenant={tenant}
            onClose={() => setRejectModalOpen(false)}
            onConfirm={handleRejectConfirm}
          />

          {/* Edit Tenant Modal */}
          <TenantEditModal
            isOpen={editModalOpen}
            tenant={tenant}
            onClose={() => setEditModalOpen(false)}
            onSave={handleEditSave}
          />

          {/* Delete Tenant Modal */}
          <TenantDeleteModal
            isOpen={deleteModalOpen}
            tenant={tenant}
            onClose={() => setDeleteModalOpen(false)}
            onConfirm={handleDeleteConfirm}
          />
        </>
      ) : null}
    </main>
  );
}

export default SuperAdminTenantDetailPage;
