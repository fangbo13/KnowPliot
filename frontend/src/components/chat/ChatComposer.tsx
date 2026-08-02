/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useLayoutEffect, useRef, useState } from 'react';
import { SendOutlined, ArrowUpOutlined, BookOutlined } from '@ant-design/icons';
import { Checkbox, Modal, Popover } from 'antd';
import { useTranslation } from 'react-i18next';
import type { AnswerMode } from '../../store/chatStore';

export interface LibraryOption {
  id: string;
  name: string;
}

const CAP_NOTICE_HIDE_KEY = 'kp.libpicker.hideCapNotice';

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
  retryAfterSeconds?: number;
  answerMode?: AnswerMode;
  canUseDeep?: boolean;
  onAnswerModeChange?: (mode: AnswerMode) => void;
  /** Independent server-governed thinking preference. */
  thinkingEnabled?: boolean;
  canUseThinking?: boolean;
  onThinkingChange?: (enabled: boolean) => void;
  /** Reference-library picker (session-level selection). */
  libraryOptions?: LibraryOption[];
  selectedLibraryIds?: string[];
  onSelectedLibraryChange?: (ids: string[]) => void;
  /** Per-mode cap on how many libraries may be cited at once. */
  maxLibraries?: number;
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
  retryAfterSeconds = 0,
  answerMode = 'fast',
  canUseDeep = false,
  onAnswerModeChange,
  thinkingEnabled = false,
  canUseThinking = false,
  onThinkingChange,
  libraryOptions = [],
  selectedLibraryIds = [],
  onSelectedLibraryChange,
  maxLibraries = 1,
}: Props) {
  const { t } = useTranslation('chat');
  const innerRef = useRef<HTMLTextAreaElement | null>(null);
  const composingRef = useRef(false);
  const [focused, setFocused] = useState(false);
  const [libOpen, setLibOpen] = useState(false);
  const [capNoticeOpen, setCapNoticeOpen] = useState(false);
  const [dontShowAgain, setDontShowAgain] = useState(false);

  const capNoticeSuppressed = () => {
    try {
      return localStorage.getItem(CAP_NOTICE_HIDE_KEY) === '1';
    } catch {
      return false;
    }
  };

  const toggleLibrary = (id: string) => {
    if (!onSelectedLibraryChange) return;
    const isSelected = selectedLibraryIds.includes(id);
    if (isSelected) {
      onSelectedLibraryChange(selectedLibraryIds.filter((value) => value !== id));
      return;
    }
    if (selectedLibraryIds.length >= maxLibraries) {
      if (!capNoticeSuppressed()) {
        setDontShowAgain(false);
        setCapNoticeOpen(true);
      }
      return;
    }
    const next = [...selectedLibraryIds, id];
    onSelectedLibraryChange(next);
    // Reaching the cap surfaces the friendly notice (with a don't-show-again
    // option) so the user understands why the remaining options disable.
    if (next.length >= maxLibraries && !capNoticeSuppressed()) {
      setDontShowAgain(false);
      setCapNoticeOpen(true);
    }
  };

  const closeCapNotice = () => {
    if (dontShowAgain) {
      try {
        localStorage.setItem(CAP_NOTICE_HIDE_KEY, '1');
      } catch {
        /* ignore storage failures */
      }
    }
    setCapNoticeOpen(false);
  };

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
      <div className="composer-mode" role="group" aria-label={t('answer_mode_label')}>
        <button
          type="button"
          className="composer-mode-toggle"
          role="switch"
          aria-label={t('answer_mode_label')}
          aria-checked={answerMode === 'deep'}
          disabled={disabled || isStreaming || !canUseDeep}
          title={!canUseDeep ? t('deep_mode_unavailable') || 'Deep mode is not available' : undefined}
          onClick={() => onAnswerModeChange?.(answerMode === 'fast' ? 'deep' : 'fast')}
        >
          <span className="composer-mode-toggle-track">
            <span className="composer-mode-toggle-thumb" />
          </span>
          <span className="composer-mode-toggle-label">
            {answerMode === 'deep' ? t('answer_mode_deep') : t('answer_mode_fast')}
          </span>
        </button>
        {canUseThinking && (
          <button
            type="button"
            className={`composer-mode-btn composer-thinking-btn${thinkingEnabled ? ' is-enabled' : ''}`}
            role="switch"
            aria-label={t('thinking_mode_label')}
            aria-checked={thinkingEnabled}
            disabled={disabled || isStreaming}
            onClick={() => onThinkingChange?.(!thinkingEnabled)}
          >
            {t('thinking_mode_label')}
            <span className="composer-thinking-state" aria-hidden="true">
              {thinkingEnabled ? t('thinking_mode_on') : t('thinking_mode_off')}
            </span>
          </button>
        )}
        {libraryOptions.length > 0 && (
          <Popover
            open={libOpen}
            onOpenChange={(next) => !isStreaming && setLibOpen(next)}
            trigger="click"
            placement="topLeft"
            content={(
              <div className="library-picker-panel" style={{ minWidth: 220, maxWidth: 300 }}>
                <div style={{ fontSize: 12, color: 'var(--color-text-tertiary)', marginBottom: 8 }}>
                  {t('library_picker_hint', {
                    max: maxLibraries,
                    defaultValue: '最多可选 {{max}} 个引用库',
                  })}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 240, overflowY: 'auto' }}>
                  {libraryOptions.map((lib) => {
                    const checked = selectedLibraryIds.includes(lib.id);
                    const atCap = !checked && selectedLibraryIds.length >= maxLibraries;
                    return (
                      <Checkbox
                        key={lib.id}
                        checked={checked}
                        disabled={atCap}
                        onChange={() => toggleLibrary(lib.id)}
                      >
                        {lib.name}
                      </Checkbox>
                    );
                  })}
                </div>
              </div>
            )}
          >
            <button
              type="button"
              className={`composer-mode-btn composer-library-btn${selectedLibraryIds.length > 0 ? ' is-enabled' : ''}`}
              aria-label={t('library_picker_label', { defaultValue: '引用库' })}
              disabled={disabled || isStreaming}
            >
              <BookOutlined />
              <span style={{ marginLeft: 4 }}>
                {t('library_picker_label', { defaultValue: '引用库' })}
                {selectedLibraryIds.length > 0 ? ` ${selectedLibraryIds.length}/${maxLibraries}` : ''}
              </span>
            </button>
          </Popover>
        )}
      </div>
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
            <button type="button" className="composer-stop" onClick={onStop} aria-label={t('stop_generation')}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: 'currentColor', display: 'block' }} />
            </button>
          ) : (
            <button
              type="button"
              className="composer-send"
              onClick={onSubmit}
              disabled={!canSend}
              aria-label={t('send')}
            >
              {multiline ? <ArrowUpOutlined /> : <SendOutlined />}
            </button>
          )}
        </div>
      </div>

      {showHint && (
        <div className="composer-hint">
          {retryAfterSeconds > 0 ? t('capacity_retry_countdown', { seconds: retryAfterSeconds }) : hintText ?? (
            <>
              <span><span className="kbd">↵</span> {t('hint_send', 'send')}</span>
              <span><span className="kbd">⇧</span><span className="kbd">↵</span> {t('hint_newline', 'newline')}</span>
            </>
          )}
        </div>
      )}

      <Modal
        open={capNoticeOpen}
        onOk={closeCapNotice}
        onCancel={closeCapNotice}
        okText={t('confirm', { defaultValue: '知道了' })}
        cancelButtonProps={{ style: { display: 'none' } }}
        title={t('library_cap_title', { defaultValue: '引用库数量限制' })}
      >
        <p>
          {t('library_cap_notice', {
            mode: answerMode === 'deep' ? t('answer_mode_deep') : t('answer_mode_fast'),
            max: maxLibraries,
            defaultValue: '{{mode}} 模式最多同时引用 {{max}} 个知识库。如需引用更多，请切换到 Deep 模式。',
          })}
        </p>
        <Checkbox
          checked={dontShowAgain}
          onChange={(e) => setDontShowAgain(e.target.checked)}
        >
          {t('dont_show_again', { defaultValue: '不再提示' })}
        </Checkbox>
      </Modal>
    </>
  );
}
