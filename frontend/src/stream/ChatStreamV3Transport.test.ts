import { describe, expect, it, vi } from 'vitest';

import {
  ChatStreamV3Transport,
  type AcceptedChatTurnV3,
} from './ChatStreamV3Transport';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';
const CLIENT_ID = '22222222-2222-4222-8222-222222222222';
const TURN_ID = '33333333-3333-4333-8333-333333333333';
const MESSAGE_ID = '44444444-4444-4444-8444-444444444444';

const accepted: AcceptedChatTurnV3 = {
  turn_id: TURN_ID,
  session_id: SESSION_ID,
  client_request_id: CLIENT_ID,
  status: 'accepted',
  events_url: `/api/v1/chat/turns/${TURN_ID}/events/`,
  status_url: `/api/v1/chat/turns/${TURN_ID}/`,
  cancel_url: `/api/v1/chat/turns/${TURN_ID}/cancel/`,
};

function jsonResponse(body: unknown, status = 202, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

function sseResponse(body: string, status = 200) {
  return new Response(body, {
    status,
    headers: {
      'Content-Type': 'text/event-stream',
      'X-Chat-Turn-Id': TURN_ID,
      'X-Chat-Client-Request-Id': CLIENT_ID,
    },
  });
}

function doneEvent(id: number) {
  return `id: ${id}\nevent: done\ndata: ${JSON.stringify({
    message_id: MESSAGE_ID,
    session_id: SESSION_ID,
    turn_id: TURN_ID,
    client_request_id: CLIENT_ID,
    model: 'safe-model',
  })}\n\n`;
}

function transport(fetchMock: ReturnType<typeof vi.fn>, sleep = vi.fn(async () => {})) {
  return new ChatStreamV3Transport({
    fetch: fetchMock as typeof fetch,
    baseUrl: '/api/v1',
    getAuthToken: () => 'token-a',
    getSpaceId: () => 'space-a',
    sleep,
  });
}

describe('ChatStreamV3Transport', () => {
  it('accepts 202 then resumes SSE from the last confirmed sequence', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(accepted))
      .mockResolvedValueOnce(sseResponse(doneEvent(8)));
    const onEvent = vi.fn();
    const client = transport(fetchMock);

    const turn = await client.accept({
      sessionId: SESSION_ID,
      content: 'hello',
      clientRequestId: CLIENT_ID,
      answerMode: 'fast',
      thinkingEnabled: false,
    });
    const terminal = await client.consume(turn, { after: 7, onEvent });

    expect(turn).toEqual(accepted);
    expect(terminal).toMatchObject({ kind: 'done', after: 8 });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `${accepted.events_url}?after=7`,
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer token-a',
          'X-Space-Id': 'space-a',
          'Last-Event-ID': '7',
        }),
      }),
    );
    expect(onEvent).toHaveBeenCalledOnce();
  });

  it('validates every accepted identity and exact 202 schema', async () => {
    for (const invalid of [
      { ...accepted, turn_id: 'not-a-uuid' },
      { ...accepted, session_id: TURN_ID },
      { ...accepted, client_request_id: TURN_ID },
      { ...accepted, events_url: 'https://evil.example/events' },
      { ...accepted, status: 'failed' },
    ]) {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(invalid));
      await expect(transport(fetchMock).accept({
        sessionId: SESSION_ID,
        content: 'hello',
        clientRequestId: CLIENT_ID,
        answerMode: 'fast',
        thinkingEnabled: false,
      })).rejects.toThrow('invalid_chat_v3_acceptance');
    }
  });

  it('surfaces 429 retry seconds without automatically retrying POST', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      code: 'generation_capacity_reached',
      retryable: true,
      retry_after_seconds: 5,
    }, 429, { 'Retry-After': '5' }));

    await expect(transport(fetchMock).accept({
      sessionId: SESSION_ID,
      content: 'hello',
      clientRequestId: CLIENT_ID,
      answerMode: 'fast',
      thinkingEnabled: false,
    })).rejects.toMatchObject({
      status: 429,
      code: 'generation_capacity_reached',
      retryAfterSeconds: 5,
    });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('ignores duplicate event IDs without invoking the consumer twice', async () => {
    const delta = 'id: 8\nevent: answer_delta\ndata: {"text":"a"}\n\n';
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(delta + delta + doneEvent(9)));
    const onEvent = vi.fn();

    const terminal = await transport(fetchMock).consume(accepted, { after: 7, onEvent });

    expect(terminal).toMatchObject({ kind: 'done', after: 9 });
    expect(onEvent.mock.calls.map(([event]) => event.sequence)).toEqual([8, 9]);
  });

  it('reconnects on clean premature EOF with bounded 1/2/4/8 second backoff', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sseResponse(''))
      .mockResolvedValueOnce(sseResponse(''))
      .mockResolvedValueOnce(sseResponse(''))
      .mockResolvedValueOnce(sseResponse(''))
      .mockResolvedValueOnce(sseResponse(doneEvent(1)));
    const sleep = vi.fn(async (_delayMs: number) => {});

    const terminal = await transport(fetchMock, sleep).consume(accepted, {
      after: 0,
      onEvent: vi.fn(),
    });

    expect(terminal.kind).toBe('done');
    expect(sleep.mock.calls.map(([delay]) => delay)).toEqual([1000, 2000, 4000, 8000]);
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it('stops immediately at terminal and never opens another response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(doneEvent(1)));

    await transport(fetchMock).consume(accepted, { after: 0, onEvent: vi.fn() });

    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('detach ends only the visible consumer without calling cancel', async () => {
    let cancelStream = () => {};
    const body = new ReadableStream<Uint8Array>({
      start() {},
      cancel() { cancelStream(); },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      },
    }));
    const client = transport(fetchMock);
    const cancelled = new Promise<void>((resolve) => { cancelStream = resolve; });

    const consuming = client.consume(accepted, { after: 0, onEvent: vi.fn() });
    await Promise.resolve();
    client.detach(SESSION_ID);

    await expect(consuming).resolves.toMatchObject({ kind: 'detached', after: 0 });
    await cancelled;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('explicit cancel posts once while detach never does', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    const client = transport(fetchMock);

    await client.cancel(accepted);

    expect(fetchMock).toHaveBeenCalledWith(accepted.cancel_url, expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ Authorization: 'Bearer token-a' }),
    }));
  });

  it('treats revoked 403 as terminal and does not reconnect', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 403 }));

    await expect(transport(fetchMock).consume(accepted, {
      after: 0,
      onEvent: vi.fn(),
    })).rejects.toMatchObject({ status: 403, code: 'stream_access_revoked' });
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
