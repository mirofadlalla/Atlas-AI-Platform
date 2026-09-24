import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import apiService from '../services/apiService';
import Spinner from '../components/Spinner';
import UserManagementTable from '../components/UserManagementTable';
import TenantEditModal from '../components/TenantEditModal';
import TenantDeleteModal from '../components/TenantDeleteModal';
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
          {/* Tenant Profile Card */}
          <div className="tenant-profile-card">
            <div className="tenant-profile-main">
              <div className="tenant-avatar" aria-hidden="true">
                🏢
              </div>
              <div className="tenant-profile-info">
                <div className="tenant-title-row">
                  <h2>{tenant.name}</h2>
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
