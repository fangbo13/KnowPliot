/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { create } from 'zustand';
import { spacesApi, type KnowledgeSpace, type JoinResult } from '../api/spaces';
import { ACTIVE_SPACE_KEY, isAbortError } from '../api/client';
import { useChatStore } from './chatStore';

interface SpaceState {
  spaces: KnowledgeSpace[];
  activeSpaceId: string | null;
  loading: boolean;
  error: string | null;
  loadSpaces: (signal?: AbortSignal) => Promise<void>;
  setActiveSpace: (id: string, signal?: AbortSignal) => Promise<void>;
  joinByCode: (code: string, signal?: AbortSignal) => Promise<JoinResult>;
  createSpace: (body: Partial<KnowledgeSpace>, signal?: AbortSignal) => Promise<KnowledgeSpace>;
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

let spaceLoadGeneration = 0;
let spaceLoadController: AbortController | null = null;

export const useSpaceStore = create<SpaceState>((set, get) => ({
  spaces: [],
  activeSpaceId: readActive(),
  loading: false,
  error: null,

  loadSpaces: async (signal) => {
    const generation = ++spaceLoadGeneration;
    spaceLoadController?.abort();
    const controller = new AbortController();
    spaceLoadController = controller;
    const forwardAbort = () => controller.abort();
    signal?.addEventListener('abort', forwardAbort, { once: true });
    set({ loading: true, error: null });
    try {
      const spaces = await spacesApi.list(controller.signal);
      if (controller.signal.aborted || generation !== spaceLoadGeneration) return;
      // Keep the current active space if still accessible, else default to first.
      let activeId = get().activeSpaceId;
      if (!activeId || !spaces.some((s) => s.id === activeId)) {
        activeId = spaces[0]?.id ?? null;
        persistActive(activeId);
      }
      set({ spaces, activeSpaceId: activeId, loading: false });
    } catch (e: any) {
      if (isAbortError(e) || controller.signal.aborted || generation !== spaceLoadGeneration) return;
      set({ loading: false, error: e?.message ?? 'Failed to load spaces' });
      throw e;
    } finally {
      signal?.removeEventListener('abort', forwardAbort);
      if (spaceLoadController === controller) {
        spaceLoadController = null;
        if (generation === spaceLoadGeneration) set({ loading: false });
      }
    }
  },

  setActiveSpace: async (id, signal) => {
    if (signal?.aborted || !id || id === get().activeSpaceId) return;
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
      await spacesApi.switch(id, signal);
    } catch {
      if (signal?.aborted) return;
      // ignore — switching is a client-side concern; the header already scopes calls
    }
    // Reload the sidebar sessions, now scoped to the new space via X-Space-Id.
    try {
      if (!signal?.aborted) await useChatStore.getState().loadSessions();
    } catch {
      // ignore
    }
  },

  joinByCode: async (code, signal) => {
    if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');
    return spacesApi.join(code, signal);
  },

  createSpace: async (body, signal) => {
    if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');
    const space = await spacesApi.create(body, signal);
    await get().loadSpaces(signal);
    await get().setActiveSpace(space.id, signal);
    return space;
  },

  getActiveSpace: () => {
    const { spaces, activeSpaceId } = get();
    return spaces.find((s) => s.id === activeSpaceId) ?? null;
  },
}));
