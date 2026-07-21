// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { actOnNotification, safeNotificationPath, type FeedItem } from '../notifications';

const invitation: FeedItem = {
  id: 'notification-1',
  kind: 'notification',
  type: 'invitation',
  title: 'Invitation',
  body: 'Join workspace',
  level: 'info',
  link: '/spaces/discover?invitation=invite-1',
  version: '',
  is_read: false,
  created_at: null,
  action_kind: 'space_invitation',
  resource_type: 'space_invitation',
  resource_id: 'invite-1',
  resource_version: 4,
  allowed_actions: ['accept', 'decline'],
  action_state: 'available',
  deep_link: '/spaces/discover?invitation=invite-1',
};

describe('actionable notifications', () => {
  afterEach(() => vi.restoreAllMocks());

  it('submits the server resource version and a fresh idempotency key', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { status: 'accepted' } });

    await actOnNotification(invitation, 'accept');

    expect(post).toHaveBeenCalledWith(
      '/notifications/notification-1/actions/accept/',
      { expected_resource_version: 4 },
      { headers: { 'Idempotency-Key': expect.any(String) } },
    );
  });

  it('refuses stale or disallowed client actions before mutation', async () => {
    const post = vi.spyOn(apiClient, 'post');

    await expect(actOnNotification({ ...invitation, action_state: 'stale', allowed_actions: [] }, 'accept'))
      .rejects.toThrow('notification_action_not_available');
    expect(post).not.toHaveBeenCalled();
  });

  it('allows only same-origin path deep links', () => {
    expect(safeNotificationPath('/spaces/discover?invitation=invite-1')).toBe('/spaces/discover?invitation=invite-1');
    expect(safeNotificationPath('//evil.example/path')).toBeNull();
    expect(safeNotificationPath('https://evil.example/path')).toBeNull();
    expect(safeNotificationPath('/\\evil.example/path')).toBeNull();
  });
});
