import { spawnSync } from 'node:child_process';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../..');
const prefix = ['compose', '-p', 'knowpliot-capacity', '-f', 'docker-compose.capacity.yml'];
for (const service of ['web', 'stream-gateway', 'chat-generation-worker']) {
  const result = spawnSync('docker', [...prefix, 'restart', service], {
    cwd: root,
    stdio: 'inherit',
  });
  if (result.status !== 0) throw new Error(`fault_restart_failed:${service}`);
  await new Promise((resolve) => setTimeout(resolve, 10_000));
}
process.stdout.write('fault_injection_complete services=web,stream-gateway,chat-generation-worker\n');
