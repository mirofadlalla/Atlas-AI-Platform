import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import apiService from '../services/apiService';
import Spinner from '../components/Spinner';
import EmptyState from '../components/EmptyState';
import TenantEditModal from '../components/TenantEditModal';
import TenantDeleteModal from '../components/TenantDeleteModal';
import { useToast } from '../components/Toast';
import './SuperAdminTenantsPage.css';

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

function SuperAdminTenantsPage() {
  const toast = useToast();
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [planFilter, setPlanFilter] = useState('all');

  // Modals
  const [editModal, setEditModal] = useState({ isOpen: false, tenant: null });
  const [deleteModal, setDeleteModal] = useState({ isOpen: false, tenant: null });

  const loadTenants = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiService.getSuperAdminTenants();
      setTenants(Array.isArray(data) ? data : []);
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to fetch tenants.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTenants();
  }, [loadTenants]);

  const handleEditSave = async (tenantId, payload) => {
    try {
      await apiService.updateSuperAdminTenant(tenantId, payload);
      toast.success('Tenant updated successfully!');
      loadTenants();
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
      loadTenants();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to delete tenant.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  // Distinct plans for filter
  const plans = useMemo(() => {
    const set = new Set();
    tenants.forEach((t) => {
      if (t.plan) set.add(t.plan);
    });
    return Array.from(set);
  }, [tenants]);

  // Filtered tenants
  const filteredTenants = useMemo(() => {
    return tenants.filter((t) => {
      const matchesSearch =
        !searchTerm.trim() ||
        (t.name && t.name.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (t.id && t.id.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchesPlan = planFilter === 'all' || t.plan === planFilter;

      return matchesSearch && matchesPlan;
    });
  }, [tenants, searchTerm, planFilter]);

  return (
    <main className="super-admin-page">
      <div className="super-admin-header">
        <div className="super-admin-header-title">
          <div className="super-admin-breadcrumbs">
            <Link to="/super-admin" className="breadcrumb-link">
              Super Admin
            </Link>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">Tenants</span>
          </div>
          <h1>All Organizations ({tenants.length})</h1>
          <p>Inspect, update plans, and manage platform tenant accounts</p>
        </div>
        <div className="super-admin-header-actions">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={loadTenants}
            disabled={loading}
            title="Refresh tenants"
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
          <button type="button" className="btn-secondary btn-sm" onClick={loadTenants}>
            Retry
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="table-toolbar">
        <div className="search-box">
          <input
            type="text"
            className="search-input"
            placeholder="Search by tenant name or ID…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            aria-label="Search tenants"
          />
          {searchTerm && (
            <button
              type="button"
              className="search-clear-btn"
              onClick={() => setSearchTerm('')}
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>

        <div className="filter-group">
          <select
            className="filter-select"
            value={planFilter}
            onChange={(e) => setPlanFilter(e.target.value)}
            aria-label="Filter by plan"
          >
            <option value="all">All Plans</option>
            {plans.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table Content */}
      {loading ? (
        <div className="super-admin-loading" aria-live="polite">
          <Spinner size="lg" label="Loading tenants…" />
          <p>Fetching organizations…</p>
        </div>
      ) : filteredTenants.length === 0 ? (
        <EmptyState
          icon="🏢"
          title={tenants.length === 0 ? 'No tenants found' : 'No matching organizations'}
          description={
            tenants.length === 0
              ? 'No tenants have registered on this platform yet.'
              : 'Try clearing your search or plan filter.'
          }
          action={
            (searchTerm || planFilter !== 'all') && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => {
                  setSearchTerm('');
                  setPlanFilter('all');
                }}
              >
                Reset Filters
              </button>
            )
          }
        />
      ) : (
        <div className="table-responsive">
          <table className="super-admin-table">
            <thead>
              <tr>
                <th scope="col">Organization / Tenant</th>
                <th scope="col">Plan</th>
                <th scope="col">User Count</th>
                <th scope="col">Created Date</th>
                <th scope="col" className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredTenants.map((tenant) => (
                <tr key={tenant.id}>
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
                      <Link
                        to={`/super-admin/tenants/${tenant.id}`}
                        className="btn-action btn-action-view"
                        title="View tenant details & users"
                      >
                        View
                      </Link>
                      <button
                        type="button"
                        className="btn-action"
                        onClick={() => setEditModal({ isOpen: true, tenant })}
                        title="Edit tenant name/plan"
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
              ))}
            </tbody>
          </table>
        </div>
      )}

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

export default SuperAdminTenantsPage;
