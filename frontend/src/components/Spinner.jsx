import React from 'react';
import './Spinner.css';

/**
 * Accessible CSS spinner — replaces emoji ⏳ used as loading indicators.
 * Usage: <Spinner /> or <Spinner size="lg" label="Saving..." />
 */
function Spinner({ size = 'md', label = 'Loading...' }) {
  return (
    <span className={`spinner spinner-${size}`} role="status">
      <span className="sr-only">{label}</span>
    </span>
  );
}

export default Spinner;
