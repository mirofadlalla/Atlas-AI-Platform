import React, { useState } from 'react';
import Modal from './Modal';
import Spinner from './Spinner';

function TenantRejectModal({ isOpen, tenant, onClose, onConfirm }) {
  const [reason, setReason] = useState('Your registration did not meet our requirements.');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!tenant) return null;

  const handleReject = async (e) => {
    e.preventDefault();
    if (!reason.trim()) {
      setError('Please provide a reason for the rejection.');
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      await onConfirm(tenant.id, reason.trim());
      onClose();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to reject tenant.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Reject Organization Registration"
      showCancel={false}
    >
      <form onSubmit={handleReject} className="modal-dialog-inner">
        {error && (
          <div className="error-banner" role="alert" style={{ marginBottom: '14px' }}>
            {error}
          </div>
        )}

        <div style={{ marginBottom: '16px', lineHeight: '1.5' }}>
          <p>
            Are you sure you want to decline registration for{' '}
            <strong>{tenant.name}</strong>?
          </p>
          <p style={{ color: 'var(--text-warning, #f59e0b)', fontSize: '0.875rem', marginTop: '6px' }}>
            The tenant status will be set to <strong>Rejected</strong>. All member logins for this workspace will remain blocked, and an email notification with your rejection reason will be dispatched to the admin.
          </p>
        </div>

        <div className="form-group" style={{ marginBottom: '18px' }}>
          <label htmlFor="reject-reason">Rejection Reason</label>
          <textarea
            id="reject-reason"
            rows="3"
            className="form-control"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Explain why this organization registration is being rejected…"
            required
            disabled={isSubmitting}
          />
        </div>

        <div className="modal-actions-inline">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn-danger btn-sm"
            disabled={isSubmitting || !reason.trim()}
          >
            {isSubmitting ? (
              <>
                <Spinner size="sm" /> Rejecting…
              </>
            ) : (
              'Decline Registration'
            )}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default TenantRejectModal;
