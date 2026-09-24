import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import apiService from '../services/apiService';
import Spinner from '../components/Spinner';
import UserManagementTable from '../components/UserManagementTable';
import { useToast } from '../components/Toast';
import { getOrganizationName } from '../utils/user';
import './AdminUsersPage.css';

function AdminUsersPage({ user: currentUser }) {
  const toast = useToast();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const orgName = getOrganizationName(currentUser);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiService.getAdminUsers();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to fetch organization users.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleRoleChange = async (targetUser, newRole) => {
    // Client-side guard: Tenant admin cannot assign or modify super_admin
    if (newRole === 'super_admin' || targetUser.role === 'super_admin') {
      toast.error('Admins cannot assign or modify the super_admin role.');
      return;
    }

    try {
      await apiService.updateAdminUserRole(targetUser.id, newRole);
      toast.success(`Role for ${targetUser.name || targetUser.email} updated to ${newRole}!`);
      loadUsers();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update user role.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleStatusChange = async (targetUser, newStatus) => {
    if (targetUser.role === 'super_admin') {
      toast.error('Admins cannot modify the approval status of a super admin.');
      return;
    }

    try {
      await apiService.updateAdminUserStatus(targetUser.id, newStatus);
      toast.success(`Status for ${targetUser.name || targetUser.email} updated to ${newStatus}!`);
      loadUsers();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update user status.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  const handleDeleteUser = async (targetUser) => {
    if (targetUser.id === currentUser?.id || targetUser.id === currentUser?.user_id) {
      toast.error('You cannot delete your own account.');
      return;
    }
    if (targetUser.role === 'super_admin') {
      toast.error('Admins cannot delete a super admin.');
      return;
    }

    try {
      await apiService.deleteAdminUser(targetUser.id);
      toast.success(`User ${targetUser.name || targetUser.email} deleted successfully.`);
      loadUsers();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to delete user.';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      throw err;
    }
  };

  return (
    <main className="admin-users-page">
      <div className="admin-users-header">
        <div className="admin-users-header-title">
          <div className="admin-breadcrumbs">
            <Link to="/admin" className="breadcrumb-link">
              Admin
            </Link>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">Users</span>
          </div>
          <h1>
            Organization Users ({users.length})
            {orgName && <span className="tenant-subtitle-badge"> · {orgName}</span>}
          </h1>
          <p>Manage user roles and approval access within your organization</p>
        </div>
        <div className="admin-users-header-actions">
          <Link to="/admin" className="btn-secondary btn-sm">
            ← Admin Dashboard
          </Link>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={loadUsers}
            disabled={loading}
            title="Refresh user list"
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
          <button type="button" className="btn-secondary btn-sm" onClick={loadUsers}>
            Retry
          </button>
        </div>
      )}

      <div className="admin-users-container">
        <UserManagementTable
          users={users}
          currentUser={currentUser}
          isSuperAdmin={false}
          showTenantColumn={false}
          loading={loading}
          onRoleChange={handleRoleChange}
          onStatusChange={handleStatusChange}
          onDelete={handleDeleteUser}
        />
      </div>
    </main>
  );
}

export default AdminUsersPage;
