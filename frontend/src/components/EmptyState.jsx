import React from 'react';
import './EmptyState.css';

/**
 * EmptyState — standardized empty state component for list/result views.
 * Usage: <EmptyState icon="📋" title="No items yet" description="Add one to get started" />
 */
function EmptyState({ icon = '📭', title, description, action }) {
  return (
    <div className="empty-state-container">
      <div className="empty-state-icon" aria-hidden="true">{icon}</div>
      {title && <h3 className="empty-state-title">{title}</h3>}
      {description && <p className="empty-state-description">{description}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}

export default EmptyState;
