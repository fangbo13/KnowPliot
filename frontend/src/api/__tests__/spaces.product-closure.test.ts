import { afterEach, describe, expect, it, vi } from 'vitest';

import { adminApi } from '../admin';
import apiClient from '../client';
import { scopedConsoleApi } from '../scopedConsole';
import { spacesApi } from '../spaces';

describe('workspace product closure APIs', () => {
  afterEach(() => vi.restoreAllMocks());

  it('discovers spaces and submits an access request with a reason', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] });
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { id: 'request-1', status: 'pending' } });

    await spacesApi.discoverable();
    await spacesApi.requestAccess('space-1', { reason: 'Need policy access', role: 'member' });

    expect(get).toHaveBeenCalledWith('/spaces/discoverable/');
    expect(post).toHaveBeenCalledWith('/spaces/space-1/access-requests/', {
      reason: 'Need policy access',
      role: 'member',
    });
  });

  it('uses explicit lifecycle endpoints for restore, clone, and transfers', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });

    await spacesApi.restore('space-1');
    await spacesApi.clone('space-1', { name: 'Clone', code: 'clone', copy_documents: false });
    await spacesApi.transfer('space-1', 'line-2');
    await spacesApi.requestOwnershipTransfer('space-1', {
      to_user_id: 'user-2', expected_ownership_version: 1,
    });

    expect(post.mock.calls.map((call) => call[0])).toEqual([
      '/spaces/space-1/restore/',
      '/spaces/space-1/clone/',
      '/spaces/space-1/transfer/',
      '/spaces/space-1/ownership-transfers/',
    ]);
  });

  it('loads server-authored offboarding impact and submits successor mappings', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { impact_version: 'impact-v1', results: [] } });
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { offboarded: true } });

    await adminApi.offboardingImpact('user-1');
    await adminApi.offboardingAdminSuccessorCandidates('user-1', {
      organization_id: 'org-1', business_line_id: null, role: 'org_admin',
    });
    await adminApi.offboardUser('user-1', {
      impact_version: 'impact-v1',
      reason_code: 'employment_ended',
      space_transfers: [{ space_id: 'space-1', successor_user_id: 'user-2', expected_ownership_version: 1 }],
      admin_successions: [{ organization_id: 'org-1', business_line_id: null, role: 'org_admin', successor_user_id: 'user-2' }],
    });

    expect(get).toHaveBeenCalledWith('/admin/users/user-1/offboarding-impact/');
    expect(get).toHaveBeenCalledWith('/admin/users/user-1/offboarding-admin-candidates/', {
      params: { organization_id: 'org-1', business_line_id: null, role: 'org_admin' },
    });
    expect(post).toHaveBeenCalledWith('/admin/users/user-1/offboard/', expect.objectContaining({
      impact_version: 'impact-v1',
      space_transfers: expect.any(Array),
      admin_successions: expect.any(Array),
    }));
  });

  it('uses the server force-candidate endpoint for offboarding successors', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { results: [] } });

    await spacesApi.ownershipCandidates('space-1', '', 'forced');

    expect(get).toHaveBeenCalledWith('/spaces/space-1/ownership-candidates/', {
      params: { purpose: 'forced', q: '' },
    });
  });

  it('requests subsequent ownership-candidate pages with the server cursor', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { results: [], next: null } });

    await spacesApi.ownershipCandidatePage('space-1', 'sam', 'voluntary', 20);

    expect(get).toHaveBeenCalledWith('/spaces/space-1/ownership-candidates/', {
      params: { purpose: 'voluntary', q: 'sam', offset: 20 },
    });
  });

  it('submits a forced ownership transfer with server-required reason and idempotency', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });

    await spacesApi.forceOwnershipTransfer('space-1', {
      to_user_id: 'user-2', expected_ownership_version: 1, reason_code: 'emergency',
    });

    expect(post).toHaveBeenCalledWith('/spaces/space-1/ownership-transfers/force/', {
      to_user_id: 'user-2', expected_ownership_version: 1, reason_code: 'emergency',
    }, expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }));
  });

  it('lists and responds to only the current user pending ownership transfers', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { results: [] } });
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });

    await spacesApi.pendingOwnershipTransfers();
    await spacesApi.acceptOwnershipTransfer('space-1', 'transfer-1');
    await spacesApi.declineOwnershipTransfer('space-1', 'transfer-1');

    expect(get).toHaveBeenCalledWith('/spaces/ownership-transfers/pending/');
    expect(post.mock.calls.map((call) => call[0])).toEqual([
      '/spaces/space-1/ownership-transfers/transfer-1/accept/',
      '/spaces/space-1/ownership-transfers/transfer-1/decline/',
    ]);
  });

  it('approves access and loads model/governance records through scoped endpoints', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] });
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });

    await scopedConsoleApi.approveAccessRequest('space-1', 'request-1');
    await adminApi.modelProfiles();
    await adminApi.governancePolicies('space-1');

    expect(post).toHaveBeenCalledWith('/admin/spaces/space-1/access-requests/request-1/approve/', {});
    expect(get).toHaveBeenCalledWith('/admin/model-profiles/');
    expect(get).toHaveBeenCalledWith('/admin/governance/policies/', { params: { space: 'space-1' } });
  });
});
