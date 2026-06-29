import { useTranslation } from 'react-i18next';
import {
  LaptopOutlined, DollarOutlined, CalendarOutlined,
  BookOutlined, EnvironmentOutlined, TeamOutlined,
} from '@ant-design/icons';
import { useChatStore } from '../../store/chatStore';
import { useState, useRef, useEffect, useMemo } from 'react';
import ChatComposer from './ChatComposer';

interface WelcomeScreenProps {
  onQuickAction: (q: string) => void;
  onSendMessage?: (msg: string) => void;
}

export default function WelcomeScreen({ onQuickAction, onSendMessage }: WelcomeScreenProps) {
  const { t, i18n } = useTranslation('chat');
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isChinese = i18n.language?.startsWith('zh');
  const isSendLocked = useChatStore((s) => s.isSendLocked);
  const streamPhase = useChatStore((s) => s.streamPhase);
  const streamingSessionId = useChatStore((s) => s.streamingSessionId);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const isStreaming = streamPhase !== 'idle' && streamingSessionId === activeSessionId;

  const quickActions = useMemo(() => (
    isChinese
      ? [
          { icon: <LaptopOutlined />, question: '如何设置公司邮箱和电脑？', label: 'IT 设置' },
          { icon: <DollarOutlined />, question: '报销流程是什么？', label: '报销流程' },
          { icon: <CalendarOutlined />, question: '我有多少年假？', label: '年假天数' },
          { icon: <BookOutlined />, question: '入职培训包含哪些课程？', label: '培训课程' },
          { icon: <EnvironmentOutlined />, question: '办公室在哪里，怎么去？', label: '办公位置' },
          { icon: <TeamOutlined />, question: '我的导师或搭档是谁？', label: '我的导师' },
        ]
      : [
          { icon: <LaptopOutlined />, question: 'How do I set up my company email and laptop?', label: 'IT setup' },
          { icon: <DollarOutlined />, question: 'What is the expense reimbursement process?', label: 'Expenses' },
          { icon: <CalendarOutlined />, question: 'How many annual leave days do I have?', label: 'Annual leave' },
          { icon: <BookOutlined />, question: 'What courses are included in onboarding training?', label: 'Training' },
          { icon: <EnvironmentOutlined />, question: 'Where is the office and how do I get there?', label: 'Office location' },
          { icon: <TeamOutlined />, question: 'Who is my mentor or buddy?', label: 'Mentor' },
        ]
  ), [isChinese]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const handleSend = () => {
    if (!inputValue.trim() || isSendLocked || isStreaming) return;
    (onSendMessage ?? onQuickAction)(inputValue.trim());
    setInputValue('');
  };

  return (
    <div className="welcome">
      <div className="welcome-head">
        <div className="welcome-mark">K</div>
        <h1 className="welcome-greeting">{t('welcome_greeting', { defaultValue: 'How can I help with your onboarding?' })}</h1>
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
      />

      <div className="welcome-suggest-grid">
        {quickActions.map((action) => (
          <button
            key={action.label}
            className="welcome-suggest"
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
