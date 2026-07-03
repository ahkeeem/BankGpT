import { useState, useEffect } from 'react';
import { login as apiLogin, logout as apiLogout, isAuthenticated, getUsername, getOrgId } from './services/api';
import AdminPortal from './components/AdminPortal';
import ChatInterface from './components/ChatInterface';
import './App.css';

export default function App() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated());
  const [activeTab, setActiveTab] = useState('chat');
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);

  useEffect(() => {
    setAuthenticated(isAuthenticated());
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError('');
    setLoginLoading(true);

    try {
      await apiLogin(loginForm.username, loginForm.password);
      setAuthenticated(true);
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    apiLogout();
    setAuthenticated(false);
    setLoginForm({ username: '', password: '' });
  };

  // ---- Login Screen ----
  if (!authenticated) {
    return (
      <div className="login-screen">
        <div className="glass-panel-elevated login-card">
          <div className="login-logo">🧠</div>
          <h1 className="login-title">Knowledge Base</h1>
          <p className="login-subtitle">Sign in to access your AI-powered knowledge assistant</p>

          <form className="login-form" onSubmit={handleLogin}>
            <div className="input-group">
              <label className="input-label" htmlFor="login-username">Username</label>
              <input
                id="login-username"
                type="text"
                className="input"
                placeholder="Enter your username"
                value={loginForm.username}
                onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
                autoComplete="username"
                required
              />
            </div>

            <div className="input-group">
              <label className="input-label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                className="input"
                placeholder="Enter your password"
                value={loginForm.password}
                onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                autoComplete="current-password"
                required
              />
            </div>

            {loginError && <div className="login-error">⚠ {loginError}</div>}

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              disabled={loginLoading || !loginForm.username || !loginForm.password}
              style={{ width: '100%', marginTop: '8px' }}
            >
              {loginLoading ? <><span className="spinner" /> Signing in...</> : 'Sign In'}
            </button>
          </form>

          <div className="login-hint">
            <strong>Demo credentials:</strong><br />
            <code>admin</code> / <code>admin123</code> → org: demo_org<br />
            <code>uba_user</code> / <code>uba123</code> → org: uba
          </div>
        </div>
      </div>
    );
  }

  // ---- Main App ----
  return (
    <div className="app-container">
      {/* Top Navigation */}
      <nav className="top-nav">
        <div className="nav-brand">
          <div className="nav-logo">🧠</div>
          <div className="nav-title">Knowledge <span>Base</span></div>
        </div>

        {/* Tab Switcher */}
        <div className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            💬 Chat
          </button>
          <button
            className={`nav-tab ${activeTab === 'admin' ? 'active' : ''}`}
            onClick={() => setActiveTab('admin')}
          >
            ⚙️ Admin
          </button>
        </div>

        {/* User Info */}
        <div className="nav-user">
          <div className="user-info">
            <div className="user-avatar">👤</div>
            <span>{getUsername()}</span>
          </div>
          <button className="logout-btn" onClick={handleLogout}>
            Sign Out
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <main className="app-content">
        {activeTab === 'chat' ? <ChatInterface /> : <AdminPortal />}
      </main>
    </div>
  );
}
