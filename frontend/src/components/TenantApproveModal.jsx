import React, { useState } from 'react';
import Modal from './Modal';
import Spinner from './Spinner';

function TenantApproveModal({ isOpen, tenant, onClose, onConfirm }) {
  const [note, setNote] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!tenant) return null;

  const handleApprove = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError('');

    try {
      await onConfirm(tenant.id, note.trim());
      setNote('');
      onClose();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to approve tenant.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Approve Organization Workspace"
      showCancel={false}
    >
      <form onSubmit={handleApprove} className="modal-dialog-inner">
        {error && (
          <div className="error-banner" role="alert" style={{ marginBottom: '14px' }}>
            {error}
          </div>
        )}

        <div style={{ marginBottom: '16px', lineHeight: '1.5' }}>
          <p>
            Are you sure you want to approve and activate the organization workspace{' '}
            <strong>{tenant.name}</strong>?
          </p>
          <ul style={{ margin: '10px 0 0 18px', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            <li>Tenant status will be set to <strong>Active</strong>.</li>
            <li>All pending administrator accounts in this tenant will be <strong>Approved</strong>.</li>
            <li>An activation email will be sent notifying the organization admin that they can now log in.</li>
          </ul>
        </div>

        <div className="form-group" style={{ marginBottom: '18px' }}>
          <label htmlFor="approve-note">
            Approval Note <span style={{ color: 'var(--text-tertiary)', fontWeight: 'normal' }}>(optional)</span>
          </label>
          <input
            id="approve-note"
            type="text"
            className="form-control"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Approved per enterprise agreement"
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
            className="btn-primary btn-sm"
            style={{ background: 'var(--color-success, #10b981)', borderColor: 'var(--color-success, #10b981)' }}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <Spinner size="sm" /> Activating…
              </>
            ) : (
              '✓ Approve & Activate'
            )}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default TenantApproveModal;
