/**
 * API Service for Atlas AI Frontend
 * Handles all HTTP requests to the backend API
 */

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

class ApiService {
  constructor() {
    this.baseURL = API_BASE_URL;
  }

  // Helper method to get common headers
  getHeaders() {
    const token = localStorage.getItem('token');
    const userStr = localStorage.getItem('user');
    let user = {};
    
    try {
      user = userStr ? JSON.parse(userStr) : {};
    } catch (e) {
      console.warn('Failed to parse user from localStorage:', e);
      user = {};
    }
    
    // Extract user_id from token if not in user object
    let userId = user.id;
    let userRole = user.role;
    let tenantId = user.tenant_id;
    
    if (!userId && token) {
      try {
        // Decode JWT to extract user_id
        const tokenParts = token.split('.');
        if (tokenParts.length !== 3) {
          throw new Error('Invalid token format');
        }
        
        const payload = JSON.parse(atob(tokenParts[1]));
        
        // Try multiple possible field names for user_id (but NOT sub, as that's the email)
        userId = payload.user_id || payload.id || userId;
        userRole = payload.role || userRole;
        tenantId = payload.tenant_id || tenantId;
        
        // Update localStorage with extracted values for future use
        if (userId && !user.id) {
          const updatedUser = { 
            ...user, 
            id: userId, 
            role: userRole || user.role, 
            tenant_id: tenantId || user.tenant_id,
            email: payload.sub || user.email
          };
          localStorage.setItem('user', JSON.stringify(updatedUser));
          // Update local variables
          user = updatedUser;
          userRole = userRole || user.role;
          tenantId = tenantId || user.tenant_id;
        }
      } catch (e) {
        console.warn('Failed to decode token for headers:', e);
        console.warn('Token:', token ? `${token.substring(0, 20)}...` : 'null');
      }
    }
    
    // Validate that userId is actually a UUID, not an email
    // UUIDs are typically in format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (36 chars)
    const isEmail = userId && userId.includes('@');
    
    if (isEmail) {
      console.error('ERROR: User ID appears to be an email address instead of UUID:', userId);
      console.error('User object:', user);
      // Try to extract user_id from token again
      if (token) {
        try {
          const tokenParts = token.split('.');
          if (tokenParts.length === 3) {
            const payload = JSON.parse(atob(tokenParts[1]));
            if (payload.user_id && !payload.user_id.includes('@')) {
              console.warn('Found valid user_id in token, updating...');
              userId = payload.user_id;
              // Update localStorage
              const updatedUser = { ...user, id: userId };
              localStorage.setItem('user', JSON.stringify(updatedUser));
            }
          }
        } catch (e) {
          console.error('Failed to re-extract user_id from token:', e);
        }
      }
    }
    
    // Warn if we still don't have a valid user ID but have a token
    if (!userId || isEmail) {
      console.warn('Warning: Could not extract valid user_id (UUID) from token or localStorage. Some requests may fail.');
      console.warn('User object:', user);
      console.warn('Token exists:', !!token);
      console.warn('Current userId value:', userId);
    }
    
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
    };
    
    // Only add headers if we have valid values (userId must be UUID, not email)
    if (userId && !userId.includes('@')) {
      headers['current-user'] = userId;
    } else if (userId && userId.includes('@')) {
      console.error('CRITICAL: Refusing to send email as user_id. User must log out and log back in.');
    }
    if (userRole) {
      headers['user-role'] = userRole;
    }
    if (tenantId) {
      headers['tenant-id'] = tenantId;
    }
    
