import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import apiService from '../services/apiService';
import Spinner from '../components/Spinner';
import './RegisterPage.css';

function RegisterPage() {
  const navigate = useNavigate();
  const [invitationToken, setInvitationToken] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isValidating, setIsValidating] = useState(false);
  const [invitationValid, setInvitationValid] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleValidateInvitation = async (e) => {
    e.preventDefault();
    if (!invitationToken) {
      setError('Please enter an invitation token');
      return;
    }
    setIsValidating(true);
    setError('');
    try {
      const response = await apiService.validateInvitation(invitationToken);
      setEmail(response.email);
      setInvitationValid(true);
    } catch (err) {
      setError(err.message || 'Invalid or expired invitation token');
      setInvitationValid(false);
    } finally {
      setIsValidating(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (!password || !invitationToken) {
      setError('Please fill all fields');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await apiService.registerViaInvitation({ token: invitationToken, password });
      navigate('/login', { state: { message: 'Registration successful! Please log in.' } });
    } catch (err) {
      setError(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="register-page">
      <div className="register-container">
        <div className="register-card">
          <div className="register-header">
            <h1>Atlas AI</h1>
            <p>Register via Invitation</p>
          </div>

          <div className="register-body">
            {/* Step indicator */}
            <div className="register-steps" aria-label="Registration steps">
              <div className={`register-step${!invitationValid ? ' active' : ' done'}`}>
                <span className="step-number" aria-hidden="true">{invitationValid ? '✓' : '1'}</span>
                <span className="step-label">Validate Token</span>
              </div>
              <div className="step-connector" aria-hidden="true" />
              <div className={`register-step${invitationValid ? ' active' : ''}`}>
                <span className="step-number" aria-hidden="true">2</span>
                <span className="step-label">Set Password</span>
              </div>
            </div>

            {!invitationValid ? (
              <form onSubmit={handleValidateInvitation} noValidate>
                <div className="form-group">
                  <label htmlFor="token">Invitation Token</label>
                  <input
                    type="text"
                    id="token"
                    value={invitationToken}
                    onChange={(e) => setInvitationToken(e.target.value)}
                    placeholder="Paste your invitation token here"
                    required
                    autoFocus
                    autoComplete="off"
                  />
                  <small>Ask your administrator for an invitation token to register</small>
                </div>

                {error && <div className="error-message" role="alert">{error}</div>}

                <button
                  type="submit"
                  className="btn-primary btn-full"
                  disabled={isValidating}
                >
                  {isValidating ? (
                    <><Spinner size="sm" label="Validating token…" /> Validating…</>
                  ) : (
                    'Validate Token'
                  )}
                </button>
              </form>
            ) : (
              <form onSubmit={handleRegister} noValidate>
                <div className="form-group">
                  <label htmlFor="email">Email</label>
                  <input
                    type="email"
                    id="email"
                    value={email}
                    disabled
                    readOnly
                    aria-readonly="true"
                  />
                  <small>This email was verified via your invitation token</small>
                </div>

                <div className="form-group">
                  <label htmlFor="password">Password</label>
                  <input
                    type="password"
                    id="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Create a strong password (min. 8 characters)"
                    required
                    autoFocus
                    autoComplete="new-password"
                  />
                </div>

                {error && <div className="error-message" role="alert">{error}</div>}

                <button
                  type="submit"
                  className="btn-primary btn-full"
                  disabled={loading}
                >
                  {loading ? (
                    <><Spinner size="sm" label="Creating account…" /> Creating Account…</>
                  ) : (
                    'Create Account'
                  )}
                </button>

                <button
                  type="button"
                  className="btn-secondary btn-full"
                  style={{ marginTop: '8px' }}
                  onClick={() => {
                    setInvitationToken('');
                    setEmail('');
                    setInvitationValid(false);
                    setError('');
                  }}
                >
                  ← Use a Different Token
                </button>
              </form>
            )}

            <p className="register-login-link">
              Already registered? <Link to="/login">Sign in here</Link>
            </p>
          </div>
        </div>

        <aside className="register-info" aria-label="Security features">
          <h3>Secure Registration</h3>
          <ul>
            <li>Invitation-only onboarding</li>
            <li>Admin approval workflow</li>
            <li>Multi-tenant isolation</li>
            <li>Enterprise-grade security</li>
            <li>Role-based access control</li>
          </ul>
        </aside>
      </div>
    </main>
  );
}

export default RegisterPage;
