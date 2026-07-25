/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import i18n from '../i18n';

/**
 * Map a caught error to a user-friendly i18n message.
 * Technical details are logged to console but never shown to users.
 *
 * Handles various error shapes: TypeError (network), fetch Response,
 * axios-style { response: { status } }, or plain Error.
 */
export function getErrorMessage(err: unknown): string {
  // Network-level error (fetch failed, CORS, offline)
  if (err instanceof TypeError) {
    console.error('[errorMessages] Network error:', err);
    return i18n.t('error_network');
  }

  // Try to extract HTTP status from various error shapes
  const status =
    (err as any)?.status ??
    (err as any)?.response?.status ??
    (err as any)?.statusCode;

  if (status === 401) {
    console.error('[errorMessages] Auth expired:', err);
    return i18n.t('error_auth_expired');
  }
  if (status === 403) {
    console.error('[errorMessages] Permission denied:', err);
    return i18n.t('error_permission_denied');
  }
  if (status === 404) {
    console.error('[errorMessages] Not found:', err);
    return i18n.t('error_not_found');
  }
  if (status === 429) {
    console.error('[errorMessages] Rate limited:', err);
    return i18n.t('error_rate_limited');
  }
  if (status && status >= 500) {
    console.error('[errorMessages] Server error:', err);
    return i18n.t('error_server');
  }

  console.error('[errorMessages] Unknown error:', err);
  return i18n.t('error_generic');
}

/**
 * Get a user-friendly error message from a fetch Response object.
 * Use this when you have `if (!response.ok)` in your fetch handler.
 */
export function getResponseErrorMessage(response: Response): string {
  if (response.status === 401) return i18n.t('error_auth_expired');
  if (response.status === 403) return i18n.t('error_permission_denied');
  if (response.status === 404) return i18n.t('error_not_found');
  if (response.status === 429) return i18n.t('error_rate_limited');
  if (response.status >= 500) return i18n.t('error_server');
  return i18n.t('error_generic');
}
