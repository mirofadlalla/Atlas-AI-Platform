import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import apiService from '../services/apiService';
import Spinner from '../components/Spinner';
import UserManagementTable from '../components/UserManagementTable';
import { useToast } from '../components/Toast';
import './SuperAdminUsersPage.css';

function SuperAdminUsersPage({ user: currentUser }) {
  const toast = useToast();
  const [users, setUsers] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [usersData, tenantsData] = await Promise.all([
        apiService.getSuperAdminUsers(),
        apiService.getSuperAdminTenants().catch(() => []),
      ]);
      setUsers(Array.isArray(usersData) ? usersData : []);
      setTenants(Array.isArray(tenantsData) ? tenantsData : []);
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to fetch platform users.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Map tenant IDs to readable tenant names
  const tenantNameMap = useMemo(() => {
    const map = {};
    tenants.forEach((t) => {
      if (t.id && t.name) {
        map[t.id] = t.name;
      }
    });
    return map;
  }, [tenants]);

  const handleRoleChange = async (targetUser, newRole) => {
    try {
      await apiService.updateSuperAdminUserRole(targetUser.id, newRole);
      toast.success(`Role for ${targetUser.name || targetUser.email} changed to ${newRole}!`);
      loadData();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update user role.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleStatusChange = async (targetUser, newStatus) => {
    try {
      await apiService.updateSuperAdminUserStatus(targetUser.id, newStatus);
      toast.success(`Status for ${targetUser.name || targetUser.email} changed to ${newStatus}!`);
      loadData();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update user status.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleDeleteUser = async (targetUser) => {
    try {
      await apiService.deleteSuperAdminUser(targetUser.id);
      toast.success(`User ${targetUser.name || targetUser.email} deleted successfully.`);
      loadData();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to delete user.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  return (
    <main className="super-admin-page">
      <div className="super-admin-header">
        <div className="super-admin-header-title">
          <div className="super-admin-breadcrumbs">
            <Link to="/super-admin" className="breadcrumb-link">
              Super Admin
            </Link>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">Users</span>
          </div>
          <h1>Platform User Directory ({users.length})</h1>
          <p>Cross-tenant user roster with role assignment and approval controls</p>
        </div>
        <div className="super-admin-header-actions">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={loadData}
            disabled={loading}
            title="Refresh users"
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
          <button type="button" className="btn-secondary btn-sm" onClick={loadData}>
            Retry
          </button>
        </div>
      )}

      <div className="super-admin-section">
        <UserManagementTable
          users={users}
          currentUser={currentUser}
          isSuperAdmin={true}
          showTenantColumn={true}
          tenantNameMap={tenantNameMap}
          loading={loading}
          onRoleChange={handleRoleChange}
          onStatusChange={handleStatusChange}
          onDelete={handleDeleteUser}
        />
      </div>
    </main>
  );
}

export default SuperAdminUsersPage;
