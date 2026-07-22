import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';

const PASSWORD = 'CapacityOnly!2026';

function percentile(values, percentileValue) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil(percentileValue * sorted.length) - 1)];
}

async function jsonRequest(url, init = {}) {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => ({}));
  return { response, body };
}

async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const index = next++;
      results[index] = await fn(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

async function identity(baseUrl, index) {
  const email = `capacity${String(index).padStart(5, '0')}@example.invalid`;
  const login = await jsonRequest(`${baseUrl}/api/v1/auth/token/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  if (!login.response.ok || !login.body.access) throw new Error(`login_failed:${login.response.status}`);
  const auth = { Authorization: `Bearer ${login.body.access}` };
  const spacesResult = await jsonRequest(`${baseUrl}/api/v1/spaces/`, { headers: auth });
  const spaces = spacesResult.body.results ?? spacesResult.body;
  const spaceId = spaces?.[0]?.id;
  if (!spaceId) throw new Error('space_missing');
  const headers = { ...auth, 'X-Space-Id': spaceId };
  const sessionsResult = await jsonRequest(`${baseUrl}/api/v1/chat/sessions/`, { headers });
  const sessions = sessionsResult.body.results ?? sessionsResult.body;
  const sessionId = sessions?.[0]?.id;
  if (!sessionId) throw new Error('session_missing');
  return { headers, sessionId };
}

async function consumeEvents(baseUrl, accepted, headers, controlledDisconnect) {
  let after = 0;
  let firstEventMs = null;
  const started = performance.now();
  const seen = new Set();
  const answerChunks = new Set();
  let terminals = 0;
  let terminalName = null;
  let reconnected = false;
  let reconnectAttempts = 0;

  while (terminals === 0) {
    const controller = new AbortController();
    const response = await fetch(`${baseUrl}${accepted.events_url}?after=${after}`, {
      headers: { ...headers, Accept: 'text/event-stream', 'Last-Event-ID': String(after) },
      signal: controller.signal,
    });
    if (!response.ok || !response.body) throw new Error(`events_failed:${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let shouldReconnect = false;
    let streamEnded = false;
    while (true) {
      const { done, value } = await reader.read();
      streamEnded = done;
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() ?? '';
      for (const block of blocks) {
        const lines = block.split('\n');
        const idLine = lines.find((line) => line.startsWith('id:'));
        const eventLine = lines.find((line) => line.startsWith('event:'));
        const dataLine = lines.find((line) => line.startsWith('data:'));
        if (!idLine || !eventLine || !dataLine) continue;
        const id = Number(idLine.slice(3).trim());
        const event = eventLine.slice(6).trim();
        const data = JSON.parse(dataLine.slice(5).trim());
        if (!Number.isSafeInteger(id) || id <= after || seen.has(id)) throw new Error('duplicate_or_non_monotonic_event');
        seen.add(id);
        after = id;
        firstEventMs ??= performance.now() - started;
        if (event === 'answer_delta') {
          if (answerChunks.has(data.text)) throw new Error('duplicate_answer_delta');
          answerChunks.add(data.text);
        }
        if (event === 'done' || event === 'error') {
          terminals += 1;
          terminalName = event;
        }
        if (controlledDisconnect && !reconnected && terminals === 0) {
          reconnected = true;
          shouldReconnect = true;
          controller.abort();
          break;
        }
      }
      if (shouldReconnect || done || terminals) break;
    }
    if (terminals === 0) {
      if (!shouldReconnect && !streamEnded) throw new Error('stream_ended_without_terminal');
      reconnectAttempts += 1;
      reconnected = true;
      if (reconnectAttempts > 30 || performance.now() - started > 300_000) {
        throw new Error('stream_reconnect_exhausted');
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
  if (terminals !== 1) throw new Error('terminal_count_invalid');
  if (terminalName !== 'done') throw new Error('generation_terminal_error');
  return { firstEventMs, eventCount: seen.size, reconnected };
}

export async function runSseCapacity({ baseUrl, streams, loginConcurrency = 25 }) {
  const indexes = Array.from({ length: streams }, (_, index) => index);
  const identities = await mapLimit(indexes, loginConcurrency, (_, index) => identity(baseUrl, index));
  const acceptanceMs = [];
  const firstEventMs = [];
  let successes = 0;
  const errors = [];
  await mapLimit(identities, streams, async (entry, index) => {
    try {
      const started = performance.now();
      const acceptedResult = await jsonRequest(`${baseUrl}/api/v1/chat/sessions/${entry.sessionId}/send/`, {
        method: 'POST',
        headers: { ...entry.headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: `Synthetic capacity request ${index}`,
          client_request_id: crypto.randomUUID(),
          answer_mode: 'fast',
          thinking_enabled: false,
          protocol_version: 3,
        }),
      });
      acceptanceMs.push(performance.now() - started);
      if (acceptedResult.response.status !== 202) {
        const code = acceptedResult.body?.code ?? acceptedResult.body?.detail ?? 'unknown';
        throw new Error(`accept_failed:${acceptedResult.response.status}:${code}`);
      }
      const result = await consumeEvents(baseUrl, acceptedResult.body, entry.headers, index === 0);
      firstEventMs.push(result.firstEventMs);
      successes += 1;
    } catch (error) {
      errors.push(String(error?.message ?? error));
    }
  });
  return {
    streams,
    successes,
    terminalRate: streams ? successes / streams : 0,
    acceptanceP95Ms: percentile(acceptanceMs, 0.95),
    firstEventP95Ms: percentile(firstEventMs, 0.95),
    errors,
  };
}

async function main() {
  const summary = await runSseCapacity({
    baseUrl: process.env.BASE_URL ?? 'http://127.0.0.1:18080',
    streams: Number(process.env.STREAMS ?? 2),
  });
  process.stdout.write(`${JSON.stringify(summary)}\n`);
  if (summary.acceptanceP95Ms > 800
    || summary.firstEventP95Ms > 1500
    || summary.terminalRate < 0.99
    || summary.errors.length) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
