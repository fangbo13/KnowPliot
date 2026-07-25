import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { writeCapacityReport } from './report-capacity.mjs';

test('reports the 500-stream objective separately from the strict latency SLA', () => {
  const artifactDir = fs.mkdtempSync(path.join(os.tmpdir(), 'knowpilot-capacity-'));
  try {
    const summary = writeCapacityReport({
      artifactDir,
      profile: 'steady',
      sse: {
        streams: 500,
        terminalRate: 1,
        acceptanceP95Ms: 28_000,
        firstEventP95Ms: 500,
        errors: [],
      },
      restExitCode: 0,
      startedAt: '2026-07-22T00:00:00.000Z',
      finishedAt: '2026-07-22T00:02:00.000Z',
    });

    assert.equal(summary.concurrencyObjectivePassed, true);
    assert.equal(summary.passed, false);
    assert.match(
      fs.readFileSync(path.join(artifactDir, 'report.md'), 'utf8'),
      /500-stream concurrency objective: PASS/,
    );
  } finally {
    fs.rmSync(artifactDir, { recursive: true, force: true });
  }
});
