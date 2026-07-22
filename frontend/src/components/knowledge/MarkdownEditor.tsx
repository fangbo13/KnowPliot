/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import { Button, Space, Tooltip } from 'antd';
import {
  BoldOutlined,
  ItalicOutlined,
  UnorderedListOutlined,
  OrderedListOutlined,
  CodeOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { MarkdownView } from '../chat/markdown';
import './MarkdownEditor.css';

interface MarkdownEditorProps {
  /** Controlled value */
  value?: string;
  /** Controlled change handler */
  onChange?: (value: string) => void;
  /** Uncontrolled initial value */
  defaultValue?: string;
  /** Placeholder for the textarea */
  placeholder?: string;
  /** Read-only mode (preview only, no toolbar/textarea) */
  readOnly?: boolean;
  /** Optional min height for the editor area */
  minHeight?: number;
}

/**
 * KB-12-Features §5: Editable Markdown editor with live preview.
 *
 * Reuses MarkdownView (from chat/markdown.tsx) for preview rendering,
 * inheriting its XSS whitelist and syntax highlighting.
 * All colors use CSS variables for light/dark mode support.
 */
export function MarkdownEditor({
  value,
  onChange,
  defaultValue = '',
  placeholder,
  readOnly = false,
  minHeight = 300,
}: MarkdownEditorProps) {
  const { t } = useTranslation('common');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [internalValue, setInternalValue] = useState(defaultValue);
  const [showPreview, setShowPreview] = useState(true);

  const currentValue = value ?? internalValue;

  const handleChange = useCallback(
    (next: string) => {
      if (value === undefined) {
        setInternalValue(next);
      }
      onChange?.(next);
    },
    [value, onChange],
  );

  /**
   * Wrap or insert text around the current selection in the textarea.
   * If a selection exists, wrap it with prefix/suffix.
   * If no selection, insert prefix + suffix and place cursor between.
   */
  const wrapSelection = useCallback(
    (prefix: string, suffix: string = prefix) => {
      const el = textareaRef.current;
      if (!el) return;
      const start = el.selectionStart;
      const end = el.selectionEnd;
      const selected = currentValue.substring(start, end);
      const newValue =
        currentValue.substring(0, start) +
        prefix +
        selected +
        suffix +
        currentValue.substring(end);
      handleChange(newValue);
      // Restore focus and selection after React re-render
      requestAnimationFrame(() => {
        el.focus();
        const cursorStart = start + prefix.length;
        const cursorEnd = end + prefix.length;
        el.setSelectionRange(cursorStart, cursorEnd);
      });
    },
    [currentValue, handleChange],
  );

  /**
   * Insert a line prefix at the start of each selected line (or current line).
   */
  const linePrefix = useCallback(
    (prefix: string) => {
      const el = textareaRef.current;
      if (!el) return;
      const start = el.selectionStart;
      const end = el.selectionEnd;
      // Expand to full lines
      const lineStart = currentValue.lastIndexOf('\n', start - 1) + 1;
      const lineEndIdx = currentValue.indexOf('\n', end);
      const lineEnd = lineEndIdx === -1 ? currentValue.length : lineEndIdx;
      const selectedLines = currentValue.substring(lineStart, lineEnd);
      const prefixed = selectedLines
        .split('\n')
        .map((line) => prefix + line)
        .join('\n');
      const newValue =
        currentValue.substring(0, lineStart) +
        prefixed +
        currentValue.substring(lineEnd);
      handleChange(newValue);
      requestAnimationFrame(() => {
        el.focus();
        el.setSelectionRange(lineStart, lineStart + prefixed.length);
      });
    },
    [currentValue, handleChange],
  );

  const toolbar = useMemo(() => {
    if (readOnly) return null;
    return (
      <div className="md-editor__toolbar">
        <Space size="small">
          <Tooltip title={t('kb_edit')}>
            <Button
              type="text"
              size="small"
              icon={<BoldOutlined />}
              onClick={() => wrapSelection('**')}
            />
          </Tooltip>
          <Tooltip title={t('kb_edit')}>
            <Button
              type="text"
              size="small"
              icon={<ItalicOutlined />}
              onClick={() => wrapSelection('*')}
            />
          </Tooltip>
          <Tooltip title="H1">
            <Button
              type="text"
              size="small"
              onClick={() => linePrefix('# ')}
            >
              H1
            </Button>
          </Tooltip>
          <Tooltip title="H2">
            <Button
              type="text"
              size="small"
              onClick={() => linePrefix('## ')}
            >
              H2
            </Button>
          </Tooltip>
          <Tooltip title={t('kb_diff_insert')}>
            <Button
              type="text"
              size="small"
              icon={<UnorderedListOutlined />}
              onClick={() => linePrefix('- ')}
            />
          </Tooltip>
          <Tooltip title={t('kb_diff_insert')}>
            <Button
              type="text"
              size="small"
              icon={<OrderedListOutlined />}
              onClick={() => linePrefix('1. ')}
            />
          </Tooltip>
          <Tooltip title={t('kb_edit')}>
            <Button
              type="text"
              size="small"
              icon={<CodeOutlined />}
              onClick={() => wrapSelection('`')}
            />
          </Tooltip>
          <Tooltip title={t('kb_edit')}>
            <Button
              type="text"
              size="small"
              icon={<LinkOutlined />}
              onClick={() => wrapSelection('[', '](https://)')}
            />
          </Tooltip>
        </Space>
        <Button
          type="text"
          size="small"
          onClick={() => setShowPreview((v) => !v)}
        >
          {showPreview ? t('kb_editor_preview') : t('kb_edit')}
        </Button>
      </div>
    );
  }, [readOnly, t, showPreview, wrapSelection, linePrefix]);

  if (readOnly) {
    return (
      <div className="md-editor__container md-editor__container--readonly">
        <div className="markdown-content">
          <MarkdownView>{currentValue}</MarkdownView>
        </div>
      </div>
    );
  }

  return (
    <div className="md-editor__container">
      {toolbar}
      <div
        className="md-editor__body"
        style={{ minHeight }}
      >
        <textarea
          ref={textareaRef}
          className="md-editor__textarea"
          value={currentValue}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder || t('kb_editor_placeholder')}
          spellCheck={false}
        />
        {showPreview && (
          <div className="md-editor__preview">
            <div className="markdown-content">
              <MarkdownView>{currentValue || ''}</MarkdownView>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default MarkdownEditor;
