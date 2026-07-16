import { describe, expect, it } from 'vitest';

import {
  InvalidChatStreamEventError,
  validateChatStreamMessage,
  validateRecoveryResponseIdentity,
} from './ChatStreamProtocol';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';
const TURN_ID = '33333333-3333-4333-8333-333333333333';
const CLIENT_ID = '22222222-2222-4222-8222-222222222221';
const MESSAGE_ID = '55555555-5555-4555-8555-555555555555';

const context = {
  protocolVersion: null as 1 | 2 | null,
  expectedSessionId: SESSION_ID,
  expectedTurnId: TURN_ID,
  expectedClientRequestId: CLIENT_ID,
};

describe('chat stream protocol validation', () => {
  it('accepts a complete v2 meta and returns its safe sequence', () => {
    expect(validateChatStreamMessage({
      id: '1',
      event: 'meta',
      data: JSON.stringify({
        protocol_version: 2,
        turn_id: TURN_ID,
        session_id: SESSION_ID,
        client_request_id: CLIENT_ID,
      }),
    }, context)).toMatchObject({ name: 'meta', sequence: 1, protocolVersion: 2 });
  });

  it('requires meta before any initial id-bearing v2 event', () => {
    expect(() => validateChatStreamMessage({
      id: '1',
      event: 'answer_delta',
      data: '{"text":"too early"}',
    }, context)).toThrow(InvalidChatStreamEventError);
  });

  it.each([null, '0', '-1', '1.5', String(Number.MAX_SAFE_INTEGER + 1)])(
    'rejects an invalid v2 event id %s',
    (id) => {
      expect(() => validateChatStreamMessage({
        id,
        event: 'answer_delta',
        data: '{"text":"unsafe"}',
      }, { ...context, protocolVersion: 2 })).toThrow(InvalidChatStreamEventError);
    },
  );

  it('rejects unknown v2 events before a cursor can be advanced', () => {
    expect(() => validateChatStreamMessage({
      id: '9',
      event: 'provider_reasoning',
      data: '{"text":"private"}',
    }, { ...context, protocolVersion: 2 })).toThrow(InvalidChatStreamEventError);
  });

  it('requires all v2 done identities and a valid message id', () => {
    expect(() => validateChatStreamMessage({
      id: '4',
      event: 'done',
      data: JSON.stringify({
        message_id: MESSAGE_ID,
        session_id: SESSION_ID,
        turn_id: TURN_ID,
      }),
    }, { ...context, protocolVersion: 2 })).toThrow(InvalidChatStreamEventError);
  });

  it('allows a legacy v1 token without an event id', () => {
    expect(validateChatStreamMessage({
      id: null,
      event: 'token',
      data: '{"token":"legacy"}',
    }, context)).toMatchObject({
      name: 'token',
      sequence: null,
      protocolVersion: 1,
      data: { token: 'legacy' },
    });
  });

  it('requires both recovery identity headers to be present and matching', () => {
    expect(() => validateRecoveryResponseIdentity(
      new Headers({ 'X-Chat-Turn-Id': TURN_ID }),
      TURN_ID,
      CLIENT_ID,
    )).toThrow(InvalidChatStreamEventError);
    expect(validateRecoveryResponseIdentity(new Headers({
      'X-Chat-Turn-Id': TURN_ID,
      'X-Chat-Client-Request-Id': CLIENT_ID,
    }), TURN_ID, CLIENT_ID)).toEqual({ turnId: TURN_ID, clientRequestId: CLIENT_ID });
  });
});
