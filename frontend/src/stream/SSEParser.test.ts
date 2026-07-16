import { describe, expect, it } from 'vitest';

import { SSEParser } from './SSEParser';

describe('SSEParser', () => {
  it('parses CRLF, split chunks, ids, comments, and multiline data', () => {
    const parser = new SSEParser();

    expect(parser.feed(': heartbeat\r')).toEqual([]);
    expect(parser.feed('\nid: 12\r\nevent: answer_delta\r\ndata: {"text":"hello"}\r')).toEqual([]);
    expect(parser.feed('\ndata: {"tail":"world"}\r\n\r')).toEqual([]);
    expect(parser.feed('\n')).toEqual([
      {
        id: '12',
        event: 'answer_delta',
        data: '{"text":"hello"}\n{"tail":"world"}',
      },
    ]);
  });

  it('flushes a complete event without a trailing blank line at EOF', () => {
    const parser = new SSEParser();

    expect(parser.feed('id: 13\nevent: done\ndata: {"message_id":"m-1"}')).toEqual([]);
    expect(parser.end()).toEqual([
      { id: '13', event: 'done', data: '{"message_id":"m-1"}' },
    ]);
    expect(parser.end()).toEqual([]);
  });

  it('keeps the last event id while ignoring id values containing null bytes', () => {
    const parser = new SSEParser();

    expect(parser.feed('id: 7\ndata: first\n\nid: bad\u0000id\ndata: second\n\n')).toEqual([
      { id: '7', event: 'message', data: 'first' },
      { id: '7', event: 'message', data: 'second' },
    ]);
  });
});
