import { useState, useCallback } from 'react';
import { CopyOutlined, CheckOutlined } from '@ant-design/icons';
import { message as antdMessage, Button, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';

interface Props {
  code: string;
  language?: string;
}

/**
 * V4.0 UI-MED-002 / P1-1: Code block copy button.
 *
 * Positioned absolutely at the top-right of code blocks.
 * Desktop: visible on hover via CSS (.code-block-copy-btn opacity transition).
 * Mobile: always visible via CSS media query override.
 *
 * Uses navigator.clipboard.writeText with textarea fallback.
 * Shows CheckOutlined icon for 2 seconds after successful copy,
 * then reverts to CopyOutlined.
 */
export default function CopyCodeButton({ code, language }: Props) {
  const { t } = useTranslation('chat');
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      antdMessage.success(t('code_copied') || '代码已复制');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers / restricted contexts
      const textarea = document.createElement('textarea');
      textarea.value = code;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      antdMessage.success(t('code_copied') || '代码已复制');
      setTimeout(() => setCopied(false), 2000);
    }
  }, [code, t]);

  return (
    <div className="code-block-copy-btn">
      {/* Language label — shown only if language is detected */}
      {language && (
        <span className="code-lang-label">{language}</span>
      )}
      <Tooltip title={copied ? (t('copied') || '已复制') : (t('copy_code') || '复制代码')}>
        <Button
          type="text"
          size="small"
          icon={copied ? <CheckOutlined style={{ color: 'var(--color-success)' }} /> : <CopyOutlined />}
          onClick={handleCopy}
          aria-label={copied ? (t('copied') || '已复制') : (t('copy_code') || '复制代码')}
          style={{
            padding: '2px 6px',
            color: copied ? 'var(--color-success)' : 'var(--color-text-tertiary)',
            fontSize: 12,
          }}
        />
      </Tooltip>
    </div>
  );
}
