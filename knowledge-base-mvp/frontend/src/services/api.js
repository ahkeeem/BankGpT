/**
 * API service layer for the Knowledge Base frontend.
 * Handles auth, ingestion, and chat SSE streaming.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Get stored auth token from localStorage.
 */
function getToken() {
  return localStorage.getItem('kb_token');
}

/**
 * Get stored organization ID.
 */
export function getOrgId() {
  return localStorage.getItem('kb_org_id') || '';
}

/**
 * Build headers with optional auth token.
 */
function authHeaders(extra = {}) {
  const headers = { ...extra };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/* ================================================================
   Authentication
   ================================================================ */

export async function login(username, password) {
  const res = await fetch(`${BASE_URL}/api/v1/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Login failed');
  }

  const data = await res.json();
  localStorage.setItem('kb_token', data.access_token);
  localStorage.setItem('kb_org_id', data.organization_id);
  localStorage.setItem('kb_username', data.username);
  return data;
}

export function logout() {
  localStorage.removeItem('kb_token');
  localStorage.removeItem('kb_org_id');
  localStorage.removeItem('kb_username');
}

export function isAuthenticated() {
  return !!getToken();
}

export function getUsername() {
  return localStorage.getItem('kb_username') || '';
}

/* ================================================================
   Document Ingestion
   ================================================================ */

export async function uploadDocument(file, orgId) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('org_id', orgId);

  const res = await fetch(`${BASE_URL}/api/v1/ingestion/upload`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Upload failed');
  }

  return res.json();
}

export async function ingestUrl(url, orgId) {
  const res = await fetch(`${BASE_URL}/api/v1/ingestion/url`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ url, org_id: orgId }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'URL ingestion failed');
  }

  return res.json();
}

export async function listDocuments(orgId) {
  const res = await fetch(`${BASE_URL}/api/v1/ingestion/documents?org_id=${encodeURIComponent(orgId)}`, {
    headers: authHeaders(),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to list documents');
  }

  return res.json();
}

/* ================================================================
   Chat (SSE Streaming)
   ================================================================ */

/**
 * Stream a chat response using Server-Sent Events.
 *
 * @param {string} organizationId - The org to query against
 * @param {string} question - The user's question
 * @param {function} onToken - Callback for each token: (tokenText) => void
 * @param {function} onSources - Callback for sources: (sourcesArray) => void
 * @param {function} onDone - Callback when stream completes
 * @param {function} onError - Callback on error: (errorMessage) => void
 * @returns {AbortController} - Controller to abort the stream
 */
export function streamChat(organizationId, question, sessionId, { onToken, onSources, onDone, onError }) {
  const controller = new AbortController();

  fetch(`${BASE_URL}/api/v1/chat`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      organization_id: organizationId,
      question,
      stream: true,
      session_id: sessionId || '',
    }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || 'Chat request failed');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();

          if (payload === '[DONE]') {
            onDone?.();
            return;
          }

          try {
            const parsed = JSON.parse(payload);
            if (parsed.token !== undefined) {
              onToken?.(parsed.token);
            }
            if (parsed.sources) {
              onSources?.(parsed.sources);
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }

      onDone?.();
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError?.(err.message);
      }
    });

  return controller;
}
