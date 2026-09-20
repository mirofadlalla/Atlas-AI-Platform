import React, { useState, useCallback } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import './Navigation.css';

function Navigation({ user, onLogout }) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = useCallback(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    onLogout();
    navigate('/login');
  }, [onLogout, navigate]);

  const closeMenu = () => setMenuOpen(false);

  const navLinkClass = ({ isActive }) =>
    isActive ? 'nav-link nav-link-active' : 'nav-link';

  const displayName =
    user?.name ||
    user?.email?.split('@')[0] ||
    user?.email ||
    'User';

  return (
    <nav className="navigation" aria-label="Main navigation">
      <div className="nav-left">
        <NavLink to="/dashboard" className="nav-logo" onClick={closeMenu}>
          Atlas AI
        </NavLink>

        {/* Hamburger toggle (mobile only) */}
        <button
          className={`nav-hamburger${menuOpen ? ' open' : ''}`}
          onClick={() => setMenuOpen((prev) => !prev)}
          aria-expanded={menuOpen}
          aria-controls="nav-links-menu"
          aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
        >
          <span className="hamburger-bar" />
          <span className="hamburger-bar" />
          <span className="hamburger-bar" />
        </button>
      </div>

      <div
        id="nav-links-menu"
        className={`nav-links${menuOpen ? ' nav-links-open' : ''}`}
        role="list"
      >
        <NavLink to="/dashboard" className={navLinkClass} onClick={closeMenu} role="listitem">Dashboard</NavLink>
        <NavLink to="/query"     className={navLinkClass} onClick={closeMenu} role="listitem">Query</NavLink>
        <NavLink to="/agent"     className={navLinkClass} onClick={closeMenu} role="listitem">Agent</NavLink>
        <NavLink to="/ingest"    className={navLinkClass} onClick={closeMenu} role="listitem">Ingest Data</NavLink>
        <NavLink to="/evaluate"  className={navLinkClass} onClick={closeMenu} role="listitem">Evaluate</NavLink>
        <NavLink to="/analytics" className={navLinkClass} onClick={closeMenu} role="listitem">Analytics</NavLink>
        {user?.role === 'admin' && (
          <>
            <span className="nav-divider" aria-hidden="true" />
            <NavLink to="/admin"          className={({ isActive }) => `nav-link nav-link-admin${isActive ? ' nav-link-active' : ''}`} onClick={closeMenu} role="listitem">Admin</NavLink>
            <NavLink to="/admin/database" className={({ isActive }) => `nav-link nav-link-admin${isActive ? ' nav-link-active' : ''}`} onClick={closeMenu} role="listitem">Tenant DB</NavLink>
          </>
        )}
      </div>

      <div className="nav-right">
        <div className="user-info" aria-label={`Signed in as ${displayName}`}>
          <span className="user-name">{displayName}</span>
          <span className="user-role">{user?.role}</span>
        </div>
        <button onClick={handleLogout} className="btn-logout">
          Logout
        </button>
      </div>
    </nav>
  );
}

export default Navigation;
