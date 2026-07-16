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

  /** Flush one legacy v1 event that omitted the required blank delimiter. */
  flushLegacyEvent(): SSEMessage[] {
    if (this.buffer.length > 0
      || this.dataLines.length === 0
      || !['token', 'citations', 'quality', 'done', 'error'].includes(this.eventName)) {
      return [];
    }
    const events: SSEMessage[] = [];
    this.dispatch(events);
    return events;
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
        // Preserve the legacy backend/client fixtures that omitted the SSE
        // blank-line delimiter between events.
        if (this.dataLines.length > 0) this.dispatch(events);
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
