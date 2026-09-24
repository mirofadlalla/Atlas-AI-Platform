import React, { useState } from 'react';
import Modal from './Modal';
import Spinner from './Spinner';

function TenantDeleteModal({ isOpen, tenant, onClose, onConfirm }) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState('');

  const handleDelete = async () => {
    if (!tenant) return;
    setIsDeleting(true);
    setError('');
    try {
      await onConfirm(tenant.id);
      onClose();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to delete tenant.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Delete Tenant"
      showCancel={false}
    >
      <div className="modal-dialog-inner">
        {error && (
          <div className="error-banner" role="alert" style={{ marginBottom: '12px' }}>
            {error}
          </div>
        )}

        <p>
          Are you sure you want to permanently delete tenant{' '}
          <strong>{tenant?.name || 'this tenant'}</strong> (<code>{tenant?.id}</code>)?
        </p>
        <p className="text-warning-muted">
          ⚠️ <strong>Warning:</strong> This is a destructive operation. All users (
          {tenant?.user_count !== undefined ? `${tenant.user_count} user${tenant.user_count === 1 ? '' : 's'}` : 'associated users'}
          ) and all tenant data will be permanently cascade-deleted.
        </p>

        <div className="modal-actions-inline">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={onClose}
            disabled={isDeleting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn-danger btn-sm"
            onClick={handleDelete}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <>
                <Spinner size="sm" /> Deleting…
              </>
            ) : (
              'Delete Tenant'
            )}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export default TenantDeleteModal;
