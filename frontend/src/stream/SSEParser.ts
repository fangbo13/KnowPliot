export interface SSEMessage {
  id: string | null;
  event: string;
  data: string;
}

/** Incremental parser for the event-stream wire format. */
export class SSEParser {
  private buffer = '';
  private eventName = '';
  private dataLines: string[] = [];
  private lastEventId: string | null = null;
  private ended = false;

  feed(chunk: string): SSEMessage[] {
    if (this.ended || chunk.length === 0) return [];
    this.buffer += chunk;
    return this.consumeCompleteLines();
  }

  end(): SSEMessage[] {
    if (this.ended) return [];
    this.ended = true;
    const events = this.consumeCompleteLines();
    if (this.buffer.length > 0) {
      this.consumeLine(this.buffer, events);
      this.buffer = '';
    }
    this.dispatch(events);
    return events;
  }

  private consumeCompleteLines(): SSEMessage[] {
    const events: SSEMessage[] = [];
    let newline = this.buffer.indexOf('\n');
    while (newline >= 0) {
      let line = this.buffer.slice(0, newline);
      this.buffer = this.buffer.slice(newline + 1);
      if (line.endsWith('\r')) line = line.slice(0, -1);
      this.consumeLine(line, events);
      newline = this.buffer.indexOf('\n');
    }
    return events;
  }

  private consumeLine(line: string, events: SSEMessage[]): void {
    if (line === '') {
      this.dispatch(events);
      return;
    }
    if (line.startsWith(':')) return;

    const separator = line.indexOf(':');
    const field = separator < 0 ? line : line.slice(0, separator);
    let value = separator < 0 ? '' : line.slice(separator + 1);
    if (value.startsWith(' ')) value = value.slice(1);

    switch (field) {
      case 'event':
        this.eventName = value;
        break;
      case 'data':
        this.dataLines.push(value);
        break;
      case 'id':
        if (!value.includes('\0')) this.lastEventId = value;
        break;
    }
  }

  private dispatch(events: SSEMessage[]): void {
    if (this.dataLines.length === 0) {
      this.eventName = '';
      return;
    }
    events.push({
      id: this.lastEventId,
      event: this.eventName || 'message',
      data: this.dataLines.join('\n'),
    });
    this.eventName = '';
    this.dataLines = [];
  }
}

const LEGACY_V1_EVENTS = new Set(['token', 'citations', 'quality', 'done', 'error']);

/** Store-facing decoder with an explicit adapter for delimiter-less legacy v1. */
export class StoreSSEDecoder {
  private readonly parser = new SSEParser();
  private lineBuffer = '';
  private currentEvent = '';
  private currentHasData = false;
  private currentHasId = false;
  private ended = false;

  feed(chunk: string): SSEMessage[] {
    if (this.ended || chunk.length === 0) return [];
    this.lineBuffer += chunk;
    const events: SSEMessage[] = [];
    let newline = this.lineBuffer.indexOf('\n');
    while (newline >= 0) {
      const rawLine = this.lineBuffer.slice(0, newline);
      this.lineBuffer = this.lineBuffer.slice(newline + 1);
      events.push(...this.consumeLine(rawLine));
      newline = this.lineBuffer.indexOf('\n');
    }
    return events;
  }

  end(): SSEMessage[] {
    if (this.ended) return [];
    this.ended = true;
    const events = this.lineBuffer.length > 0
      ? this.consumeLine(this.lineBuffer, false)
      : [];
    this.lineBuffer = '';
    events.push(...this.parser.end());
    return events;
  }

  private consumeLine(rawLine: string, terminated = true): SSEMessage[] {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
    const events: SSEMessage[] = [];
    if (line.startsWith('event:')) {
      const nextEvent = line.slice(6).replace(/^ /, '');
      const isLegacyBoundary = this.currentHasData
        && !this.currentHasId
        && LEGACY_V1_EVENTS.has(this.currentEvent)
        && LEGACY_V1_EVENTS.has(nextEvent);
      if (isLegacyBoundary) {
        events.push(...this.parser.feed('\n'));
        this.resetEventTracking();
      }
      this.currentEvent = nextEvent;
    } else if (line.startsWith('data:')) {
      this.currentHasData = true;
    } else if (line.startsWith('id:')) {
      this.currentHasId = true;
    } else if (line === '') {
      this.resetEventTracking();
    }
    events.push(...this.parser.feed(rawLine + (terminated ? '\n' : '')));
    return events;
  }

  private resetEventTracking(): void {
    this.currentEvent = '';
    this.currentHasData = false;
    this.currentHasId = false;
  }
}
