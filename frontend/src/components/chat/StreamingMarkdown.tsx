import { useMemo } from 'react';
import { MarkdownView } from './markdown';

/**
 * Block-level incremental Markdown for the live streaming bubble.
 *
 * Strategy (keeps per-frame work O(1) amortized — no jank on long replies):
 *  - Split the growing text into blocks at blank-line boundaries (fences kept whole).
 *  - All blocks EXCEPT the last are "stable": rendered via memoized <MarkdownView>,
 *    so each parses exactly once and never re-parses as more tokens arrive.
 *  - The last (in-progress) block is the only thing that re-renders each frame, and
 *    it renders as cheap plain text (or a live <pre> while a code fence is open) with
 *    a blinking caret. When the user/LLM finishes the block (blank line), it promotes
 *    to a memoized Markdown block and a fresh tail begins.
 *
 * On stream completion MessageBubble renders the full authoritative <MarkdownView>,
 * so any transient split artifacts disappear.
 */

function splitStreamBlocks(src: string): { stable: string[]; tail: string } {
  const lines = src.split('\n');
  const blocks: string[] = [];
  let cur: string[] = [];
  let inFence = false;
  let marker = '';

  for (const line of lines) {
    const t = line.trimStart();
    const fence = /^(```|~~~)/.exec(t);
    if (fence) {
      if (!inFence) { inFence = true; marker = fence[1]; }
      else if (t.startsWith(marker)) { inFence = false; }
      cur.push(line);
      continue;
    }
    if (!inFence && line.trim() === '') {
      if (cur.length) { blocks.push(cur.join('\n')); cur = []; }
    } else {
      cur.push(line);
    }
  }
  return { stable: blocks, tail: cur.join('\n') };
}

function analyzeTail(tail: string): { openCode: boolean; codeBody: string } {
  const lines = tail.split('\n');
  let open = false;
  let marker = '';
  let bodyStart = -1;
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trimStart();
    const m = /^(```|~~~)/.exec(t);
    if (m) {
      if (!open) { open = true; marker = m[1]; bodyStart = i + 1; }
      else if (t.startsWith(marker)) { open = false; }
    }
  }
  const codeBody = open && bodyStart >= 0 ? lines.slice(bodyStart).join('\n') : '';
  return { openCode: open, codeBody };
}

const Caret = () => <span className="stream-caret" aria-hidden="true" />;

export default function StreamingMarkdown({ content }: { content: string }) {
  const { stable, tail } = useMemo(() => splitStreamBlocks(content), [content]);
  const tailInfo = useMemo(() => (tail ? analyzeTail(tail) : { openCode: false, codeBody: '' }), [tail]);

  // Non-code tails render as live Markdown (only this one block re-parses per frame;
  // stable blocks are memoized). The blinking caret is appended to the last rendered
  // block via CSS (.stream-live > :last-child::after), so it sits inline at the end of
  // the text. Open code fences get an explicit caret inside the <code> instead.
  if (tailInfo.openCode) {
    return (
      <div className="markdown-content">
        {stable.map((block, i) => <MarkdownView key={i}>{block}</MarkdownView>)}
        <pre><code>{tailInfo.codeBody}<Caret /></code></pre>
      </div>
    );
  }

  return (
    <div className="markdown-content stream-live">
      {/* index keys are safe: the stable list is append-only and immutable. */}
      {stable.map((block, i) => <MarkdownView key={i}>{block}</MarkdownView>)}
      {tail && <MarkdownView>{tail}</MarkdownView>}
    </div>
  );
}
