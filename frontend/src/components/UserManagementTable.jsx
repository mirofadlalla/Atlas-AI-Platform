import React, { useState, useMemo } from 'react';
import Modal from './Modal';
import Spinner from './Spinner';
import EmptyState from './EmptyState';
import './UserManagementTable.css';

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

function UserManagementTable({
  users = [],
  currentUser = null,
  isSuperAdmin = false,
  showTenantColumn = false,
  tenantNameMap = {},
  loading = false,
  onRoleChange,
  onStatusChange,
  onDelete,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [tenantFilter, setTenantFilter] = useState('all');

  // Modals state
  const [deleteModal, setDeleteModal] = useState({ isOpen: false, user: null, isProcessing: false });
  const [roleModal, setRoleModal] = useState({ isOpen: false, user: null, selectedRole: 'user', isProcessing: false });
  const [statusModal, setStatusModal] = useState({ isOpen: false, user: null, selectedStatus: 'approved', isProcessing: false });

  // Unique tenants for filter dropdown when in global mode
  const uniqueTenants = useMemo(() => {
    if (!showTenantColumn) return [];
    const tenants = new Map();
    users.forEach((u) => {
      if (u.tenant_id) {
        const name = tenantNameMap[u.tenant_id] || u.tenant_name || `Tenant ${u.tenant_id.substring(0, 8)}…`;
        tenants.set(u.tenant_id, name);
      }
    });
    return Array.from(tenants.entries()).map(([id, name]) => ({ id, name }));
  }, [users, showTenantColumn, tenantNameMap]);

  // Filtered users
  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      // Search filter
      const matchesSearch =
        !searchTerm.trim() ||
        (u.name && u.name.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (u.email && u.email.toLowerCase().includes(searchTerm.toLowerCase()));

      // Role filter
      const matchesRole = roleFilter === 'all' || u.role === roleFilter;

      // Status filter
      const matchesStatus = statusFilter === 'all' || u.approval_status === statusFilter;

      // Tenant filter
      const matchesTenant =
        tenantFilter === 'all' ||
        (tenantFilter === 'none' && !u.tenant_id) ||
        u.tenant_id === tenantFilter;

      return matchesSearch && matchesRole && matchesStatus && matchesTenant;
    });
  }, [users, searchTerm, roleFilter, statusFilter, tenantFilter]);

  // Check if current user is attempting an action on self
  const isSelf = (user) => {
    if (!currentUser || !user) return false;
    return (
      (currentUser.id && currentUser.id === user.id) ||
      (currentUser.user_id && currentUser.user_id === user.id) ||
      (currentUser.email && currentUser.email === user.email)
    );
  };

  // Determine if tenant admin is restricted from modifying this user
  const isSuperAdminTargetForTenantAdmin = (user) => {
    return !isSuperAdmin && user?.role === 'super_admin';
  };

  // Delete Handlers
  const handleOpenDelete = (user) => {
    setDeleteModal({ isOpen: true, user, isProcessing: false });
  };

  const handleConfirmDelete = async () => {
    if (!deleteModal.user || !onDelete) return;
    setDeleteModal((prev) => ({ ...prev, isProcessing: true }));
    try {
      await onDelete(deleteModal.user);
      setDeleteModal({ isOpen: false, user: null, isProcessing: false });
    } catch (err) {
      setDeleteModal((prev) => ({ ...prev, isProcessing: false }));
    }
  };

  // Role Handlers
  const handleOpenRole = (user) => {
    setRoleModal({
      isOpen: true,
      user,
      selectedRole: user.role || 'user',
      isProcessing: false,
    });
  };

  const handleConfirmRole = async () => {
    if (!roleModal.user || !onRoleChange) return;
    setRoleModal((prev) => ({ ...prev, isProcessing: true }));
    try {
      await onRoleChange(roleModal.user, roleModal.selectedRole);
      setRoleModal({ isOpen: false, user: null, selectedRole: 'user', isProcessing: false });
    } catch (err) {
      setRoleModal((prev) => ({ ...prev, isProcessing: false }));
    }
  };

  // Status Handlers
  const handleOpenStatus = (user) => {
    setStatusModal({
      isOpen: true,
      user,
      selectedStatus: user.approval_status || 'approved',
      isProcessing: false,
    });
  };

  const handleConfirmStatus = async () => {
    if (!statusModal.user || !onStatusChange) return;
    setStatusModal((prev) => ({ ...prev, isProcessing: true }));
    try {
      await onStatusChange(statusModal.user, statusModal.selectedStatus);
      setStatusModal({ isOpen: false, user: null, selectedStatus: 'approved', isProcessing: false });
    } catch (err) {
      setStatusModal((prev) => ({ ...prev, isProcessing: false }));
    }
  };

  return (
    <div className="user-management-table-wrap">
      {/* Search & Filter Toolbar */}
      <div className="table-toolbar">
        <div className="search-box">
          <input
            type="text"
            className="search-input"
            placeholder="Search by name or email…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            aria-label="Search users"
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
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            aria-label="Filter by role"
          >
            <option value="all">All Roles</option>
            <option value="user">User</option>
            <option value="admin">Admin</option>
            {isSuperAdmin && <option value="super_admin">Super Admin</option>}
          </select>

          <select
            className="filter-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by approval status"
          >
            <option value="all">All Statuses</option>
            <option value="approved">Approved</option>
            <option value="pending">Pending</option>
            <option value="rejected">Rejected</option>
          </select>

          {showTenantColumn && uniqueTenants.length > 0 && (
            <select
              className="filter-select"
              value={tenantFilter}
              onChange={(e) => setTenantFilter(e.target.value)}
              aria-label="Filter by tenant"
            >
              <option value="all">All Tenants</option>
              <option value="none">No Tenant (Global)</option>
              {uniqueTenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Table Content */}
      {loading ? (
        <div className="table-loading-container" aria-live="polite">
          <Spinner size="lg" label="Loading users…" />
          <p>Loading users…</p>
        </div>
      ) : filteredUsers.length === 0 ? (
        <EmptyState
          icon="👥"
          title={users.length === 0 ? 'No users found' : 'No matching users'}
          description={
            users.length === 0
              ? 'There are currently no users in this view.'
              : 'Try clearing your search or changing your filter criteria.'
          }
          action={
            (searchTerm || roleFilter !== 'all' || statusFilter !== 'all' || tenantFilter !== 'all') && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => {
                  setSearchTerm('');
                  setRoleFilter('all');
                  setStatusFilter('all');
                  setTenantFilter('all');
                }}
              >
                Reset Filters
              </button>
            )
          }
        />
      ) : (
        <div className="table-responsive">
          <table className="user-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                {showTenantColumn && <th scope="col">Tenant</th>}
                <th scope="col">Role</th>
                <th scope="col">Status</th>
                <th scope="col">Created</th>
                <th scope="col" className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => {
                const self = isSelf(user);
                const superAdminRestricted = isSuperAdminTargetForTenantAdmin(user);

                return (
                  <tr key={user.id} className={self ? 'row-self' : ''}>
                    <td className="user-name-cell">
                      <div className="user-primary-name">
                        {user.name || 'Unnamed User'}
                        {self && <span className="self-tag">You</span>}
                      </div>
                    </td>
                    <td className="user-email-cell">
                      <span className="user-email">{user.email}</span>
                    </td>
                    {showTenantColumn && (
                      <td className="user-tenant-cell">
                        {user.tenant_id ? (
                          <span className="tenant-name-badge" title={user.tenant_id}>
                            {tenantNameMap[user.tenant_id] ||
                              user.tenant_name ||
                              `${user.tenant_id.substring(0, 8)}…`}
                          </span>
                        ) : (
                          <span className="tenant-global-badge">Global (None)</span>
                        )}
                      </td>
                    )}
                    <td className="user-role-cell">
                      <span
                        className={`role-badge role-${user.role || 'user'}`}
                        title={`Role: ${user.role}`}
                      >
                        {user.role === 'super_admin'
                          ? 'Super Admin'
                          : user.role === 'admin'
                          ? 'Admin'
                          : 'User'}
                      </span>
                    </td>
                    <td className="user-status-cell">
                      <span
                        className={`status-badge status-${user.approval_status || 'pending'}`}
                        title={`Status: ${user.approval_status}`}
                      >
                        {user.approval_status || 'pending'}
                      </span>
                    </td>
                    <td className="user-created-cell">
                      {formatDate(user.created_at)}
                    </td>
                    <td className="user-actions-cell text-right">
                      <div className="action-buttons-group">
                        {/* Change Role Button */}
                        <button
                          type="button"
                          className="btn-action btn-action-role"
                          onClick={() => handleOpenRole(user)}
                          disabled={superAdminRestricted}
                          title={
                            superAdminRestricted
                              ? 'Cannot modify role of a super admin'
                              : 'Change user role'
                          }
                          aria-label={`Change role for ${user.name || user.email}`}
                        >
                          Role
                        </button>

                        {/* Change Status Button */}
                        <button
                          type="button"
                          className="btn-action btn-action-status"
                          onClick={() => handleOpenStatus(user)}
                          disabled={superAdminRestricted}
                          title={
                            superAdminRestricted
                              ? 'Cannot modify status of a super admin'
                              : 'Change approval status'
                          }
                          aria-label={`Change status for ${user.name || user.email}`}
                        >
                          Status
                        </button>

                        {/* Delete User Button */}
                        <button
                          type="button"
                          className="btn-action btn-action-danger"
                          onClick={() => handleOpenDelete(user)}
                          disabled={self || superAdminRestricted}
                          title={
                            self
                              ? 'You cannot delete your own account'
                              : superAdminRestricted
                              ? 'Cannot delete a super admin'
                              : 'Delete user'
                          }
                          aria-label={`Delete ${user.name || user.email}`}
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

      {/* Delete User Confirmation Modal */}
      <Modal
        isOpen={deleteModal.isOpen}
        onClose={() => setDeleteModal({ isOpen: false, user: null, isProcessing: false })}
        title="Delete User"
        showCancel={false}
      >
        <div className="modal-dialog-inner">
          <p>
            Are you sure you want to permanently delete user{' '}
            <strong>{deleteModal.user?.name || 'this user'}</strong> (
            <code>{deleteModal.user?.email}</code>)?
          </p>
          <p className="text-warning-muted">
            This action cannot be undone. All permissions, sessions, and memory data for this user will be removed.
          </p>
          <div className="modal-actions-inline">
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => setDeleteModal({ isOpen: false, user: null, isProcessing: false })}
              disabled={deleteModal.isProcessing}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-danger btn-sm"
              onClick={handleConfirmDelete}
              disabled={deleteModal.isProcessing}
            >
              {deleteModal.isProcessing ? (
                <>
                  <Spinner size="sm" /> Deleting…
                </>
              ) : (
                'Delete User'
              )}
            </button>
          </div>
        </div>
      </Modal>

      {/* Change Role Modal */}
      <Modal
        isOpen={roleModal.isOpen}
        onClose={() => setRoleModal({ isOpen: false, user: null, selectedRole: 'user', isProcessing: false })}
        title="Change User Role"
        showCancel={false}
      >
        <div className="modal-dialog-inner">
          <p>
            Update role for <strong>{roleModal.user?.name || roleModal.user?.email}</strong>:
          </p>
          <div className="form-group" style={{ margin: '16px 0' }}>
            <label htmlFor="select-user-role">Select Role</label>
            <select
              id="select-user-role"
              className="form-control"
              value={roleModal.selectedRole}
              onChange={(e) => setRoleModal((prev) => ({ ...prev, selectedRole: e.target.value }))}
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
              {isSuperAdmin && <option value="super_admin">Super Admin</option>}
            </select>
          </div>
          <div className="modal-actions-inline">
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => setRoleModal({ isOpen: false, user: null, selectedRole: 'user', isProcessing: false })}
              disabled={roleModal.isProcessing}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary btn-sm"
              onClick={handleConfirmRole}
              disabled={roleModal.isProcessing || roleModal.selectedRole === roleModal.user?.role}
            >
              {roleModal.isProcessing ? (
                <>
                  <Spinner size="sm" /> Updating…
                </>
              ) : (
                'Update Role'
              )}
            </button>
          </div>
        </div>
      </Modal>

      {/* Change Status Modal */}
      <Modal
        isOpen={statusModal.isOpen}
        onClose={() => setStatusModal({ isOpen: false, user: null, selectedStatus: 'approved', isProcessing: false })}
        title="Change Approval Status"
        showCancel={false}
      >
        <div className="modal-dialog-inner">
          <p>
            Update approval status for <strong>{statusModal.user?.name || statusModal.user?.email}</strong>:
          </p>
          <div className="form-group" style={{ margin: '16px 0' }}>
            <label htmlFor="select-user-status">Select Status</label>
            <select
              id="select-user-status"
              className="form-control"
              value={statusModal.selectedStatus}
              onChange={(e) => setStatusModal((prev) => ({ ...prev, selectedStatus: e.target.value }))}
            >
              <option value="approved">Approved</option>
              <option value="pending">Pending</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          <div className="modal-actions-inline">
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => setStatusModal({ isOpen: false, user: null, selectedStatus: 'approved', isProcessing: false })}
              disabled={statusModal.isProcessing}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary btn-sm"
              onClick={handleConfirmStatus}
              disabled={statusModal.isProcessing || statusModal.selectedStatus === statusModal.user?.approval_status}
            >
              {statusModal.isProcessing ? (
                <>
                  <Spinner size="sm" /> Updating…
                </>
              ) : (
                'Update Status'
              )}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default UserManagementTable;