    return headers;
  }

  // Authentication endpoints
  async register(email, password, name, tenantName) {
    const response = await fetch(`${this.baseURL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email,
        password,
        name,
        tenant_name: tenantName,
      }),
    });
    return this.handleResponse(response);
  }

  async registerTenant(organizationName, adminEmail, adminPassword, adminName = 'Admin') {
    const response = await fetch(`${this.baseURL}/auth/tenant/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        organization_name: organizationName,
        admin_email: adminEmail,
        admin_password: adminPassword,
        admin_name: adminName,
      }),
    });
    return this.handleResponse(response);
  }

  async login(email, password) {
    const response = await fetch(`${this.baseURL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    return this.handleResponse(response);
  }

  async getProfile() {
    const response = await fetch(`${this.baseURL}/auth/profile`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  // Query endpoints
  async askQuestion(query, sessionId) {
    const response = await fetch(`${this.baseURL}/query/ask`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ query, session_id: sessionId }),
    });
    return {
      ok: response.ok,
      status: response.status,
      body: response.body,
    };
  }

  async retrieveDocuments(query) {
    const response = await fetch(`${this.baseURL}/query/retrieve`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ query }),
    });
    return this.handleResponse(response);
  }

  // File ingestion endpoints
  async uploadFile(file, source, author, recursive = false) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('source', source);
    formData.append('author', author);
    formData.append('recursive', recursive);
    
    const user = JSON.parse(localStorage.getItem('user'));
    formData.append('tenant_id', user.tenant_id);
    formData.append('current_user', user.id);
    formData.append('user_role', user.role);

    const token = localStorage.getItem('token');
    
    // Debug logging
    console.log('Upload file - User data:', { 
      id: user.id, 
      role: user.role, 
      tenant_id: user.tenant_id 
    });

    const response = await fetch(`${this.baseURL}/ingest-rag/upload_file`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
      body: formData,
    });
    return this.handleResponse(response);
  }

  // Evaluation endpoints
  async startEvaluation(file, runs = 2) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('runs', runs);

    const token = localStorage.getItem('token');
    const response = await fetch(`${this.baseURL}/eval/evaluate`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
      body: formData,
    });
    return this.handleResponse(response);
  }

  async getEvaluationStatus(taskId) {
    const response = await fetch(`${this.baseURL}/eval/status/${taskId}`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async generateEvalDataset(maxChunks = 30) {
    const formData = new FormData();
    formData.append('max_chunks', maxChunks);

    const token = localStorage.getItem('token');
    const response = await fetch(`${this.baseURL}/eval/generate_dataset`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
      body: formData,
    });
    return this.handleResponse(response);
  }

  // Invitation endpoints
  async sendInvitation(email) {
    const response = await fetch(`${this.baseURL}/auth/invitations/send`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        invited_email: email,
      }),
    });
    return this.handleResponse(response);
  }

  async validateInvitation(token) {
    const response = await fetch(`${this.baseURL}/auth/invitations/validate?token=${token}`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async registerViaInvitation(token, name, password, tenantId) {
    const response = await fetch(`${this.baseURL}/auth/register-via-invitation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        token,
        name,
        password,
        tenant_id: tenantId,
      }),
    });
    return this.handleResponse(response);
  }

  async getPendingInvitations() {
    const response = await fetch(`${this.baseURL}/auth/invitations/pending`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async resendInvitation(token) {
    const response = await fetch(`${this.baseURL}/auth/invitations/resend`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ token }),
    });
    return this.handleResponse(response);
  }

  // Admin approval endpoints
  async getPendingApprovals() {
    const response = await fetch(`${this.baseURL}/auth/pending-approvals`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async approveUser(userId) {
    const response = await fetch(`${this.baseURL}/auth/approve-user/${userId}`, {
      method: 'POST',
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async rejectUser(userId) {
    const response = await fetch(`${this.baseURL}/auth/reject-user/${userId}`, {
      method: 'POST',
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  // Analytics endpoints
  async getCostAnalytics() {
    const response = await fetch(`${this.baseURL}/query/cost-analytics`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async getRuns() {
    const response = await fetch(`${this.baseURL}/query/runs`, {
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  // Agent endpoints
  async askAgent(question, tenantId, sessionId) {
    const response = await fetch(`${this.baseURL}/agent/ask-agent`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        question,
        session_id: sessionId,
      }),
    });
    
    return {
      ok: response.ok,
      status: response.status,
      body: response.body,
    };
  }

  async askAgentBatch(question, tenantId, sessionId) {
    const response = await fetch(`${this.baseURL}/agent/ask-agent-batch`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        question,
        session_id: sessionId,
      }),
    });
    return this.handleResponse(response);
  }

  // Recommended Q&A Endpoints
  async getRecommendedQuestions() {
    const response = await fetch(`${this.baseURL}/recommended-qa`, {
      method: 'GET',
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async addRecommendedQuestion(question, answer) {
    const response = await fetch(`${this.baseURL}/recommended-qa`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ question, answer }),
    });
    return this.handleResponse(response);
  }

  async deleteRecommendedQuestion(qaId) {
    const response = await fetch(`${this.baseURL}/recommended-qa/${qaId}`, {
      method: 'DELETE',
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  // Helper method to handle responses
  async handleResponse(response) {
    // ── 401 Unauthorized: token expired or invalid ─────────────────────────
    // Clear stored credentials and redirect to login so the user can
    // re-authenticate. Pass a message via sessionStorage so the login page
    // can display a friendly explanation.
    if (response.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      sessionStorage.setItem(
        'auth_redirect_message',
        'Your session has expired. Please log in again.'
      );
      window.location.href = '/login';
      // Return a pending promise — the page is navigating away anyway.
      return new Promise(() => {});
    }

    // ── 403 Forbidden: account approval revoked mid-session ────────────────
    // The backend now checks approval_status on every request, so a user
    // whose account was rejected after login will start getting 403s.
    // We check the detail message to distinguish a real 403 (e.g. "not admin")
    // from a session-revocation 403 ("Account is not approved").
    if (response.status === 403) {
      try {
        const body = await response.clone().json();
        const detail = (body.detail || '').toLowerCase();
        if (detail.includes('not approved') || detail.includes('awaiting')) {
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          sessionStorage.setItem(
            'auth_redirect_message',
            'Your account access has been revoked. Please contact your administrator.'
          );
          window.location.href = '/login';
          return new Promise(() => {});
        }
      } catch (_) {
        // If we can't parse the body just fall through to normal error handling
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      console.error(`API Error [${response.status}]:`, error);

      // Extract meaningful error message
      let errorMessage = 'Unknown error';
      if (typeof error.detail === 'string') {
        errorMessage = error.detail;
      } else if (error.detail && typeof error.detail === 'object') {
        console.error('Error detail is object:', error.detail);
        errorMessage = error.detail.message || JSON.stringify(error.detail);
      } else if (error.message) {
        errorMessage = error.message;
      }

      const customError = new Error(errorMessage);
      customError.status = response.status;
      customError.data = error;
      throw customError;
    }
    return response.json().catch(() => ({}));
  }
}

const apiService = new ApiService();
export default apiService;
