import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  appendToken,
  flushImmediate,
  initTokenBatcher,
  resetTokenBatcher,
} from './TokenBatchRenderer';

describe('TokenBatchRenderer per-session buffers', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    resetTokenBatcher('session-a');
    resetTokenBatcher('session-b');
  });

  it('keeps concurrent session callbacks and content isolated', () => {
    const receivedA: string[] = [];
    const receivedB: string[] = [];
    initTokenBatcher('session-a', 'generation-a', (update) => {
      receivedA.push('appendTokens' in update ? update.appendTokens : update.fullContent);
    });
    initTokenBatcher('session-b', 'generation-b', (update) => {
      receivedB.push('appendTokens' in update ? update.appendTokens : update.fullContent);
    });

    appendToken('session-a', 'generation-a', 'alpha');
    appendToken('session-b', 'generation-b', 'beta');
    flushImmediate('session-a', 'generation-a');
    flushImmediate('session-b', 'generation-b');

    expect(receivedA).toEqual(['alpha']);
    expect(receivedB).toEqual(['beta']);
  });
});
