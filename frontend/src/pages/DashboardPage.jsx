import React from 'react';
import { Link } from 'react-router-dom';
import './DashboardPage.css';

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
          <div className="card-action">Start Querying →</div>
        </Link>

        <Link to="/ingest" className="dashboard-card">
          <div className="card-icon">📤</div>
          <h3>Ingest Documents</h3>
          <p>Upload and process files into your knowledge base</p>
          <div className="card-action">Upload Files →</div>
        </Link>

        <Link to="/evaluate" className="dashboard-card">
          <div className="card-icon">📊</div>
          <h3>Evaluate Performance</h3>
          <p>Run evaluations and track RAG pipeline quality metrics</p>
          <div className="card-action">Run Evaluation →</div>
        </Link>

        <Link to="/analytics" className="dashboard-card">
          <div className="card-icon">📈</div>
          <h3>Analytics & Costs</h3>
          <p>Track usage, costs, and performance metrics</p>
          <div className="card-action">View Analytics →</div>
        </Link>

        {user?.role === 'admin' && (
          <Link to="/admin" className="dashboard-card admin-card">
            <div className="card-icon">👨‍💼</div>
            <h3>Admin Panel</h3>
            <p>Manage users, invitations, and approvals</p>
            <div className="card-action">Go to Admin →</div>
          </Link>
        )}
      </div>

      <div className="dashboard-stats">
        <div className="stat-card">
          <h4>Status</h4>
          <p className="stat-value">✅ Active</p>
        </div>
        <div className="stat-card">
          <h4>Role</h4>
          <p className="stat-value">{user?.role}</p>
        </div>
        <div className="stat-card">
          <h4>Tenant</h4>
          <p className="stat-value">{user?.tenant_id}</p>
        </div>
        <div className="stat-card">
          <h4>Approval Status</h4>
          <p className={`stat-value status-${user?.approval_status}`}>
            {user?.approval_status}
          </p>
        </div>
      </div>
    </main>
  );
}

export default DashboardPage;
