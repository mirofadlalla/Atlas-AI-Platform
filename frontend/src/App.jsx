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
import EvaluationPage from './pages/EvaluationPage';
import CostAnalyticsPage from './pages/CostAnalyticsPage';
import TenantDatabasePage from './pages/TenantDatabasePage';

// Import components
import Navigation from './components/Navigation';
import ProtectedRoute, { AdminRoute } from './components/ProtectedRoute';

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
    return <div className="loading-screen"><div className="loading-spinner">⏳</div> Loading...</div>;
  }

  return (
    <Router>
      <div className="App">
        {isAuthenticated && <Navigation user={user} onLogout={handleLogout} />}
        
        <Routes>
          {/* Public Routes */}
          <Route 
            path="/login" 
            element={<LoginPage setIsAuthenticated={setIsAuthenticated} setUser={setUser} />} 
          />
          <Route 
            path="/register" 
            element={<RegisterPage />} 
          />
          <Route 
            path="/tenant/register" 
            element={<TenantRegistrationPage setIsAuthenticated={setIsAuthenticated} setUser={setUser} />} 
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
          <Route path="/admin/database" element={<AdminRoute isAuthenticated={isAuthenticated} user={user}><TenantDatabasePage /></AdminRoute>} />

          {/* Catch all */}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
