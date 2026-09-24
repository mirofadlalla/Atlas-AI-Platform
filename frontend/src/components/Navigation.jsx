import React, { useState, useCallback } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useTheme } from '../context/ThemeContext';
import { getOrganizationName } from '../utils/user';
import './Navigation.css';

function Navigation({ user, onLogout }) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

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

  const orgName = getOrganizationName(user);

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
            <NavLink to="/admin" end className={({ isActive }) => `nav-link nav-link-admin${isActive ? ' nav-link-active' : ''}`} onClick={closeMenu} role="listitem">Admin</NavLink>
            <NavLink to="/admin/users" className={({ isActive }) => `nav-link nav-link-admin${isActive ? ' nav-link-active' : ''}`} onClick={closeMenu} role="listitem">Users</NavLink>
            <NavLink to="/admin/database" className={({ isActive }) => `nav-link nav-link-admin${isActive ? ' nav-link-active' : ''}`} onClick={closeMenu} role="listitem">Tenant DB</NavLink>
          </>
        )}
        {user?.role === 'super_admin' && (
          <>
            <span className="nav-divider" aria-hidden="true" />
            <NavLink to="/super-admin" end className={({ isActive }) => `nav-link nav-link-super-admin${isActive ? ' nav-link-active' : ''}`} onClick={closeMenu} role="listitem">Super Admin</NavLink>
            <NavLink to="/super-admin/tenants" className={({ isActive }) => `nav-link nav-link-super-admin${isActive ? ' nav-link-active' : ''}`} onClick={closeMenu} role="listitem">Tenants</NavLink>
            <NavLink to="/super-admin/users" className={({ isActive }) => `nav-link nav-link-super-admin${isActive ? ' nav-link-active' : ''}`} onClick={closeMenu} role="listitem">Users</NavLink>
          </>
        )}
      </div>

      <div className="nav-right">
        <button
          type="button"
          onClick={toggleTheme}
          className="theme-toggle"
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? (
            /* Sun icon — shown so the user knows clicking switches to light mode */
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
            </svg>
          ) : (
            /* Moon icon — shown so the user knows clicking switches to dark mode */
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>
        <div className="user-info" aria-label={`Signed in as ${displayName}`}>
          <span className="user-name">{displayName}</span>
          <span className="user-role">
            {user?.role === 'super_admin' ? (
              <span className="badge-super-admin-nav">Super Admin</span>
            ) : (
              <>
                {user?.role}
                {orgName && <span className="user-org"> · {orgName}</span>}
              </>
            )}
          </span>
        </div>
        <button onClick={handleLogout} className="btn-logout">
          Logout
        </button>
      </div>
    </nav>
  );
}

export default Navigation;
