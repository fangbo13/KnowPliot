import http from 'node:http';
import { pathToFileURL } from 'node:url';

function numberEnv(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
  } catch {
    return {};
  }
}

function shouldInject(rate, requestNumber) {
  if (rate <= 0) return false;
  if (rate >= 1) return true;
  return requestNumber % Math.max(1, Math.round(1 / rate)) === 0;
}

export function createMockProvider(options = {}) {
  const config = {
    tokenCount: numberEnv(options.tokenCount ?? process.env.MOCK_PROVIDER_TOKEN_COUNT, 32),
    tokenDelayMs: numberEnv(options.tokenDelayMs ?? process.env.MOCK_PROVIDER_TOKEN_DELAY_MS, 20),
    errorRate: numberEnv(options.errorRate ?? process.env.MOCK_PROVIDER_ERROR_RATE, 0),
    disconnectRate: numberEnv(options.disconnectRate ?? process.env.MOCK_PROVIDER_DISCONNECT_RATE, 0),
    embeddingDimensions: numberEnv(options.embeddingDimensions ?? process.env.MOCK_PROVIDER_EMBEDDING_DIMENSIONS, 1024),
  };
  const logger = options.logger ?? (() => {});
  let requestNumber = 0;

  const server = http.createServer(async (request, response) => {
    requestNumber += 1;
    const url = new URL(request.url ?? '/', 'http://mock-provider');
    const body = await readJson(request);
    void body; // Prompts are intentionally never logged.

    if (url.pathname === '/health') {
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end('{"status":"ok"}');
      return;
    }

    if (shouldInject(config.errorRate, requestNumber)) {
      logger({ method: request.method, path: url.pathname, status: 503 });
      response.writeHead(503, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ error: { code: 'mock_provider_unavailable' } }));
      return;
    }

    if (url.pathname === '/v1/embeddings') {
      logger({ method: request.method, path: url.pathname, status: 200 });
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({
        object: 'list',
        model: 'mock-embedding',
        data: [{ object: 'embedding', index: 0, embedding: Array(config.embeddingDimensions).fill(0.01) }],
        usage: { prompt_tokens: 1, total_tokens: 1 },
      }));
      return;
    }

    if (url.pathname === '/v1/chat/completions') {
      logger({ method: request.method, path: url.pathname, status: 200 });
      response.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });
      const disconnect = shouldInject(config.disconnectRate, requestNumber);
      for (let index = 0; index < config.tokenCount; index += 1) {
        const token = `safe-${String(index).padStart(3, '0')} `;
        response.write(`data: ${JSON.stringify({
          id: 'mock-chat',
          object: 'chat.completion.chunk',
          choices: [{ index: 0, delta: { content: token }, finish_reason: null }],
        })}\n\n`);
        if (disconnect && index + 1 >= Math.ceil(config.tokenCount / 2)) {
          response.destroy();
          return;
        }
        if (config.tokenDelayMs) {
          await new Promise((resolve) => setTimeout(resolve, config.tokenDelayMs));
        }
      }
      response.write(`data: ${JSON.stringify({
        id: 'mock-chat',
        object: 'chat.completion.chunk',
        choices: [{ index: 0, delta: {}, finish_reason: 'stop' }],
      })}\n\n`);
      response.end('data: [DONE]\n\n');
      return;
    }

    logger({ method: request.method, path: url.pathname, status: 404 });
    response.writeHead(404, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ error: { code: 'not_found' } }));
  });

  return server;
}

async function main() {
  const port = numberEnv(process.env.MOCK_PROVIDER_PORT, 4010);
  const server = createMockProvider({
    logger: (entry) => process.stdout.write(`${JSON.stringify(entry)}\n`),
  });
  server.listen(port, '0.0.0.0', () => {
    process.stdout.write(`mock_provider_ready port=${port}\n`);
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
