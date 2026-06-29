import { useTranslation } from 'react-i18next';
import { Row, Col, Typography, Card, Input } from 'antd';
import {
  LaptopOutlined,
  DollarOutlined,
  CalendarOutlined,
  BookOutlined,
  EnvironmentOutlined,
  TeamOutlined,
  SendOutlined,
  StopOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useChatStore } from '../../store/chatStore';
import { abortActiveStream } from '../../stream/StreamLifecycleManager';
import { useState, useRef, useEffect } from 'react';

const { Title, Text } = Typography;

const quickActions = [
  { icon: <LaptopOutlined />, question: "如何设置公司邮箱和电脑？", label: "IT 设置" },
  { icon: <DollarOutlined />, question: "报销流程是什么？", label: "报销流程" },
  { icon: <CalendarOutlined />, question: "我有多少天年假？", label: "年假天数" },
  { icon: <BookOutlined />, question: "入职培训包含哪些课程？", label: "培训课程" },
  { icon: <EnvironmentOutlined />, question: "办公室在哪里，怎么去？", label: "办公位置" },
  { icon: <TeamOutlined />, question: "我的导师/搭档是谁？", label: "我的导师" },
];
 
interface WelcomeScreenProps {
  onQuickAction: (q: string) => void;
  onSendMessage?: (msg: string) => void;
}

export default function WelcomeScreen({ onQuickAction, onSendMessage }: WelcomeScreenProps) {
  const { t } = useTranslation('chat');
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<any>(null);
  // V3.5 HIGH-001: Read send lock from store to prevent double-send
  const isSendLocked = useChatStore(state => state.isSendLocked);
  const streamPhase = useChatStore(state => state.streamPhase);
  const streamingSessionId = useChatStore(state => state.streamingSessionId);
  const activeSessionId = useChatStore(state => state.activeSessionId);
  // V4.6: Only show streaming UI when the stream belongs to the active session
  const isStreaming = streamPhase !== 'idle' && streamingSessionId === activeSessionId;

  // Auto-focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // V3.5 HIGH-001: handleSend checks isSendLocked
  const handleSend = () => {
    if (!inputValue.trim() || isSendLocked || isStreaming) return;
    if (onSendMessage) {
      onSendMessage(inputValue.trim());
    } else {
      // Fallback: treat as quick action
      onQuickAction(inputValue.trim());
    }
    setInputValue('');
  };

  // V4.0 UI-HIGH-001: Stop generation handler (same logic as ChatPage)
  const handleStop = () => {
    abortActiveStream();
  };

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      {/* Onboarding tip for first-time users */}
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

      {/* Chat Input Box */}
      <div style={{
        maxWidth: 680,
        margin: '0 auto',
        animation: 'fadeInUp 0.4s ease-out 0.2s both',
      }}>
        <div
          className="chat-input-container"
          style={{
            background: 'var(--color-bg-container)',
            border: '1.5px solid var(--color-border)',
            borderRadius: 24,
            padding: '12px 16px',
            boxShadow: 'var(--shadow-md)',
            transition: 'box-shadow 0.25s ease, border-color 0.25s ease',
          }}
        >
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}>
            <Input
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onPressEnter={handleSend}
              placeholder={t('placeholder') || "在此输入你的问题..."}
              maxLength={4000}
              disabled={isSendLocked || isStreaming}
              className="chat-input-singleline"
              aria-label={t('chat_input_label') || "输入你的问题"}
              style={{
                border: 'none',
                boxShadow: 'none',
                fontSize: 15,
                padding: '4px 0',
                background: 'transparent',
              }}
            />
            {isStreaming ? (
              <button
                className="chat-input-stop-btn"
                onClick={handleStop}
                aria-label={t('stop_generation') || '停止生成'}
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
                className="chat-input-send-btn"
                onClick={handleSend}
                disabled={!inputValue.trim() || isSendLocked || isStreaming}
                aria-label={t('send_message') || '发送'}
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 20,
                  border: 'none',
                  background: inputValue.trim() ? 'var(--gradient-accent)' : 'var(--color-border)',
                  color: inputValue.trim() ? '#fff' : 'var(--color-text-tertiary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: inputValue.trim() ? 'pointer' : 'default',
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
      </div>

      <Card
        title={t('quick_actions_title') || '常见问题'}
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
