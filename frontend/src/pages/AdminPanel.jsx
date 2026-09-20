import React, { useState, useEffect, useCallback } from 'react';
import apiService from '../services/apiService';
import Modal from '../components/Modal';
import { useToast } from '../components/Toast';
import './AdminPanel.css';

function AdminPanel({ user }) {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState('invitations');
  const [invitations, setInvitations] = useState([]);
  const [pendingUsers, setPendingUsers] = useState([]);
  const [recommendedQA, setRecommendedQA] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [inviteSending, setInviteSending] = useState(false);
  const [newQuestion, setNewQuestion] = useState('');
  const [newAnswer, setNewAnswer] = useState('');
  const [addingQA, setAddingQA] = useState(false);
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false, title: '', message: '', onConfirm: null, variant: 'danger',
  });
  const [tokenModal, setTokenModal] = useState({ isOpen: false, token: '' });

  // ── helpers defined BEFORE useEffect ────────────────────────────────────────

  const getErrorMessage = (err) => {
    if (typeof err === 'string') return err;
    if (err?.message) return err.message;
    if (err?.data?.detail) {
      const detail = err.data.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail))
        return detail.map((d) =>
          typeof d === 'string' ? d : d.msg || d.message || JSON.stringify(d)
        ).join('; ');
      if (typeof detail === 'object') return JSON.stringify(detail);
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── useEffect AFTER loadData ─────────────────────────────────────────────────
  useEffect(() => {
    if (user?.role !== 'admin') {
      setError('Access denied: Admin only');
      return;
    }
    loadData();
  }, [user, loadData]);

  // ── event handlers ───────────────────────────────────────────────────────────

  const openConfirm = (title, message, onConfirm, variant = 'danger') => {
    setConfirmModal({ isOpen: true, title, message, onConfirm, variant });
  };

  const closeConfirm = () => {
    setConfirmModal((prev) => ({ ...prev, isOpen: false, onConfirm: null }));
  };

  const handleAddRecommendedQA = async (e) => {
    e.preventDefault();
    if (!newQuestion.trim() || !newAnswer.trim()) return;
    if (recommendedQA.length >= 10) {
      toast.warning('Maximum limit of 10 recommended questions reached for this tenant.');
      return;
    }
    setAddingQA(true);
    try {
      await apiService.addRecommendedQuestion(newQuestion, newAnswer);
      toast.success('Recommended Q&A pair added successfully!');
      setNewQuestion('');
      setNewAnswer('');
      loadData();
    } catch (err) {
      toast.error('Error adding recommended Q&A: ' + getErrorMessage(err));
    } finally {
      setAddingQA(false);
    }
  };

  const handleDeleteRecommendedQA = (id) => {
    openConfirm(
      'Delete Recommended Question',
      'Are you sure you want to delete this recommended question? This cannot be undone.',
      async () => {
        try {
          await apiService.deleteRecommendedQuestion(id);
          toast.success('Deleted successfully!');
          loadData();
        } catch (err) {
          toast.error('Error deleting recommended Q&A: ' + getErrorMessage(err));
        }
      }
    );
  };

  const handleDeleteInvitation = (id) => {
    openConfirm(
      'Delete Invitation',
      'Delete this invitation token? The link will stop working immediately.',
      async () => {
        try {
          await apiService.deleteInvitation(id);
          toast.success('Invitation deleted.');
          loadData();
        } catch (err) {
          toast.error('Could not delete invitation: ' + getErrorMessage(err));
        }
      }
    );
  };

  const handleSendInvitation = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setInviteSending(true);
    try {
      const resp = await apiService.sendInvitation(email);
      if (resp && resp.token) {
        setTokenModal({ isOpen: true, token: resp.token });
      } else {
        toast.success('Invitation sent successfully!');
      }
      setEmail('');
      loadData();
    } catch (err) {
      toast.error('Error sending invitation: ' + getErrorMessage(err));
    } finally {
      setInviteSending(false);
    }
  };

  const handleApproveUser = async (userId) => {
    try {
      await apiService.approveUser(userId);
      toast.success('User approved!');
      loadData();
    } catch (err) {
      toast.error('Error approving user: ' + getErrorMessage(err));
    }
  };

  const handleRejectUser = (userId) => {
    openConfirm(
      'Reject User',
      'Are you sure you want to reject this user? They will not be able to access the platform.',
      async () => {
        try {
          await apiService.rejectUser(userId);
          toast.success('User rejected.');
          loadData();
        } catch (err) {
          toast.error('Error rejecting user: ' + getErrorMessage(err));
        }
      }
    );
  };

  const handleCopyToken = async (token) => {
    try {
      await navigator.clipboard?.writeText(token);
      toast.success('Token copied to clipboard!');
    } catch {
      toast.warning('Could not copy automatically — please copy the token manually.');
    }
  };

  // ── early return for non-admins ───────────────────────────────────────────────
  if (user?.role !== 'admin') {
    return (
      <main className="admin-panel">
        <div className="error-page">
          <h1>Access Denied</h1>
          <p>You need admin privileges to access this page.</p>
        </div>
      </main>
    );
  }

  // ── render ────────────────────────────────────────────────────────────────────
  return (
    <main className="admin-panel">
      {/* Confirm Modal */}
      <Modal
        isOpen={confirmModal.isOpen}
        onClose={closeConfirm}
        title={confirmModal.title}
        confirmText="Confirm"
        onConfirm={confirmModal.onConfirm}
        confirmVariant={confirmModal.variant}
        cancelText="Cancel"
      >
        <p>{confirmModal.message}</p>
      </Modal>

      {/* Token display modal */}
      <Modal
        isOpen={tokenModal.isOpen}
        onClose={() => setTokenModal({ isOpen: false, token: '' })}
        title="Invitation Sent"
        showCancel={false}
      >
        <p>Invitation sent! Share this token with the user:</p>
        <div className="token-value" style={{ margin: '12px 0', wordBreak: 'break-all' }}>
          {tokenModal.token}
        </div>
        <button className="btn-copy" onClick={() => handleCopyToken(tokenModal.token)}>
          Copy Token
        </button>
      </Modal>

      <div className="admin-header">
        <h1>Admin Panel</h1>
        <p>Manage user invitations and registrations</p>
      </div>

      {error && <div className="error-banner" role="alert">{error}</div>}

      <div className="admin-container">
        <div className="admin-tabs" role="tablist" aria-label="Admin sections">
          <button
            role="tab"
            id="tab-invitations"
            aria-selected={activeTab === 'invitations'}
            aria-controls="panel-invitations"
            className={`tab-button ${activeTab === 'invitations' ? 'active' : ''}`}
            onClick={() => setActiveTab('invitations')}
          >
            Send Invitations
          </button>
          <button
            role="tab"
            id="tab-approvals"
            aria-selected={activeTab === 'approvals'}
            aria-controls="panel-approvals"
            className={`tab-button ${activeTab === 'approvals' ? 'active' : ''}`}
            onClick={() => setActiveTab('approvals')}
          >
            Approve Users
          </button>
          <button
            role="tab"
            id="tab-recommended"
            aria-selected={activeTab === 'recommended'}
            aria-controls="panel-recommended"
            className={`tab-button ${activeTab === 'recommended' ? 'active' : ''}`}
            onClick={() => setActiveTab('recommended')}
          >
            Recommended Q&amp;A ({recommendedQA.length}/10)
          </button>
        </div>

        {/* ===== INVITATIONS TAB ===== */}
        {activeTab === 'invitations' && (
          <div className="tab-content" role="tabpanel" id="panel-invitations" aria-labelledby="tab-invitations">
            <div className="send-invitation-form">
              <h3>Send User Invitation</h3>
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
                    autoComplete="email"
                  />
                </div>
                <button type="submit" disabled={inviteSending} className="btn-primary">
                  {inviteSending ? 'Sending…' : 'Send Invitation'}
                </button>
              </form>
            </div>

            <div className="invitations-list">
              <h3>Pending Invitations ({invitations.length})</h3>
              {loading ? (
                <div className="loading" aria-live="polite">Loading…</div>
              ) : invitations.length > 0 ? (
                <div className="list-items">
                  {invitations.map((inv) => (
                    <div key={inv.invitation_id} className="list-item">
                      <div className="item-details">
                        <div className="item-header">
                          <h4>{inv.invited_email}</h4>
                          <span className={`status-badge status-${inv.status}`}>{inv.status}</span>
                        </div>
                        <p>Sent: {new Date(inv.created_at).toLocaleDateString()}</p>
                        <p>Expires: {new Date(inv.expires_at).toLocaleDateString()}</p>
                        {inv.token && (
                          <p>
                            Token: <span className="token-value">{inv.token}</span>{' '}
                            <button
                              className="btn-copy"
                              onClick={() => handleCopyToken(inv.token)}
                              aria-label={`Copy token for ${inv.invited_email}`}
                            >
                              Copy
                            </button>
                          </p>
                        )}
                      </div>
                      <div className="item-actions">
                        <button
                          className="btn-danger"
                          onClick={() => handleDeleteInvitation(inv.invitation_id)}
                          aria-label={`Delete invitation for ${inv.invited_email}`}
                        >
                          Delete
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

        {/* ===== APPROVALS TAB ===== */}
        {activeTab === 'approvals' && (
          <div className="tab-content" role="tabpanel" id="panel-approvals" aria-labelledby="tab-approvals">
            <div className="approvals-list">
              <h3>Pending User Approvals ({pendingUsers.length})</h3>
              {loading ? (
                <div className="loading" aria-live="polite">Loading…</div>
              ) : pendingUsers.length > 0 ? (
                <div className="list-items">
                  {pendingUsers.map((pendingUser) => (
                    <div key={pendingUser.user_id} className="list-item">
                      <div className="item-details">
                        <div className="item-header">
                          <h4>{pendingUser.name}</h4>
                        </div>
                        <p className="email">{pendingUser.email}</p>
                        <p>Registered: {new Date(pendingUser.created_at).toLocaleDateString()}</p>
                      </div>
                      <div className="item-actions">
                        <button
                          onClick={() => handleApproveUser(pendingUser.user_id)}
                          className="btn-success"
                          aria-label={`Approve ${pendingUser.name}`}
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleRejectUser(pendingUser.user_id)}
                          className="btn-danger"
                          aria-label={`Reject ${pendingUser.name}`}
                        >
                          Reject
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

        {/* ===== RECOMMENDED Q&A TAB ===== */}
        {activeTab === 'recommended' && (
          <div className="tab-content" role="tabpanel" id="panel-recommended" aria-labelledby="tab-recommended">
            <div className="send-invitation-form">
              <h3>Add Recommended Question &amp; Answer</h3>
              <p className="recommended-desc">
                These questions are cached per tenant and shown as suggestions in the chat interface. Max 10 per tenant.
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
                <div className="form-group">
                  <label htmlFor="rec-answer">Answer</label>
                  <textarea
                    id="rec-answer"
                    value={newAnswer}
                    onChange={(e) => setNewAnswer(e.target.value)}
                    placeholder="Pre-defined answer text…"
                    rows={4}
                    required
                  />
                </div>
                <button
                  type="submit"
                  disabled={addingQA || recommendedQA.length >= 10}
                  className="btn-primary"
                >
                  {addingQA ? 'Adding…' : recommendedQA.length >= 10 ? 'Limit Reached (10/10)' : 'Add Q&A'}
                </button>
              </form>
            </div>

            <div className="invitations-list">
              <h3>Tenant Recommended Questions ({recommendedQA.length}/10)</h3>
              {loading ? (
                <div className="loading" aria-live="polite">Loading…</div>
              ) : recommendedQA.length > 0 ? (
                <div className="list-items">
                  {recommendedQA.map((item) => (
                    <div key={item.id} className="qa-item">
                      <div className="qa-item-header">
                        <p className="qa-question">{item.question}</p>
                        <button
                          onClick={() => handleDeleteRecommendedQA(item.id)}
                          className="btn-danger btn-sm"
                          aria-label={`Delete question: ${item.question}`}
                        >
                          Delete
                        </button>
                      </div>
                      <div className="qa-answer">
                        <span className="qa-answer-label">Answer</span>
                        {item.answer}
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
    </main>
  );
}

export default AdminPanel;
