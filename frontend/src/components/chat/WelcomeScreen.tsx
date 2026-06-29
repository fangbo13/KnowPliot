import { useTranslation } from 'react-i18next';
import { Row, Col, Typography, Card } from 'antd';
import {
  LaptopOutlined,
  DollarOutlined,
  CalendarOutlined,
  BookOutlined,
  EnvironmentOutlined,
  TeamOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useChatStore } from '../../store/chatStore';
import { useState, useRef, useEffect, useMemo } from 'react';
import ChatComposer from './ChatComposer';

const { Title, Text } = Typography;

interface WelcomeScreenProps {
  onQuickAction: (q: string) => void;
  onSendMessage?: (msg: string) => void;
}

export default function WelcomeScreen({ onQuickAction, onSendMessage }: WelcomeScreenProps) {
  const { t, i18n } = useTranslation('chat');
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<any>(null);
  const isChinese = i18n.language?.startsWith('zh');
  const isSendLocked = useChatStore(state => state.isSendLocked);
  const streamPhase = useChatStore(state => state.streamPhase);
  const streamingSessionId = useChatStore(state => state.streamingSessionId);
  const activeSessionId = useChatStore(state => state.activeSessionId);
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

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = () => {
    if (!inputValue.trim() || isSendLocked || isStreaming) return;
    if (onSendMessage) {
      onSendMessage(inputValue.trim());
    } else {
      onQuickAction(inputValue.trim());
    }
    setInputValue('');
  };

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{
        background: 'var(--color-fill)',
        border: '1px solid var(--color-border-secondary)',
        borderRadius: 'var(--radius-lg)',
        padding: '12px 20px',
        marginBottom: 24,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        animation: 'fadeInUp 0.5s ease-out 0.1s both',
      }}>
        <RocketOutlined style={{ fontSize: 18, color: 'var(--accent)', flexShrink: 0 }} />
        <Text style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
          {t('welcome_tip')}
        </Text>
      </div>

      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 72,
          height: 72,
          borderRadius: 18,
          background: 'var(--gradient-accent)',
          marginBottom: 20,
          boxShadow: 'var(--shadow-accent-lg), var(--shadow-sm)',
          animation: 'fadeInUp 0.5s ease-out',
        }}>
          <span style={{
            fontSize: 32,
            fontWeight: 800,
            color: '#FFFFFF',
            letterSpacing: -1,
          }}>EY</span>
        </div>
        <Title level={3} style={{
          fontWeight: 400,
          color: 'var(--color-text, #0F172A)',
          marginTop: 8,
          fontFamily: "'Calistoga', Georgia, serif",
        }}>
          {t('title')}
        </Title>
      </div>

      <div style={{
        maxWidth: 680,
        margin: '0 auto',
        animation: 'fadeInUp 0.4s ease-out 0.2s both',
      }}>
        <ChatComposer
          value={inputValue}
          onChange={setInputValue}
          onSubmit={handleSend}
          placeholder={t('placeholder') || 'Type your question here...'}
          ariaLabel={t('chat_input_label') || 'Type your message'}
          isStreaming={isStreaming}
          disabled={isSendLocked}
          multiline={false}
          inputRef={inputRef}
          autoFocus
          maxRows={1}
        />
      </div>

      <Card
        title={t('quick_actions_title') || 'Common questions'}
        bordered={false}
        style={{
          background: 'var(--color-bg-container, white)',
          borderColor: 'var(--color-border-secondary, #f0f0f0)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          animation: 'fadeInUp 0.4s ease-out 0.3s both',
          marginTop: 24,
        }}
      >
        <Row gutter={[16, 16]}>
          {quickActions.map((action) => (
            <Col xs={24} sm={12} md={8} key={action.label}>
              <div
                className="welcome-card"
                onClick={() => onQuickAction(action.question)}
                role="button"
                tabIndex={0}
                aria-label={`${action.label}: ${action.question}`}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onQuickAction(action.question);
                  }
                }}
                style={{
                  background: 'var(--color-bg-container)',
                  border: '1px solid var(--color-border-secondary)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '16px',
                  cursor: 'pointer',
                  minHeight: 72,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ color: 'var(--accent)', fontSize: 16 }}>{action.icon}</span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{action.label}</span>
                </div>
                <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.4 }}>
                  {action.question}
                </Text>
              </div>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
}
