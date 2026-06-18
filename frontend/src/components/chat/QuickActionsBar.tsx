import { Button, Space } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';

interface Props {
  onQuickAction: (question: string) => void;
}

const actions = [
  "How do I set up my company email?",
  "What is the expense reimbursement process?",
  "How many annual leave days do I have?",
  "Where is my office?",
  "Who is my buddy/mentor?",
];

export default function QuickActionsBar({ onQuickAction }: Props) {
  return (
    <div style={{ padding: '8px 0', borderTop: '1px solid #f0f0f0' }}>
      <Space wrap>
        {actions.map((q) => (
          <Button
            key={q}
            size="small"
            icon={<QuestionCircleOutlined />}
            onClick={() => onQuickAction(q)}
          >
            {q}
          </Button>
        ))}
      </Space>
    </div>
  );
}
