import assert from 'node:assert/strict';
import test from 'node:test';

import { createMockProvider } from './mock-provider.mjs';

test('mock provider emits exact safe tokens without logging credentials or prompts', async (t) => {
  const logs = [];
  const server = createMockProvider({
    tokenCount: 4,
    tokenDelayMs: 0,
    embeddingDimensions: 8,
    logger: (entry) => logs.push(JSON.stringify(entry)),
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.close());
  const { port } = server.address();
  const secretToken = 'secret-provider-token';
  const secretPrompt = 'private prompt must never be logged';

  const embedding = await fetch(`http://127.0.0.1:${port}/v1/embeddings`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${secretToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: secretPrompt }),
  }).then((response) => response.json());
  assert.equal(embedding.data[0].embedding.length, 8);

  const response = await fetch(`http://127.0.0.1:${port}/v1/chat/completions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${secretToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages: [{ role: 'user', content: secretPrompt }], stream: true }),
  });
  const body = await response.text();
  const tokens = body.split('\n')
    .filter((line) => line.startsWith('data: {'))
    .map((line) => JSON.parse(line.slice(6)).choices[0].delta.content ?? '')
    .join('');

  assert.equal(tokens, 'safe-000 safe-001 safe-002 safe-003 ');
  const serializedLogs = logs.join('\n');
  assert.doesNotMatch(serializedLogs, /secret-provider-token/);
  assert.doesNotMatch(serializedLogs, /private prompt/);
  assert.match(serializedLogs, /\/v1\/chat\/completions/);
});

