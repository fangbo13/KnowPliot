import { useTranslation } from 'react-i18next';
import { Row, Col, Typography, Card, Input, Button, Space } from 'antd';
import {
  LaptopOutlined,
  DollarOutlined,
  CalendarOutlined,
  BookOutlined,
  EnvironmentOutlined,
  TeamOutlined,
  SendOutlined,
  RocketOutlined,
} from '@ant-design/icons';
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

  // Auto-focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = () => {
    if (!inputValue.trim()) return;
    if (onSendMessage) {
      onSendMessage(inputValue.trim());
    } else {
      // Fallback: treat as quick action
      onQuickAction(inputValue.trim());
    }
    setInputValue('');
  };

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      {/* Onboarding tip for first-time users */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(0, 82, 255, 0.06), rgba(77, 124, 255, 0.04))',
        border: '1px solid rgba(0, 82, 255, 0.15)',
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
          background: 'linear-gradient(135deg, #0052FF, #4D7CFF)',
          marginBottom: 20,
          boxShadow: '0 8px 24px rgba(0, 82, 255, 0.25), 0 2px 8px rgba(0, 82, 255, 0.15)',
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
        <Text type="secondary" style={{ display: 'block', maxWidth: 480, margin: '0 auto' }}>
          {t('welcome_message')}
        </Text>
      </div>

      {/* Chat Input Box - NEW */}
      <div style={{
        maxWidth: 680,
        margin: '0 auto 32px',
        animation: 'fadeInUp 0.4s ease-out 0.2s both',
      }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onPressEnter={handleSend}
            placeholder={t('placeholder') || "在此输入你的问题..."}
            size="large"
            maxLength={4000}
            style={{
              borderRadius: 'var(--radius-lg) 0 0 var(--radius-lg)',
              borderRight: 'none',
            }}
            aria-label={t('chat_input_label') || "输入你的问题"}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!inputValue.trim()}
            size="large"
            style={{
              minWidth: 56,
              padding: inputValue.trim() ? '0 16px' : '0 20px',
              fontWeight: 600,
              borderRadius: '0 var(--radius-lg) var(--radius-lg) 0',
            }}
          />
        </Space.Compact>
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
