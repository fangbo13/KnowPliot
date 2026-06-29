import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token + active space to requests
apiClient.interceptors.request.use((config) => {
  try {
    const saved = localStorage.getItem('ey-auth');
    if (saved) {
      const { token } = JSON.parse(saved);
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
  } catch {
    // ignore
  }
  // V6.0: scope every request to the active knowledge space. The backend reads
  // X-Space-Id and isolates documents / sessions / retrieval to that space.
  const spaceId = getActiveSpaceId();
  if (spaceId) {
    config.headers['X-Space-Id'] = spaceId;
  }
  return config;
});

// Handle 401 responses
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('ey-auth');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

/**
 * Get the current auth token from localStorage.
 * Use this for non-axios requests (e.g., fetch, SSE, Upload components).
 */
export function getAuthToken(): string {
  try {
    const saved = localStorage.getItem('ey-auth');
    if (saved) {
      const { token } = JSON.parse(saved);
      return token || '';
    }
  } catch {
    // ignore
  }
  return '';
}

/** localStorage key holding the active knowledge space id (V6.0). */
export const ACTIVE_SPACE_KEY = 'ey-active-space';

/**
 * Current active space id, used to scope API requests. Returns '' when none is
 * selected (the backend then falls back to the user's default space).
 * Use this for non-axios requests (e.g. SSE fetch) which bypass the interceptor.
 */
export function getActiveSpaceId(): string {
  try {
    return localStorage.getItem(ACTIVE_SPACE_KEY) || '';
  } catch {
    return '';
  }
}

export default apiClient;
