import { useState, useCallback } from 'react';
import { CopyOutlined, CheckOutlined } from '@ant-design/icons';
import { message as antdMessage } from 'antd';
import { useTranslation } from 'react-i18next';

interface Props {
  code: string;
  language?: string;
}

/** Copy affordance for code blocks (hover-revealed on desktop, always shown on touch). */
export default function CopyCodeButton({ code, language }: Props) {
  const { t } = useTranslation('chat');
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = code;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    setCopied(true);
    antdMessage.success(t('code_copied') || 'Code copied');
    setTimeout(() => setCopied(false), 2000);
  }, [code, t]);

  return (
    <div className="code-block-copy-btn">
      {language && <span className="code-lang-label">{language}</span>}
      <button
        className="icon-btn"
        style={{ width: 28, height: 28, background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}
        onClick={handleCopy}
        aria-label={copied ? (t('copied') || 'Copied') : (t('copy_code') || 'Copy code')}
        title={copied ? (t('copied') || 'Copied') : (t('copy_code') || 'Copy code')}
      >
        {copied ? <CheckOutlined style={{ color: 'var(--color-success)', fontSize: 13 }} /> : <CopyOutlined style={{ fontSize: 13 }} />}
      </button>
    </div>
  );
}
