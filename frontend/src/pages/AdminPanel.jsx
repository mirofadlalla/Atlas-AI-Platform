import React, { useState, useEffect, useCallback } from 'react';
import apiService from '../services/apiService';
import './AdminPanel.css';

function AdminPanel({ user }) {
  const [activeTab, setActiveTab] = useState('invitations'); // 'invitations', 'approvals', 'recommended'
  const [invitations, setInvitations] = useState([]);
  const [pendingUsers, setPendingUsers] = useState([]);
  const [recommendedQA, setRecommendedQA] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [inviteSending, setInviteSending] = useState(false);
  
  // Recommended QA form state
  const [newQuestion, setNewQuestion] = useState('');
  const [newAnswer, setNewAnswer] = useState('');
  const [addingQA, setAddingQA] = useState(false);

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
      const [invData, appData, recData] = await Promise.all([
        apiService.getPendingInvitations().catch(() => ({ invitations: [] })),
        apiService.getPendingApprovals().catch(() => ({ pending_users: [] })),
        apiService.getRecommendedQuestions().catch(() => ({ recommended_qa: [] })),
      ]);
      setInvitations(invData.invitations || []);
      setPendingUsers(appData.pending_users || []);
      setRecommendedQA(recData.recommended_qa || []);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const handleAddRecommendedQA = async (e) => {
    e.preventDefault();
    if (!newQuestion.trim() || !newAnswer.trim()) return;

    if (recommendedQA.length >= 10) {
      alert('Maximum limit of 10 recommended questions reached for this tenant!');
      return;
    }

    setAddingQA(true);
    try {
      await apiService.addRecommendedQuestion(newQuestion, newAnswer);
      alert('Recommended Q&A pair added successfully!');
      setNewQuestion('');
      setNewAnswer('');
      loadData();
    } catch (err) {
      alert('Error adding recommended Q&A: ' + getErrorMessage(err));
    } finally {
      setAddingQA(false);
    }
  };

  const handleDeleteRecommendedQA = async (id) => {
    if (!window.confirm('Are you sure you want to delete this recommended question?')) return;
    try {
      await apiService.deleteRecommendedQuestion(id);
      alert('Deleted successfully!');
      loadData();
    } catch (err) {
      alert('Error deleting recommended Q&A: ' + getErrorMessage(err));
    }
  };

  const handleDeleteInvitation = async (id) => {
    if (!window.confirm('Delete this invitation token? The link will stop working immediately.')) return;
    try { await apiService.deleteInvitation(id); loadData(); }
    catch (err) { alert('Could not delete invitation: ' + getErrorMessage(err)); }
  };

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
        <button
          className={`tab-button ${activeTab === 'recommended' ? 'active' : ''}`}
          onClick={() => setActiveTab('recommended')}
        >
          💡 Recommended Q&A ({recommendedQA.length}/10)
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
                      <button className="btn-danger" onClick={() => handleDeleteInvitation(inv.invitation_id)}>
                        Delete invitation
                      </button>
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

      {activeTab === 'recommended' && (
        <div className="tab-content">
          <div className="send-invitation-form">
            <h3>💡 Add Recommended Question & Answer (Tenant Level, Max 10)</h3>
            <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: '15px' }}>
              These questions will be cached in memory per tenant and automatically presented as recommended/suggested questions when users load the chat interface.
            </p>
            <form onSubmit={handleAddRecommendedQA}>
              <div className="form-group">
                <label htmlFor="rec-question">Question</label>
                <input
                  type="text"
                  id="rec-question"
                  value={newQuestion}
                  onChange={(e) => setNewQuestion(e.target.value)}
                  placeholder="e.g. What is the company policy on remote work?"
                  required
                />
              </div>
              <div className="form-group" style={{ marginTop: '10px' }}>
                <label htmlFor="rec-answer">Answer</label>
                <textarea
                  id="rec-answer"
                  value={newAnswer}
                  onChange={(e) => setNewAnswer(e.target.value)}
                  placeholder="Pre-defined answer text to present or use as guidance..."
                  rows={4}
                  required
                  style={{ width: '100%', background: '#1e293b', color: '#fff', border: '1px solid #334155', borderRadius: '6px', padding: '8px' }}
                />
              </div>
              <button
                type="submit"
                disabled={addingQA || recommendedQA.length >= 10}
                className="btn-primary"
                style={{ marginTop: '10px' }}
              >
                {addingQA ? 'Adding...' : recommendedQA.length >= 10 ? 'Limit Reached (10/10)' : '➕ Add Recommended Q&A'}
              </button>
            </form>
          </div>

          <div className="invitations-list" style={{ marginTop: '20px' }}>
            <h3>📋 Tenant Recommended Questions ({recommendedQA.length}/10)</h3>
            {loading ? (
              <div className="loading">Loading...</div>
            ) : recommendedQA.length > 0 ? (
              <div className="list-items">
                {recommendedQA.map((item) => (
                  <div key={item.id} className="list-item" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
                      <h4 style={{ color: '#6366f1' }}>❓ {item.question}</h4>
                      <button
                        onClick={() => handleDeleteRecommendedQA(item.id)}
                        className="btn-danger"
                        style={{ padding: '4px 10px', fontSize: '0.8rem' }}
                      >
                        🗑️ Delete
                      </button>
                    </div>
                    <div style={{ marginTop: '8px', color: '#cbd5e1', background: '#0f172a', padding: '10px', borderRadius: '6px', width: '100%' }}>
                      <strong>Answer:</strong> {item.answer}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">No recommended questions added for this tenant yet</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminPanel;
