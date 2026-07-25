/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  capabilitiesApi,
  type CapabilitySnapshot,
  type NavigationMode,
} from '../api/capabilities';
import { getRateLimitDetails } from '../api/client';
import { useSpaceStore } from '../store/spaceStore';
import { useAuth } from './AuthProvider';
import {
  CAPABILITY_NAV_ENABLED,
  createAuthorizationAdapter,
  type AuthorizationAdapter,
  type CapabilityStateStatus,
} from './authorization';

interface CapabilityContextValue {
  enabled: boolean;
  status: CapabilityStateStatus;
  snapshot: CapabilitySnapshot | null;
  errorCode: string | null;
  retryAfterSeconds?: number | null;
  resolvedUserId: string | null;
  resolvedSpaceId: string | null;
  expectedNavigationMode: NavigationMode;
  refresh: () => void;
}

const CapabilityContext = createContext<CapabilityContextValue | null>(null);

export function CapabilityProvider({
  children,
  enabled = CAPABILITY_NAV_ENABLED,
}: {
  children: ReactNode;
  enabled?: boolean;
}) {
  const { user } = useAuth();
  const expectedNavigationMode: NavigationMode = enabled ? 'capability' : 'legacy';
  const activeSpaceId = useSpaceStore((state) => state.activeSpaceId);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const requestSequence = useRef(0);
  const [state, setState] = useState<{
    status: CapabilityStateStatus;
    snapshot: CapabilitySnapshot | null;
    errorCode: string | null;
    retryAfterSeconds: number | null;
    resolvedUserId: string | null;
    resolvedSpaceId: string | null;
  }>(() => ({
    status: 'loading',
    snapshot: null,
    errorCode: null,
    retryAfterSeconds: null,
    resolvedUserId: null,
    resolvedSpaceId: null,
  }));

  const refresh = useCallback(() => setRefreshVersion((value) => value + 1), []);

  useEffect(() => {
    const sequence = ++requestSequence.current;
    if (!user?.id) {
      setState({
        status: 'denied',
        snapshot: null,
        errorCode: 'capability_denied',
        retryAfterSeconds: null,
        resolvedUserId: null,
        resolvedSpaceId: null,
      });
      return;
    }

    const requestedUserId = user.id;
    const requestedSpaceId = activeSpaceId;
    const controller = new AbortController();
    setState({
      status: 'loading',
      snapshot: null,
      errorCode: null,
      retryAfterSeconds: null,
      resolvedUserId: null,
      resolvedSpaceId: null,
    });
    const isCurrent = () =>
      !controller.signal.aborted && sequence === requestSequence.current;
    const resolveCapabilities = async () => {
      try {
        let snapshot: CapabilitySnapshot;
        try {
          snapshot = await capabilitiesApi.me(activeSpaceId, controller.signal);
        } catch (error: unknown) {
          const status = (error as { response?: { status?: number } })?.response?.status;
          if (status !== 404 || !requestedSpaceId) throw error;
          snapshot = await capabilitiesApi.me(null, controller.signal);
        }
        if (controller.signal.aborted || sequence !== requestSequence.current) return;
        const navigationMatches = snapshot.navigation_mode === expectedNavigationMode;
        setState({
          status: navigationMatches ? 'ready' : 'mismatch',
          snapshot,
          errorCode: navigationMatches ? null : 'navigation_mode_mismatch',
          retryAfterSeconds: null,
          resolvedUserId: requestedUserId,
          resolvedSpaceId: requestedSpaceId,
        });
      } catch (error: unknown) {
        if (!isCurrent()) return;
        const status = (error as { response?: { status?: number } })?.response?.status;
        const rateLimit = getRateLimitDetails(error);
        if (status === 403 || status === 404) {
          setState({
            status: 'denied',
            snapshot: null,
            errorCode: 'capability_denied',
            retryAfterSeconds: null,
            resolvedUserId: requestedUserId,
            resolvedSpaceId: requestedSpaceId,
          });
        } else {
          setState({
            status: 'error',
            snapshot: null,
            errorCode: rateLimit ? 'rate_limited' : 'capability_unavailable',
            retryAfterSeconds: rateLimit?.retryAfterSeconds ?? null,
            resolvedUserId: requestedUserId,
            resolvedSpaceId: requestedSpaceId,
          });
        }
      }
    };
    void resolveCapabilities();

    return () => controller.abort();
  }, [activeSpaceId, expectedNavigationMode, refreshVersion, user?.id]);

  const value = useMemo<CapabilityContextValue>(
    () => ({ enabled, ...state, expectedNavigationMode, refresh }),
    [enabled, expectedNavigationMode, refresh, state],
  );

  return <CapabilityContext.Provider value={value}>{children}</CapabilityContext.Provider>;
}

export function useCapabilities(): CapabilityContextValue {
  const context = useContext(CapabilityContext);
  if (!context) {
    throw new Error('useCapabilities must be used within CapabilityProvider');
  }
  return context;
}

/** The only active-UI entry point for capability and legacy authorization. */
export function useAuthorization(): AuthorizationAdapter {
  const capabilityState = useCapabilities();
  const { user } = useAuth();
  const activeSpaceId = useSpaceStore((state) => state.activeSpaceId);
  const activeSpaceRole = useSpaceStore(
    (state) =>
      state.spaces.find((space) => space.id === state.activeSpaceId)?.my_role ?? null,
  );

  return useMemo(
    () => {
      // Bug #17 fix: Always check that resolvedSpaceId matches activeSpaceId,
      // even when capability navigation is disabled, to prevent stale
      // capabilities from the previous space leaking through during a switch.
      const spaceIdMatches = capabilityState.resolvedSpaceId === activeSpaceId;
      const userMatches = capabilityState.resolvedUserId === (user?.id ?? null);
      const identityMatches = spaceIdMatches && (capabilityState.enabled ? userMatches : true);
      return createAuthorizationAdapter({
        capabilityNavigationEnabled: capabilityState.enabled,
        status: identityMatches ? capabilityState.status : 'loading',
        snapshot: identityMatches ? capabilityState.snapshot : null,
        legacyUser: user,
        activeSpaceRole,
        activeSpaceId,
      });
    },
    [
      activeSpaceId,
      activeSpaceRole,
      capabilityState.enabled,
      capabilityState.snapshot,
      capabilityState.status,
      capabilityState.resolvedSpaceId,
      capabilityState.resolvedUserId,
      user,
    ],
  );
}
