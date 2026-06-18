import { Row, Col, Typography, Card } from 'antd';
import {
  LaptopOutlined,
  DollarOutlined,
  CalendarOutlined,
  BookOutlined,
  EnvironmentOutlined,
  TeamOutlined,
} from '@ant-design/icons';

const { Title, Text } = Typography;

const quickActions = [
  { icon: <LaptopOutlined />, question: "How do I set up my company email and laptop?", label: "IT Setup" },
  { icon: <DollarOutlined />, question: "What is the expense reimbursement process?", label: "Reimbursement" },
  { icon: <CalendarOutlined />, question: "How many annual leave days do I have?", label: "Annual Leave" },
  { icon: <BookOutlined />, question: "What training courses are included in onboarding?", label: "Training" },
  { icon: <EnvironmentOutlined />, question: "Where is the office and how do I get there?", label: "Office Location" },
  { icon: <TeamOutlined />, question: "Who is my mentor/buddy?", label: "My Buddy" },
];

export default function WelcomeScreen({ onQuickAction }: { onQuickAction: (q: string) => void }) {
  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 72,
          height: 72,
          borderRadius: 18,
          background: 'linear-gradient(145deg, #FFE500 0%, #FDD800 100%)',
          marginBottom: 20,
          boxShadow: '0 8px 24px rgba(255, 229, 0, 0.25), 0 2px 8px rgba(255, 229, 0, 0.15)',
          animation: 'fadeInUp 0.5s ease-out',
        }}>
          <span style={{
            fontSize: 32,
            fontWeight: 800,
            color: '#262626',
            letterSpacing: -1,
          }}>EY</span>
        </div>
        <Title level={3} style={{
          fontWeight: 500,
          color: 'var(--color-text, #333)',
          marginTop: 8,
          fontFamily: 'var(--font-family-display)',
        }}>
          Onboarding Assistant
        </Title>
        <Text type="secondary" style={{ display: 'block', maxWidth: 480, margin: '0 auto' }}>
          Hi! I&apos;m your EY Onboarding Assistant. Ask me anything about your onboarding process, company policies, benefits, and more.
        </Text>
      </div>

      <Card
        title="Common Questions"
        bordered={false}
        style={{
          background: 'var(--color-bg-container, white)',
          borderColor: 'var(--color-border-secondary, #f0f0f0)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <Row gutter={[16, 16]}>
          {quickActions.map((action) => (
            <Col xs={24} sm={12} md={8} key={action.label}>
              <div
                onClick={() => onQuickAction(action.question)}
                style={{
                  background: 'var(--color-bg-container)',
                  border: '1px solid var(--color-border-secondary)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '16px',
                  cursor: 'pointer',
                  transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                  minHeight: 72,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
                onMouseEnter={(e) => {
                  const target = e.currentTarget;
                  target.style.boxShadow = 'var(--shadow-md)';
                  target.style.borderColor = 'var(--ey-yellow)';
                  target.style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={(e) => {
                  const target = e.currentTarget;
                  target.style.boxShadow = '';
                  target.style.borderColor = '';
                  target.style.transform = '';
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ color: 'var(--ey-yellow)', fontSize: 16 }}>{action.icon}</span>
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
