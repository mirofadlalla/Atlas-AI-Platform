import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './Navigation.css';

function Navigation({ user, onLogout }) {
  const navigate = useNavigate();
  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    onLogout();
    navigate('/login');
  };

  return (
    <nav className="navigation">
      <div className="nav-left">
        <Link to="/dashboard" className="nav-logo">Atlas AI</Link>
        <div className="nav-links">
          <Link to="/dashboard">Dashboard</Link><Link to="/query">Query</Link>
          <Link to="/agent">Agent</Link><Link to="/ingest">Ingest Data</Link>
          <Link to="/evaluate">Evaluate</Link><Link to="/analytics">Analytics</Link>
          {user?.role === 'admin' && <><Link to="/admin" className="nav-link-admin">Admin</Link><Link to="/admin/database" className="nav-link-admin">Tenant Database</Link></>}
        </div>
      </div>
      <div className="nav-right"><div className="user-info"><span className="user-name">{user?.email}</span><span className="user-role">{user?.role}</span></div><button onClick={handleLogout} className="btn-logout">Logout</button></div>
    </nav>
  );
}

export default Navigation;
