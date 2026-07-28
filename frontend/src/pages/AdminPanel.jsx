import React, { useState, useEffect, useCallback } from 'react';
import apiService from '../services/apiService';
import './AdminPanel.css';

function AdminPanel({ user }) {
  const [activeTab, setActiveTab] = useState('invitations'); // 'invitations', 'approvals'
  const [invitations, setInvitations] = useState([]);
  const [pendingUsers, setPendingUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [inviteSending, setInviteSending] = useState(false);

  useEffect(() => {
    if (user?.role !== 'admin') {
      setError('Access denied: Admin only');
      return;
    }
    loadData();
  }, [user]);

  const getErrorMessage = (err) => {
    if (typeof err === 'string') return err;
    if (err?.message) return err.message;
    if (err?.data?.detail) {
      const detail = err.data.detail;
      if (typeof detail === 'string') {
        return detail;
      } else if (Array.isArray(detail)) {
        // Handle array of errors (validation errors)
        return detail.map(d => 
          typeof d === 'string' ? d : (d.msg || d.message || JSON.stringify(d))
        ).join('; ');
      } else if (typeof detail === 'object') {
        return JSON.stringify(detail);
      }
    }
    return 'An unknown error occurred';
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [invData, appData] = await Promise.all([
        apiService.getPendingInvitations(),
        apiService.getPendingApprovals(),
      ]);
      setInvitations(invData.invitations || []);
      setPendingUsers(appData.pending_users || []);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSendInvitation = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;

    setInviteSending(true);
    try {
      console.log('Sending invitation for:', email);
      const resp = await apiService.sendInvitation(email);
      // If API returns token immediately, show it; otherwise pending list will include it
      if (resp && resp.token) {
        alert('Invitation sent successfully!\nToken: ' + resp.token);
      } else {
        alert('Invitation sent successfully!');
      }
      setEmail('');
      loadData();
    } catch (err) {
      console.error('Invitation error:', err);
      console.error('Error details:', err.data);
      alert('Error sending invitation: ' + getErrorMessage(err));
    } finally {
      setInviteSending(false);
    }
  };

  const handleApproveUser = async (userId) => {
    try {
      await apiService.approveUser(userId);
      alert('User approved!');
      loadData();
    } catch (err) {
      alert('Error approving user: ' + getErrorMessage(err));
    }
  };

  const handleRejectUser = async (userId) => {
    try {
      await apiService.rejectUser(userId);
      alert('User rejected!');
      loadData();
    } catch (err) {
      alert('Error rejecting user: ' + getErrorMessage(err));
    }
  };

  if (user?.role !== 'admin') {
    return (
      <div className="admin-panel">
        <div className="error-page">
          <h1>❌ Access Denied</h1>
          <p>You need admin privileges to access this page</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-panel">
      <div className="admin-header">
        <h1>👨‍💼 Admin Panel</h1>
        <p>Manage user invitations and registrations</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="admin-tabs">
        <button
          className={`tab-button ${activeTab === 'invitations' ? 'active' : ''}`}
          onClick={() => setActiveTab('invitations')}
        >
          📧 Send Invitations
        </button>
        <button
          className={`tab-button ${activeTab === 'approvals' ? 'active' : ''}`}
          onClick={() => setActiveTab('approvals')}
        >
          ✅ Approve Users
        </button>
      </div>

      {activeTab === 'invitations' && (
        <div className="tab-content">
          <div className="send-invitation-form">
            <h3>📨 Send User Invitation</h3>
            <form onSubmit={handleSendInvitation}>
              <div className="form-group">
                <label htmlFor="email">Email Address</label>
                <input
                  type="email"
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="user@example.com"
                  required
                />
              </div>
              <button type="submit" disabled={inviteSending} className="btn-primary">
                {inviteSending ? 'Sending...' : '📤 Send Invitation'}
              </button>
            </form>
          </div>

          <div className="invitations-list">
            <h3>📋 Pending Invitations ({invitations.length})</h3>
            {loading ? (
              <div className="loading">Loading...</div>
            ) : invitations.length > 0 ? (
              <div className="list-items">
                {invitations.map((inv) => (
                  <div key={inv.invitation_id} className="list-item">
                    <div className="item-header">
                      <h4>✉️ {inv.invited_email}</h4>
                      <span className={`status-badge status-${inv.status}`}>
                        {inv.status}
                      </span>
                    </div>
                    <div className="item-details">
                      <p>Sent: {new Date(inv.created_at).toLocaleDateString()}</p>
                      <p>Expires: {new Date(inv.expires_at).toLocaleDateString()}</p>
                      {inv.token && (
                        <p>
                          Token: <span className="token-value">{inv.token}</span>{' '}
                          <button
                            className="btn-copy"
                            onClick={() => {
                              navigator.clipboard?.writeText(inv.token);
                              alert('Token copied to clipboard');
                            }}
                          >
                            Copy
                          </button>
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">No pending invitations</div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'approvals' && (
        <div className="tab-content">
          <div className="approvals-list">
            <h3>⏳ Pending User Approvals ({pendingUsers.length})</h3>
            {loading ? (
              <div className="loading">Loading...</div>
            ) : pendingUsers.length > 0 ? (
              <div className="list-items">
                {pendingUsers.map((pendingUser) => (
                  <div key={pendingUser.user_id} className="list-item approval-item">
                    <div className="item-header">
                      <div>
                        <h4>👤 {pendingUser.name}</h4>
                        <p className="email">📧 {pendingUser.email}</p>
                      </div>
                    </div>
                    <div className="item-details">
                      <p>Registered: {new Date(pendingUser.created_at).toLocaleDateString()}</p>
                    </div>
                    <div className="item-actions">
                      <button
                        onClick={() => handleApproveUser(pendingUser.user_id)}
                        className="btn-success"
                      >
                        ✅ Approve
                      </button>
                      <button
                        onClick={() => handleRejectUser(pendingUser.user_id)}
                        className="btn-danger"
                      >
                        ❌ Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">No pending approvals</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminPanel;
