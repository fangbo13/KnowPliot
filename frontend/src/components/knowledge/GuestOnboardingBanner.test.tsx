// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { spacesApi } from '../../api/spaces';
import GuestOnboardingBanner from './GuestOnboardingBanner';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../../api/spaces', () => ({ spacesApi: { completeOnboarding: vi.fn() } }));

describe('GuestOnboardingBanner', () => {
  it('upgrades the guest and refreshes space authorization', async () => {
    vi.mocked(spacesApi.completeOnboarding).mockResolvedValue({ role: 'member' } as never);
    const onCompleted = vi.fn().mockResolvedValue(undefined);
    render(<GuestOnboardingBanner spaceId="space-1" onCompleted={onCompleted} />);

    fireEvent.click(screen.getByRole('button', { name: /guest_onboarding_start/ }));
    await waitFor(() => expect(spacesApi.completeOnboarding).toHaveBeenCalledWith('space-1'));
    expect(onCompleted).toHaveBeenCalled();
  });
});
