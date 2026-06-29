import { Input, type InputRef } from 'antd';
import { SendOutlined, StopOutlined } from '@ant-design/icons';

const { TextArea } = Input;

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
  inputRef?: React.Ref<InputRef>;
  maxRows?: number;
  showCharacterCount?: boolean;
};

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
  maxRows = 4,
  showCharacterCount = true,
}: Props) {
  return (
    <div
      className="chat-input-container"
      style={{
        position: 'relative',
        background: 'var(--color-bg-container)',
        border: '1.5px solid var(--color-border)',
        borderRadius: 24,
        padding: '12px 16px',
        boxShadow: 'var(--shadow-floating-input)',
        transition: 'box-shadow 0.25s ease, border-color 0.25s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12 }}>
        <TextArea
          ref={inputRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={placeholder}
          disabled={disabled || isStreaming}
          autoFocus={autoFocus}
          maxLength={4000}
          autoSize={{ minRows: 1, maxRows: multiline ? maxRows : 1 }}
          aria-label={ariaLabel}
          className="chat-input-textarea"
          style={{
            border: 'none',
            boxShadow: 'none',
            fontSize: 15,
            padding: '4px 0',
            background: 'transparent',
            resize: 'none',
          }}
        />
        {showCharacterCount && value.length > 0 && (
          <div
            role="status"
            aria-live="polite"
            aria-label={`Character count: ${value.length} of 4000`}
            className="chat-input-counter"
            style={{
              position: 'absolute',
              right: 64,
              bottom: 5,
              fontSize: 11,
              lineHeight: 1,
              color:
                value.length >= 4000
                  ? 'var(--color-error)'
                  : value.length > 3500
                    ? 'var(--color-warning)'
                    : 'var(--color-text-tertiary)',
              pointerEvents: 'none',
              transition: 'color 0.2s ease, opacity 0.2s ease',
            }}
          >
            {value.length}/4000
          </div>
        )}
        {isStreaming ? (
          <button
            type="button"
            className="chat-input-stop-btn"
            onClick={onStop}
            aria-label="Stop generation"
            style={{
              width: 36,
              height: 36,
              borderRadius: 20,
              border: '1.5px solid var(--color-error)',
              background: 'rgba(var(--color-error-rgb, 239, 68, 68), 0.08)',
              color: 'var(--color-error)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              flexShrink: 0,
              transition: 'all 0.2s ease',
              fontSize: 16,
            }}
          >
            <StopOutlined />
          </button>
        ) : (
          <button
            type="button"
            className="chat-input-send-btn"
            onClick={onSubmit}
            disabled={!value.trim() || disabled}
            aria-label="Send message"
            style={{
              width: 36,
              height: 36,
              borderRadius: 20,
              border: 'none',
              background: value.trim() && !disabled ? 'var(--gradient-accent)' : 'var(--color-border)',
              color: value.trim() && !disabled ? '#fff' : 'var(--color-text-tertiary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: value.trim() && !disabled ? 'pointer' : 'default',
              flexShrink: 0,
              transition: 'all 0.2s ease',
              fontSize: 15,
            }}
          >
            <SendOutlined />
          </button>
        )}
      </div>
    </div>
  );
}
