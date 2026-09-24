import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import apiService from '../services/apiService';
import './TenantRegistrationPage.css';

function TenantRegistrationPage({ setIsAuthenticated, setUser }) {
  const navigate = useNavigate();
  const [organizationName, setOrganizationName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminName, setAdminName] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [agreeToTerms, setAgreeToTerms] = useState(false);

  const validateForm = () => {
    if (!organizationName.trim()) {
      setError('Organization name is required');
      return false;
    }
    if (organizationName.length < 3) {
      setError('Organization name must be at least 3 characters');
      return false;
    }
    if (!adminEmail.includes('@')) {
      setError('Please enter a valid email address');
      return false;
    }
    if (!adminName.trim()) {
      setError('Admin name is required');
      return false;
    }
    if (adminPassword.length < 8) {
      setError('Password must be at least 8 characters');
      return false;
    }
    if (adminPassword !== confirmPassword) {
      setError('Passwords do not match');
      return false;
    }
    if (!agreeToTerms) {
      setError('You must agree to the terms and conditions');
      return false;
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!validateForm()) return;

    setLoading(true);

    try {
      const data = await apiService.registerTenant(
        organizationName,
        adminEmail,
        adminPassword,
        adminName
      );

      // Store authentication
      const resolvedEmail = data.admin_email || adminEmail;
      const resolvedOrg = data.organization_name || organizationName;
      const userData = {
        id: data.admin_id,
        email: resolvedEmail,
        role: 'admin',
        tenant_id: data.tenant_id,
        organization_name: resolvedOrg,
        approval_status: 'approved',
      };

      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user', JSON.stringify(userData));

      setIsAuthenticated(true);
      setUser(userData);

      navigate('/');
    } catch (err) {
      setError(err.message || 'Failed to register organization');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tenant-registration-container">
      <div className="registration-card">
        <div className="registration-header">
          <h1>Create Your Atlas AI Workspace</h1>
          <p>Set up your multi-tenant RAG platform</p>
        </div>

        {error && <div className="error-message">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-section">
            <h3>Organization Details</h3>

            <div className="form-group">
              <label htmlFor="organization">Organization Name</label>
              <input
                type="text"
                id="organization"
                value={organizationName}
                onChange={(e) => setOrganizationName(e.target.value)}
                placeholder="Your Company Name"
                required
              />
              <small>This will be your unique workspace identifier</small>
            </div>
          </div>

          <div className="form-section">
            <h3>Admin Account</h3>

            <div className="form-group">
              <label htmlFor="adminName">Full Name</label>
              <input
                type="text"
                id="adminName"
                value={adminName}
                onChange={(e) => setAdminName(e.target.value)}
                placeholder="Your Full Name"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="adminEmail">Email Address</label>
              <input
                type="email"
                id="adminEmail"
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                placeholder="admin@example.com"
                required
              />
              <small>You'll use this to log in and manage your workspace</small>
            </div>

            <div className="form-group">
              <label htmlFor="adminPassword">Password</label>
              <input
                type="password"
                id="adminPassword"
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                placeholder="Min. 8 characters"
                required
              />
              <small>Use a strong password with numbers and symbols</small>
            </div>

            <div className="form-group">
              <label htmlFor="confirmPassword">Confirm Password</label>
              <input
                type="password"
                id="confirmPassword"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                required
              />
            </div>
          </div>

          <div className="form-group checkbox-group">
            <input
              type="checkbox"
              id="agreeToTerms"
              checked={agreeToTerms}
              onChange={(e) => setAgreeToTerms(e.target.checked)}
            />
            <label htmlFor="agreeToTerms">
              I agree to the Terms & Conditions and Privacy Policy
            </label>
          </div>

          <button type="submit" disabled={loading} className="submit-button">
            {loading ? '⏳ Creating Workspace...' : '✨ Create Workspace'}
          </button>
        </form>

        <div className="registration-footer">
          <p>Already have a workspace? <Link to="/login">Sign in here</Link></p>
        </div>
      </div>

      <div className="registration-info">
        <div className="info-card">
          <h4>🔒 Enterprise Security</h4>
          <p>Multi-tenant isolation, role-based access control, and encrypted data storage</p>
        </div>
        <div className="info-card">
          <h4>📊 Advanced RAG Features</h4>
          <p>Document reranking, cost tracking, and comprehensive analytics dashboard</p>
        </div>
        <div className="info-card">
          <h4>👥 Easy Team Management</h4>
          <p>Invitation-based onboarding and admin approval workflow</p>
        </div>
      </div>
    </div>
  );
}

export default TenantRegistrationPage;
