import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export function writeCapacityReport({ artifactDir, profile, sse, restExitCode, startedAt, finishedAt }) {
  fs.mkdirSync(artifactDir, { recursive: true });
  const thresholds = {
    acceptanceP95Ms: 800,
    ordinaryReadP95Ms: 500,
    ordinaryReadP99Ms: 1500,
    firstEventP95Ms: 1500,
    terminalRate: 0.99,
    unexpectedErrorRate: 0.001,
  };
  const passed = restExitCode === 0
    && sse.acceptanceP95Ms <= thresholds.acceptanceP95Ms
    && sse.firstEventP95Ms <= thresholds.firstEventP95Ms
    && sse.terminalRate >= thresholds.terminalRate
    && sse.errors.length === 0;
  const concurrencyObjectivePassed = sse.streams >= 500
    && sse.terminalRate >= thresholds.terminalRate
    && sse.errors.length === 0;
  const summary = {
    profile,
    passed,
    concurrencyObjectivePassed,
    thresholds,
    sse,
    restExitCode,
    startedAt,
    finishedAt,
  };
  fs.writeFileSync(path.join(artifactDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`);
  const markdown = `# KnowPilot capacity report\n\n- Profile: ${profile}\n- Strict SLA result: ${passed ? 'PASS' : 'FAIL'}\n- 500-stream concurrency objective: ${concurrencyObjectivePassed ? 'PASS' : 'FAIL'}\n- Streams: ${sse.streams}\n- Terminal success: ${(sse.terminalRate * 100).toFixed(2)}%\n- Acceptance p95: ${sse.acceptanceP95Ms.toFixed(1)} ms\n- First event p95: ${sse.firstEventP95Ms.toFixed(1)} ms\n- REST thresholds: ${restExitCode === 0 ? 'PASS' : 'FAIL'}\n- Errors: ${sse.errors.length}\n\nThis synthetic-provider result does not certify external model-provider quota.\n`;
  fs.writeFileSync(path.join(artifactDir, 'report.md'), markdown);
  return summary;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  process.stdout.write(`${JSON.stringify(writeCapacityReport(input))}\n`);
}
