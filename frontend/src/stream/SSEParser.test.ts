import { describe, expect, it } from 'vitest';

import { SSEParser, StoreSSEDecoder } from './SSEParser';

describe('SSEParser', () => {
  it('parses CRLF, split chunks, ids, comments, and multiline data', () => {
    const parser = new SSEParser();

    expect(parser.feed(': heartbeat\r')).toEqual([]);
    expect(parser.feed('\nid: 12\r\nevent: answer_delta\r\ndata: {"text":"hello"}\r')).toEqual([]);
    expect(parser.feed('\ndata: {"tail":"world"}\r\n\r')).toEqual([]);
    expect(parser.feed('\n')).toEqual([
      {
        id: '12',
        hasExplicitId: true,
        event: 'answer_delta',
        data: '{"text":"hello"}\n{"tail":"world"}',
      },
    ]);
  });

  it('flushes a complete event without a trailing blank line at EOF', () => {
    const parser = new SSEParser();

    expect(parser.feed('id: 13\nevent: done\ndata: {"message_id":"m-1"}')).toEqual([]);
    expect(parser.end()).toEqual([
      { id: '13', hasExplicitId: true, event: 'done', data: '{"message_id":"m-1"}' },
    ]);
    expect(parser.end()).toEqual([]);
  });

  it('keeps the last event id while ignoring id values containing null bytes', () => {
    const parser = new SSEParser();

    expect(parser.feed('id: 7\ndata: first\n\nid: bad\u0000id\ndata: second\n\n')).toEqual([
      { id: '7', hasExplicitId: true, event: 'message', data: 'first' },
      { id: '7', hasExplicitId: false, event: 'message', data: 'second' },
    ]);
  });

  it('does not dispatch merely because another event field follows data', () => {
    const parser = new SSEParser();

    expect(parser.feed('event: token\ndata: first\nevent: done\n')).toEqual([]);
    expect(parser.feed('data: second\n\n')).toEqual([
      { id: null, hasExplicitId: false, event: 'done', data: 'first\nsecond' },
    ]);
  });

  it('keeps multiline citations, quality, and done intact across chunks', () => {
    const decoder = new StoreSSEDecoder();

    expect(decoder.feed('event: citations\r\ndata: [\r\ndata: {"document_id":"d-1"}\r')).toEqual([]);
    expect(decoder.feed('\ndata: ]\r\n\r\nevent: quality\r\ndata: {\r\ndata: "score": 0.9\r\ndata: }\r\n\r\nevent: done\r\ndata: {\r\ndata: "message_id":"m-1"\r')).toEqual([
      { id: null, hasExplicitId: false, event: 'citations', data: '[\n{"document_id":"d-1"}\n]' },
      { id: null, hasExplicitId: false, event: 'quality', data: '{\n"score": 0.9\n}' },
    ]);
    expect(decoder.feed('\ndata: }\r\n\r\n')).toEqual([
      { id: null, hasExplicitId: false, event: 'done', data: '{\n"message_id":"m-1"\n}' },
    ]);
  });

  it('adapts adjacent legacy v1 events only at a recognized next-event boundary', () => {
    const decoder = new StoreSSEDecoder();

    expect(decoder.feed('event: token\ndata: {"token":"hello"}\nevent: citations\ndata: []\nevent: done\ndata: {"message_id":"m-1"}\n')).toEqual([
      { id: null, hasExplicitId: false, event: 'token', data: '{"token":"hello"}' },
      { id: null, hasExplicitId: false, event: 'citations', data: '[]' },
    ]);
    expect(decoder.end()).toEqual([
      { id: null, hasExplicitId: false, event: 'done', data: '{"message_id":"m-1"}' },
    ]);
  });
});
