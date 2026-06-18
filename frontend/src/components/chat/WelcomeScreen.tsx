import { Button, Row, Col, Typography, Card } from 'antd';
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
    <div>
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <Title level={2} style={{ color: '#E00033' }}>EY</Title>
        <Title level={4} style={{ fontWeight: 400, color: '#333' }}>
          Onboarding Assistant
        </Title>
        <Text type="secondary">
          Hi! I'm your EY Onboarding Assistant. Ask me anything about your onboarding process, company policies, benefits, and more.
        </Text>
      </div>

      <Card title="Common Questions" bordered={false}>
        <Row gutter={[16, 16]}>
          {quickActions.map((action) => (
            <Col xs={24} sm={12} md={8} key={action.label}>
              <Button
                block
                icon={action.icon}
                onClick={() => onQuickAction(action.question)}
                style={{
                  textAlign: 'left',
                  height: 'auto',
                  padding: '12px 16px',
                }}
              >
                <div style={{ fontWeight: 500 }}>{action.label}</div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {action.question}
                </Text>
              </Button>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
}
