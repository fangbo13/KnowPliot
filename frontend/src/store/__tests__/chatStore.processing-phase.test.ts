import { describe, expect, it } from 'vitest';

import { mapServerPhaseForUi } from '../chatStore';

describe('safe server phase compatibility', () => {
  it.each([
    ['accepted', 'connecting', 'accepted'],
    ['retrieving', 'searching', 'searching'],
    ['searching', 'searching', 'searching'],
    ['reasoning', 'streaming', 'generating'],
    ['answering', 'streaming', 'generating'],
    ['generating', 'streaming', 'generating'],
    ['saving', 'completing', 'finalizing'],
    ['finalizing', 'completing', 'finalizing'],
  ])('maps %s to legacy %s and public %s', (serverPhase, streamPhase, safePhase) => {
    expect(mapServerPhaseForUi(serverPhase)).toEqual({ streamPhase, safePhase });
  });
});
