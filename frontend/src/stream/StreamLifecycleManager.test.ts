import { beforeEach, describe, expect, it } from 'vitest';

import {
  abortActiveStream,
  createStreamAbortController,
} from './StreamLifecycleManager';

describe('StreamLifecycleManager per-session ownership', () => {
  beforeEach(() => {
    abortActiveStream('session-a');
    abortActiveStream('session-b');
  });

  it('does not abort session A when session B starts', () => {
    const controllerA = createStreamAbortController('session-a', 'generation-a');
    const controllerB = createStreamAbortController('session-b', 'generation-b');

    expect(controllerA.signal.aborted).toBe(false);
    expect(controllerB.signal.aborted).toBe(false);
  });

  it('does not abort session A when a non-owner session is deleted', () => {
    const controllerA = createStreamAbortController('session-a', 'generation-a');

    expect(abortActiveStream('session-b')).toBe(false);
    expect(controllerA.signal.aborted).toBe(false);
  });
});
