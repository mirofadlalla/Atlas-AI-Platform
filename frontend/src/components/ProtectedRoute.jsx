import React from 'react';
import { Navigate } from 'react-router-dom';

/**
 * ProtectedRoute — redirects unauthenticated users to /login.
 *
 * Usage:
 *   <ProtectedRoute isAuthenticated={isAuthenticated}>
 *     <SomePage />
 *   </ProtectedRoute>
 */
function ProtectedRoute({ children, isAuthenticated, loading }) {
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <p>⏳ Loading...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

/**
 * AdminRoute — redirects unauthenticated users to /login AND
 * redirects authenticated non-admin users to /dashboard.
 * Super admins accessing /admin are redirected to /super-admin.
 *
 * Previously the /admin route was only guarded by isAuthenticated,
 * meaning any logged-in user (including regular users) could access
 * admin functionality. This component adds the role check.
 *
 * Usage:
 *   <AdminRoute isAuthenticated={isAuthenticated} user={user}>
 *     <AdminPanel />
 *   </AdminRoute>
 */
export function AdminRoute({ children, isAuthenticated, user, loading }) {
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <p>⏳ Loading...</p>
      </div>
    );
  }

  // Not logged in at all → go to login
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Super admins have their own portal, redirect to /super-admin
  if (user?.role === 'super_admin') {
    return <Navigate to="/super-admin" replace />;
  }

  // Logged in but not an admin → redirect to dashboard with a message
  if (!user || user.role !== 'admin') {
    return <Navigate to="/dashboard" replace state={{ error: 'Admin access required.' }} />;
  }

  return children;
}

/**
 * SuperAdminRoute — redirects unauthenticated users to /login AND
 * redirects non-super-admin users to /dashboard.
 *
 * Usage:
 *   <SuperAdminRoute isAuthenticated={isAuthenticated} user={user}>
 *     <SuperAdminDashboardPage />
 *   </SuperAdminRoute>
 */
export function SuperAdminRoute({ children, isAuthenticated, user, loading }) {
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <p>⏳ Loading...</p>
      </div>
    );
  }

  // Not logged in at all → go to login
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Logged in but not a super admin → redirect to dashboard
  if (!user || user.role !== 'super_admin') {
    return <Navigate to="/dashboard" replace state={{ error: 'Super Admin access required.' }} />;
  }

  return children;
}

export default ProtectedRoute;
