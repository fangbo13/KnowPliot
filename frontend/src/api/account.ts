import apiClient from './client';

export interface AuthSession {
  id: string;
  ip_address: string | null;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
}

export const accountApi = {
  requestPasswordReset(email: string) {
    return apiClient.post('/auth/password/reset/request/', { email });
  },
  confirmPasswordReset(uid: string, token: string, newPassword: string) {
    return apiClient.post('/auth/password/reset/confirm/', {
      uid,
      token,
      new_password: newPassword,
    });
  },
  changePassword(currentPassword: string, newPassword: string) {
    return apiClient.post('/auth/password/change/', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },
  async sessions(): Promise<AuthSession[]> {
    const { data } = await apiClient.get('/auth/sessions/');
    return data;
  },
  revokeSession(id: string) {
    return apiClient.delete(`/auth/sessions/${id}/`);
  },
  revokeOtherSessions() {
    return apiClient.post('/auth/sessions/revoke-others/');
  },
  setupMfa(currentPassword: string) {
    return apiClient.post('/auth/mfa/setup/', {
      current_password: currentPassword,
    });
  },
  confirmMfa(code: string) {
    return apiClient.post('/auth/mfa/confirm/', { code });
  },
  disableMfa(currentPassword: string, code: string) {
    return apiClient.post('/auth/mfa/disable/', {
      current_password: currentPassword,
      code,
    });
  },
  async completeMfa(challenge: string, code: string) {
    const { data } = await apiClient.post('/auth/token/mfa/', { challenge, code });
    return data;
  },
};
