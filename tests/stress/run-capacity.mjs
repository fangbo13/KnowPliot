import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

import { runSseCapacity } from './sse-capacity.mjs';
import { writeCapacityReport } from './report-capacity.mjs';

const ROOT = path.resolve(import.meta.dirname, '../..');
const COMPOSE = ['compose', '-p', 'knowpliot-capacity', '-f', 'docker-compose.capacity.yml'];
const args = new Set(process.argv.slice(2));
const profileName = process.argv[process.argv.indexOf('--profile') + 1] || 'smoke';
const cleanup = args.has('--cleanup');
const profiles = JSON.parse(fs.readFileSync(path.join(import.meta.dirname, 'capacity-profile.json'), 'utf8'));
const profile = profiles[profileName];
if (!profile) throw new Error(`unknown_profile:${profileName}`);

function run(command, commandArgs, options = {}) {
  const result = spawnSync(command, commandArgs, {
    cwd: ROOT,
    encoding: 'utf8',
    stdio: options.capture ? 'pipe' : 'inherit',
    env: { ...process.env, ...options.env },
  });
  if (options.required !== false && result.status !== 0) {
    throw new Error(`${command}_failed:${result.status}`);
  }
  return result;
}

function assertRealProviderGuard() {
  if (profileName !== 'realProvider') return;
  const maxUsers = Number(process.env.REAL_PROVIDER_MAX_USERS);
  if (process.env.ENABLE_REAL_PROVIDER_STRESS !== '1'
    || maxUsers !== 20
    || !process.env.DASHSCOPE_API_KEY
    || profile.users > 20
    || profile.maxInputChars > 300
    || profile.maxOutputTokens > 512) {
    throw new Error('real_provider_guard_rejected');
  }
  process.env.CAPACITY_PROVIDER_KEY = process.env.DASHSCOPE_API_KEY;
  process.env.CAPACITY_LITELLM_BASE_URL = process.env.LITELLM_BASE_URL
    || 'https://dashscope.aliyuncs.com/compatible-mode/v1';
  process.env.CAPACITY_PROVIDER_MAX_OUTPUT_TOKENS = '512';
}

function verifyIsolatedProject() {
  const config = run('docker', [...COMPOSE, 'config', '--format', 'json'], { capture: true });
  const parsed = JSON.parse(config.stdout);
  if (parsed.name !== 'knowpliot-capacity') throw new Error('unsafe_compose_project');
}

const artifactDir = path.join(ROOT, 'artifacts', 'capacity', 'latest');
const startedAt = new Date().toISOString();
let summary;
assertRealProviderGuard();
verifyIsolatedProject();

try {
  run('docker', [...COMPOSE, 'up', '-d', '--no-build']);
  const users = profile.users ?? profile.streams ?? 20;
  run('docker', [...COMPOSE, 'exec', '-T', 'web', 'python', 'manage.py', 'seed_capacity_data',
    '--users', String(Math.max(10, users)), '--spaces', '10', '--sessions-per-user', '20',
    '--messages-per-session', '40', '--notifications-per-user', '2', '--audits-per-user', '1']);

  const streams = Array.isArray(profile.streams) ? Math.max(...profile.streams) : profile.streams ?? profile.users;
  const sse = await runSseCapacity({ baseUrl: 'http://127.0.0.1:18080', streams });
  const durationSeconds = profile.durationSeconds ?? profile.secondsPerStage ?? 120;
  const rest = run('docker', ['run', '--rm', '-i',
    '-e', 'BASE_URL=http://host.docker.internal:18080',
    '-e', `USERS=${Math.max(10, users)}`,
    '-e', `DURATION_SECONDS=${durationSeconds}`,
    // One in five iterations sends a chat request. Keep each synthetic user
    // within the product throttle (at most about two sends per minute).
    '-e', `RATE=${Math.max(1, Math.floor(users / 6))}`,
    '-v', `${path.join(ROOT, 'tests', 'stress')}:/scripts:ro`,
    'grafana/k6:0.54.0', 'run', '/scripts/k6-rest-capacity.js'], { required: false });
  summary = writeCapacityReport({
    artifactDir,
    profile: profileName,
    sse,
    restExitCode: rest.status ?? 1,
    startedAt,
    finishedAt: new Date().toISOString(),
  });
} finally {
  if (cleanup) {
    verifyIsolatedProject();
    run('docker', [...COMPOSE, 'down', '--volumes', '--remove-orphans'], { required: false });
  }
}

process.stdout.write(`${JSON.stringify(summary)}\n`);
if (!summary?.passed) process.exitCode = 1;
