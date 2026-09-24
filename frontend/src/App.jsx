import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import './App.css';

// Import pages
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import TenantRegistrationPage from './pages/TenantRegistrationPage';
import DashboardPage from './pages/DashboardPage';
import QueryPage from './pages/QueryPage';
import AgentPage from './pages/AgentPage';
import IngestPage from './pages/IngestPage';
import AdminPanel from './pages/AdminPanel';
import AdminUsersPage from './pages/AdminUsersPage';
import SuperAdminDashboardPage from './pages/SuperAdminDashboardPage';
import SuperAdminTenantsPage from './pages/SuperAdminTenantsPage';
import SuperAdminTenantDetailPage from './pages/SuperAdminTenantDetailPage';
import SuperAdminUsersPage from './pages/SuperAdminUsersPage';
import EvaluationPage from './pages/EvaluationPage';
import CostAnalyticsPage from './pages/CostAnalyticsPage';
import TenantDatabasePage from './pages/TenantDatabasePage';

// Import components
import Navigation from './components/Navigation';
import ProtectedRoute, { AdminRoute, SuperAdminRoute } from './components/ProtectedRoute';
import { ToastProvider } from './components/Toast';
import apiService from './services/apiService';
import { mergeProfileIntoUser } from './utils/user';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is already logged in
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');
    
    if (token && userData) {
      try {
        const user = JSON.parse(userData);
        
        // Validate that user.id is a UUID, not an email
        // If it's an email, try to extract user_id from token
        if (user.id && user.id.includes('@')) {
          console.warn('User ID is an email, attempting to extract UUID from token...');
          try {
            const tokenParts = token.split('.');
            if (tokenParts.length === 3) {
              const payload = JSON.parse(atob(tokenParts[1]));
              if (payload.user_id && !payload.user_id.includes('@')) {
                console.log('Found valid user_id in token, updating user object');
                user.id = payload.user_id;
                // Update localStorage with corrected user data
                localStorage.setItem('user', JSON.stringify(user));
              } else {
                console.error('Token also missing valid user_id, user must log in again');
                // Clear invalid data
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                setLoading(false);
                return;
              }
            }
          } catch (e) {
            console.error('Failed to extract user_id from token:', e);
            // Clear invalid data
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            setLoading(false);
            return;
          }
        }
        
        setIsAuthenticated(true);
        setUser(user);

        // The JWT/local copy doesn't always carry the organization name
        // the user chose at signup — fetch the full profile once per
        // session so the nav can show it instead of a raw tenant_id.
        apiService
          .getProfile()
          .then((profile) => {
            const merged = mergeProfileIntoUser(user, profile);
            setUser(merged);
            localStorage.setItem('user', JSON.stringify(merged));
          })
          .catch(() => {
            // Non-fatal: fall back to whatever we already have locally.
          });
      } catch (e) {
        console.error('Failed to parse user data:', e);
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      }
    }
    
    setLoading(false);
  }, []);

  const handleLogout = () => {
    setIsAuthenticated(false);
    setUser(null);
  };

  if (loading) {
    return (
      <div className="loading-screen" role="status">
        <div className="loading-spinner" aria-hidden="true" />
        <span>Loading Atlas AI…</span>
      </div>
    );
  }

  return (
    <ToastProvider>
      <Router>
        <div className="App">
          {isAuthenticated && <Navigation user={user} onLogout={handleLogout} />}
        
        <Routes>
          {/* Public Routes — redirect away if already signed in, so a
              logged-in user hitting these URLs (back button, stale
              bookmark) doesn't see the nav bar and an auth form at once. */}
          <Route
            path="/login"
            element={
              isAuthenticated ? (
                <Navigate to="/dashboard" replace />
              ) : (
                <LoginPage setIsAuthenticated={setIsAuthenticated} setUser={setUser} />
              )
            }
          />
          <Route
            path="/register"
            element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <RegisterPage />}
          />
          <Route
            path="/tenant/register"
            element={
              isAuthenticated ? (
                <Navigate to="/dashboard" replace />
              ) : (
                <TenantRegistrationPage setIsAuthenticated={setIsAuthenticated} setUser={setUser} />
              )
            }
          />

          {/* Protected Routes */}
          <Route 
            path="/" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated}>
                <DashboardPage user={user} />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/dashboard" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated}>
                <DashboardPage user={user} />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/query" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated}>
                <QueryPage user={user} />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/agent" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated}>
                <AgentPage user={user} />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/ingest" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated}>
                <IngestPage user={user} />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/evaluate" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated}>
                <EvaluationPage user={user} />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/analytics" 
            element={
              <ProtectedRoute isAuthenticated={isAuthenticated}>
                <CostAnalyticsPage user={user} />
              </ProtectedRoute>
            } 
          />
          <Route
            path="/admin"
            element={
              <AdminRoute isAuthenticated={isAuthenticated} user={user}>
                <AdminPanel user={user} />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <AdminRoute isAuthenticated={isAuthenticated} user={user}>
                <AdminUsersPage user={user} />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/database"
            element={
              <AdminRoute isAuthenticated={isAuthenticated} user={user}>
                <TenantDatabasePage />
              </AdminRoute>
            }
          />

          {/* Super Admin Routes */}
          <Route
            path="/super-admin"
            element={
              <SuperAdminRoute isAuthenticated={isAuthenticated} user={user}>
                <SuperAdminDashboardPage user={user} />
              </SuperAdminRoute>
            }
          />
          <Route
            path="/super-admin/tenants"
            element={
              <SuperAdminRoute isAuthenticated={isAuthenticated} user={user}>
                <SuperAdminTenantsPage user={user} />
              </SuperAdminRoute>
            }
          />
          <Route
            path="/super-admin/tenants/:id"
            element={
              <SuperAdminRoute isAuthenticated={isAuthenticated} user={user}>
                <SuperAdminTenantDetailPage user={user} />
              </SuperAdminRoute>
            }
          />
          <Route
            path="/super-admin/users"
            element={
              <SuperAdminRoute isAuthenticated={isAuthenticated} user={user}>
                <SuperAdminUsersPage user={user} />
              </SuperAdminRoute>
            }
          />

          {/* Catch all */}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </div>
    </Router>
    </ToastProvider>
  );
}

export default App;
