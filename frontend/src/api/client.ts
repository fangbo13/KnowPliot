import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
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

export default apiClient;
