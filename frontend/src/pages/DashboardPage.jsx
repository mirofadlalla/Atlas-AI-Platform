import React from 'react';
import { Link } from 'react-router-dom';
import { getOrganizationName } from '../utils/user';
import './DashboardPage.css';

const ArrowIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);

function DashboardPage({ user }) {
  const displayName =
    user?.name ||
    user?.email?.split('@')[0] ||
    'there';

  return (
    <main className="dashboard-page">
      <div className="dashboard-header">
        <h1>Welcome back, {displayName}!</h1>
        <p>Atlas AI — Multi-tenant RAG Platform</p>
      </div>

      <div className="dashboard-grid">
        <Link to="/query" className="dashboard-card">
          <div className="card-icon">❓</div>
          <h3>Ask Questions</h3>
          <p>Query your documents and get AI-powered answers with reranking</p>
          <div className="card-action">Start querying <ArrowIcon /></div>
        </Link>

        <Link to="/ingest" className="dashboard-card">
          <div className="card-icon">📤</div>
          <h3>Ingest Documents</h3>
          <p>Upload and process files into your knowledge base</p>
          <div className="card-action">Upload files <ArrowIcon /></div>
        </Link>

        <Link to="/evaluate" className="dashboard-card">
          <div className="card-icon">📊</div>
          <h3>Evaluate Performance</h3>
          <p>Run evaluations and track RAG pipeline quality metrics</p>
          <div className="card-action">Run evaluation <ArrowIcon /></div>
        </Link>

        <Link to="/analytics" className="dashboard-card">
          <div className="card-icon">📈</div>
          <h3>Analytics & Costs</h3>
          <p>Track usage, costs, and performance metrics</p>
          <div className="card-action">View analytics <ArrowIcon /></div>
        </Link>

        {user?.role === 'admin' && (
          <Link to="/admin" className="dashboard-card admin-card">
            <div className="card-icon">👨‍💼</div>
            <h3>Admin Panel</h3>
            <p>Manage users, invitations, and approvals</p>
            <div className="card-action">Go to admin <ArrowIcon /></div>
          </Link>
        )}

        {user?.role === 'super_admin' && (
          <Link to="/super-admin" className="dashboard-card admin-card super-admin-card">
            <div className="card-icon">⚡</div>
            <h3>Super Admin</h3>
            <p>Manage platform organizations, global users, and metrics</p>
            <div className="card-action">Go to super admin <ArrowIcon /></div>
          </Link>
        )}
      </div>

      <div className="dashboard-stats">
        <div className="stat-card">
          <h4>Status</h4>
          <p className="stat-value dash-badge dash-badge-success">Active</p>
        </div>
        <div className="stat-card">
          <h4>Role</h4>
          <p className="stat-value">
            {user?.role === 'super_admin' ? 'Super Admin' : user?.role}
          </p>
        </div>
        <div className="stat-card">
          <h4>Tenant</h4>
          <p className="stat-value">
            {user?.role === 'super_admin'
              ? 'Global Platform'
              : getOrganizationName(user) || user?.tenant_id || '—'}
          </p>
        </div>
        <div className="stat-card">
          <h4>Approval Status</h4>
          <p className={`stat-value dash-badge dash-badge-${user?.approval_status || 'approved'}`}>
            {user?.approval_status || 'approved'}
          </p>
        </div>
      </div>
    </main>
  );
}

export default DashboardPage;
