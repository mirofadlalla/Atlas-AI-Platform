import React, { useState, useEffect } from 'react';
import Modal from './Modal';
import Spinner from './Spinner';

const STANDARD_PLANS = ['Free', 'Starter', 'Pro', 'Enterprise'];

function TenantEditModal({ isOpen, tenant, onClose, onSave }) {
  const [name, setName] = useState('');
  const [plan, setPlan] = useState('Free');
  const [isCustomPlan, setIsCustomPlan] = useState(false);
  const [customPlan, setCustomPlan] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (tenant) {
      setName(tenant.name || '');
      const currentPlan = tenant.plan || 'Free';
      if (STANDARD_PLANS.includes(currentPlan)) {
        setPlan(currentPlan);
        setIsCustomPlan(false);
        setCustomPlan('');
      } else {
        setPlan('custom');
        setIsCustomPlan(true);
        setCustomPlan(currentPlan);
      }
      setError('');
    }
  }, [tenant]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Tenant name is required.');
      return;
    }

    const finalPlan = isCustomPlan ? customPlan.trim() || 'Free' : plan;

    setIsSubmitting(true);
    setError('');

    try {
      await onSave(tenant.id, {
        name: name.trim(),
        plan: finalPlan,
      });
      onClose();
    } catch (err) {
      const msg = err?.data?.detail || err?.message || 'Failed to update tenant.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePlanChange = (e) => {
    const val = e.target.value;
    if (val === 'custom') {
      setIsCustomPlan(true);
      setPlan('custom');
    } else {
      setIsCustomPlan(false);
      setPlan(val);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Edit Tenant: ${tenant?.name || ''}`}
      showCancel={false}
    >
      <form onSubmit={handleSubmit} className="modal-dialog-inner">
        {error && (
          <div className="error-banner" role="alert" style={{ marginBottom: '12px' }}>
            {error}
          </div>
        )}

        <div className="form-group">
          <label htmlFor="tenant-edit-name">Tenant / Organization Name</label>
          <input
            id="tenant-edit-name"
            type="text"
            className="form-control"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme Corp"
            required
            autoFocus
          />
        </div>

        <div className="form-group">
          <label htmlFor="tenant-edit-plan">Subscription Plan</label>
          <select
            id="tenant-edit-plan"
            className="form-control"
            value={isCustomPlan ? 'custom' : plan}
            onChange={handlePlanChange}
          >
            {STANDARD_PLANS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
            <option value="custom">Custom Plan…</option>
          </select>
        </div>

        {isCustomPlan && (
          <div className="form-group">
            <label htmlFor="tenant-custom-plan">Custom Plan Name</label>
            <input
              id="tenant-custom-plan"
              type="text"
              className="form-control"
              value={customPlan}
              onChange={(e) => setCustomPlan(e.target.value)}
              placeholder="e.g. Enterprise Plus"
              required
            />
          </div>
        )}

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
            disabled={isSubmitting || !name.trim()}
          >
            {isSubmitting ? (
              <>
                <Spinner size="sm" /> Saving…
              </>
            ) : (
              'Save Changes'
            )}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default TenantEditModal;
