/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useTranslation } from 'react-i18next';
import {
  SafetyCertificateOutlined, AuditOutlined, WarningOutlined,
  FileSearchOutlined, FileTextOutlined, CheckCircleOutlined,
  BookOutlined,
} from '@ant-design/icons';
import { useChatStore } from '../../store/chatStore';
import { useState, useRef, useEffect, useMemo } from 'react';
import ChatComposer from './ChatComposer';

interface WelcomeScreenProps {
  onQuickAction: (q: string) => void;
  onSendMessage?: (msg: string, options?: { answerMode?: 'fast' | 'deep'; thinkingEnabled?: boolean }) => void;
  templateQuickQuestions?: string[];
}

export default function WelcomeScreen({ onQuickAction, onSendMessage, templateQuickQuestions }: WelcomeScreenProps) {
  const { t, i18n } = useTranslation('chat');
  const [inputValue, setInputValue] = useState('');
  const [answerMode, setAnswerMode] = useState<'fast' | 'deep'>('fast');
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isChinese = i18n.language?.startsWith('zh');
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const activeTurn = useChatStore((s) => activeSessionId ? s.turnsBySession[activeSessionId] : undefined);
  const pendingSessionCreation = useChatStore((s) => activeSessionId ? false : s.isSendLocked);
  const isSendLocked = activeTurn?.isLocked ?? pendingSessionCreation;
  const isStreaming = Boolean(activeTurn?.isLocked && activeTurn.phase !== 'error');

  const defaultQuickActions = useMemo(() => (
    isChinese
      ? [
          { icon: <SafetyCertificateOutlined />, question: '审计适用哪些准则和规范？', label: '审计准则' },
          { icon: <AuditOutlined />, question: '如何进行内部控制评价？', label: '内控评价' },
          { icon: <WarningOutlined />, question: '风险评估的流程是什么？', label: '风险评估' },
          { icon: <FileSearchOutlined />, question: '本次审计需要执行哪些程序？', label: '审计程序' },
          { icon: <FileTextOutlined />, question: '审计报告应包含哪些内容？', label: '审计报告' },
          { icon: <CheckCircleOutlined />, question: '关键合规要求有哪些？', label: '合规要求' },
        ]
      : [
          { icon: <SafetyCertificateOutlined />, question: 'What audit standards and regulations apply?', label: 'Standards' },
          { icon: <AuditOutlined />, question: 'How do I assess internal controls?', label: 'Controls' },
          { icon: <WarningOutlined />, question: 'What is the risk assessment process?', label: 'Risk' },
          { icon: <FileSearchOutlined />, question: 'What audit procedures are required for this engagement?', label: 'Procedures' },
          { icon: <FileTextOutlined />, question: 'What should the audit report include?', label: 'Report' },
          { icon: <CheckCircleOutlined />, question: 'What are the key compliance requirements?', label: 'Compliance' },
        ]
  ), [isChinese]);

  const activeQuickActions = useMemo(() => {
    if (templateQuickQuestions && templateQuickQuestions.length > 0) {
      return templateQuickQuestions.map((q, idx) => ({
        icon: <BookOutlined />,
        question: q,
        label: isChinese ? `问题 ${idx + 1}` : `Question ${idx + 1}`,
      }));
    }
    return defaultQuickActions;
  }, [templateQuickQuestions, defaultQuickActions, isChinese]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const handleSend = () => {
    if (!inputValue.trim() || isSendLocked || isStreaming) return;
    if (onSendMessage) {
      onSendMessage(inputValue.trim(), { answerMode, thinkingEnabled });
    } else {
      onQuickAction(inputValue.trim());
    }
    setInputValue('');
  };

  return (
    <div className="welcome">
      <div className="welcome-head section-enter">
        <div className="welcome-mark ambient-glow">K</div>
        <h1 className="welcome-greeting">{t('welcome_greeting', { defaultValue: 'How can I help with your audit?' })}</h1>
        <p className="welcome-sub">{t('welcome_tip')}</p>
      </div>

      <ChatComposer
        value={inputValue}
        onChange={setInputValue}
        onSubmit={handleSend}
        placeholder={t('placeholder') || 'Type your question here...'}
        ariaLabel={t('chat_input_label') || 'Type your message'}
        isStreaming={isStreaming}
        disabled={isSendLocked}
        multiline
        inputRef={inputRef}
        autoFocus
        maxRows={5}
        showHint
        hintText={t('welcome_suggest_hint', { defaultValue: 'Ask anything, or pick a topic below' }) as string}
        answerMode={answerMode}
        canUseDeep
        thinkingEnabled={thinkingEnabled}
        canUseThinking
        onAnswerModeChange={setAnswerMode}
        onThinkingChange={setThinkingEnabled}
      />

      <div className="welcome-suggest-grid">
        {activeQuickActions.map((action) => (
          <button
            key={action.label}
            className="welcome-suggest hover-lift btn-press"
            onClick={() => onQuickAction(action.question)}
            aria-label={`${action.label}: ${action.question}`}
          >
            <span className="welcome-suggest-top">
              <span className="welcome-suggest-icon">{action.icon}</span>
              <span className="welcome-suggest-label">{action.label}</span>
            </span>
            <span className="welcome-suggest-q">{action.question}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
