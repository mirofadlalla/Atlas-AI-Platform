import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import apiService from '../services/apiService';
import './LoginPage.css';

function LoginPage({ setIsAuthenticated, setUser }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [redirectMessage, setRedirectMessage] = useState('');
  const [loading, setLoading] = useState(false);

  // Show a message if the user was automatically redirected (e.g. session expired)
  useEffect(() => {
    const msg = sessionStorage.getItem('auth_redirect_message');
    if (msg) {
      setRedirectMessage(msg);
      sessionStorage.removeItem('auth_redirect_message');
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await apiService.login(email, password);
      
      if (response.access_token) {
        localStorage.setItem('token', response.access_token);
        
        // Decode JWT to get user info (basic decoding)
        let payload;
        try {
          const tokenParts = response.access_token.split('.');
          if (tokenParts.length !== 3) {
            throw new Error('Invalid token format');
          }
          payload = JSON.parse(atob(tokenParts[1]));
        } catch (e) {
          console.error('Failed to decode token:', e);
          setError('Failed to process authentication token. Please try again.');
          return;
        }
        
        // Ensure user_id is present
        if (!payload.user_id) {
          console.error('Token missing user_id:', payload);
          setError('Authentication token is missing required information. Please try logging in again.');
          return;
        }
        
        const userData = {
          email: payload.sub,
          id: payload.user_id, // Map user_id from token to id
          tenant_id: payload.tenant_id,
          role: payload.role || 'user',
          approval_status: payload.approval_status || 'approved',
        };
        
        localStorage.setItem('user', JSON.stringify(userData));
        setUser(userData);
        setIsAuthenticated(true);
        
        navigate('/');
      }
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <h1>🌍 Atlas AI</h1>
          <p>RAG Platform Login</p>
        </div>

        {/* Auto-redirect message (e.g. session expired, account revoked) */}
        {redirectMessage && (
          <div className="info-message" style={{
            background: 'rgba(59, 130, 246, 0.15)',
            border: '1px solid rgba(59, 130, 246, 0.4)',
            borderRadius: '8px',
            padding: '10px 14px',
            marginBottom: '16px',
            color: '#93c5fd',
            fontSize: '0.9rem'
          }}>
            ℹ️ {redirectMessage}
          </div>
        )}

        {error && <div className="error-message">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
            />
          </div>

          <button type="submit" disabled={loading} className="submit-button">
            {loading ? 'Logging in...' : 'Sign In'}
          </button>
        </form>

        <div className="login-footer">
          <p>Don't have an account? <Link to="/register">Register here</Link></p>
          <p style={{ marginTop: '15px', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '15px' }}>
            Creating a new workspace? <Link to="/tenant/register">Create Organization</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
