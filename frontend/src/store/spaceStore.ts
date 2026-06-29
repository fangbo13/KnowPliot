/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { create } from 'zustand';
import { spacesApi, type KnowledgeSpace } from '../api/spaces';
import { ACTIVE_SPACE_KEY } from '../api/client';
import { useChatStore } from './chatStore';

interface SpaceState {
  spaces: KnowledgeSpace[];
  activeSpaceId: string | null;
  loading: boolean;
  error: string | null;
  loadSpaces: () => Promise<void>;
  setActiveSpace: (id: string) => Promise<void>;
  joinByCode: (code: string) => Promise<KnowledgeSpace>;
  createSpace: (body: Partial<KnowledgeSpace>) => Promise<KnowledgeSpace>;
  getActiveSpace: () => KnowledgeSpace | null;
}

function persistActive(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_SPACE_KEY, id);
    else localStorage.removeItem(ACTIVE_SPACE_KEY);
  } catch {
    // ignore
  }
}

function readActive(): string | null {
  try {
    return localStorage.getItem(ACTIVE_SPACE_KEY);
  } catch {
    return null;
  }
}

export const useSpaceStore = create<SpaceState>((set, get) => ({
  spaces: [],
  activeSpaceId: readActive(),
  loading: false,
  error: null,

  loadSpaces: async () => {
    set({ loading: true, error: null });
    try {
      const spaces = await spacesApi.list();
      // Keep the current active space if still accessible, else default to first.
      let activeId = get().activeSpaceId;
      if (!activeId || !spaces.some((s) => s.id === activeId)) {
        activeId = spaces[0]?.id ?? null;
        persistActive(activeId);
      }
      set({ spaces, activeSpaceId: activeId, loading: false });
    } catch (e: any) {
      set({ loading: false, error: e?.message ?? 'Failed to load spaces' });
    }
  },

  setActiveSpace: async (id) => {
    if (!id || id === get().activeSpaceId) return;
    persistActive(id);
    set({ activeSpaceId: id });
    // V6.0: switching spaces clears chat context so the previous space's
    // session and messages never leak into the new space.
    try {
      useChatStore.getState().resetSession();
    } catch {
      // ignore
    }
    // Best-effort: record the switch server-side (drives default routing + audit).
    try {
      await spacesApi.switch(id);
    } catch {
      // ignore — switching is a client-side concern; the header already scopes calls
    }
    // Reload the sidebar sessions, now scoped to the new space via X-Space-Id.
    try {
      await useChatStore.getState().loadSessions();
    } catch {
      // ignore
    }
  },

  joinByCode: async (code) => {
    const { space } = await spacesApi.join(code);
    await get().loadSpaces();
    await get().setActiveSpace(space.id);
    return space;
  },

  createSpace: async (body) => {
    const space = await spacesApi.create(body);
    await get().loadSpaces();
    await get().setActiveSpace(space.id);
    return space;
  },

  getActiveSpace: () => {
    const { spaces, activeSpaceId } = get();
    return spaces.find((s) => s.id === activeSpaceId) ?? null;
  },
}));
