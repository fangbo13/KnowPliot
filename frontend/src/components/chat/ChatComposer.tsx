import { useLayoutEffect, useRef, useState } from 'react';
import { SendOutlined, ArrowUpOutlined } from '@ant-design/icons';

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  placeholder: string;
  ariaLabel: string;
  isStreaming: boolean;
  disabled?: boolean;
  multiline?: boolean;
  autoFocus?: boolean;
  inputRef?: React.RefObject<HTMLTextAreaElement> | ((node: HTMLTextAreaElement | null) => void);
  maxRows?: number;
  showCharacterCount?: boolean;
  showHint?: boolean;
  hintText?: string;
};

const MAX_LEN = 4000;
const ROW_PX = 24;

export default function ChatComposer({
  value,
  onChange,
  onSubmit,
  onStop,
  placeholder,
  ariaLabel,
  isStreaming,
  disabled = false,
  multiline = true,
  autoFocus = false,
  inputRef,
  maxRows = 6,
  showCharacterCount = true,
  showHint = false,
  hintText,
}: Props) {
  const innerRef = useRef<HTMLTextAreaElement | null>(null);
  const composingRef = useRef(false);
  const [focused, setFocused] = useState(false);

  const setRefs = (node: HTMLTextAreaElement | null) => {
    innerRef.current = node;
    if (typeof inputRef === 'function') inputRef(node);
    else if (inputRef) (inputRef as React.MutableRefObject<HTMLTextAreaElement | null>).current = node;
  };

  // Auto-grow up to maxRows, then scroll.
  useLayoutEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    const maxH = (multiline ? maxRows : 1) * ROW_PX + 16;
    el.style.height = 'auto';
    const next = Math.min(el.scrollHeight, maxH);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > maxH ? 'auto' : 'hidden';
  }, [value, multiline, maxRows]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // IME-safe: never submit while a composition (e.g. pinyin) is active.
    if (e.key === 'Enter' && !e.shiftKey && !composingRef.current && !(e.nativeEvent as any).isComposing) {
      e.preventDefault();
      onSubmit();
    }
  };

  const canSend = !!value.trim() && !disabled;
  const counterClass = value.length >= MAX_LEN ? 'danger' : value.length > 3500 ? 'warn' : '';

  return (
    <>
      <div className={`composer${focused ? ' is-focused' : ''}${disabled ? ' is-disabled' : ''}`}>
        <div className="composer-inner">
          <textarea
            ref={setRefs}
            className="composer-textarea"
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => { composingRef.current = true; }}
            onCompositionEnd={() => { composingRef.current = false; }}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder={placeholder}
            disabled={disabled || isStreaming}
            autoFocus={autoFocus}
            maxLength={MAX_LEN}
            aria-label={ariaLabel}
          />

          {showCharacterCount && value.length > 0 && (
            <div className={`composer-counter ${counterClass}`} role="status" aria-live="polite">
              {value.length}/{MAX_LEN}
            </div>
          )}

          {isStreaming ? (
            <button type="button" className="composer-stop" onClick={onStop} aria-label="Stop generation">
              <span style={{ width: 11, height: 11, borderRadius: 3, background: 'currentColor', display: 'block' }} />
            </button>
          ) : (
            <button
              type="button"
              className="composer-send"
              onClick={onSubmit}
              disabled={!canSend}
              aria-label="Send message"
            >
              {multiline ? <ArrowUpOutlined /> : <SendOutlined />}
            </button>
          )}
        </div>
      </div>

      {showHint && (
        <div className="composer-hint">
          {hintText ?? (
            <>
              <span><span className="kbd">↵</span> send</span>
              <span><span className="kbd">⇧</span><span className="kbd">↵</span> newline</span>
            </>
          )}
        </div>
      )}
    </>
  );
}
