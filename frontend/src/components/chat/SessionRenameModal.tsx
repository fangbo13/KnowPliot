import { Modal, Input, type InputRef } from 'antd';
import { useEffect, useRef, useState } from 'react';

type Props = {
  open: boolean;
  initialTitle: string;
  title: string;
  okText: string;
  cancelText: string;
  placeholder: string;
  onCancel: () => void;
  onConfirm: (nextTitle: string) => Promise<void> | void;
};

export default function SessionRenameModal({
  open,
  initialTitle,
  title,
  okText,
  cancelText,
  placeholder,
  onCancel,
  onConfirm,
}: Props) {
  const [value, setValue] = useState(initialTitle);
  const inputRef = useRef<InputRef>(null);

  useEffect(() => {
    if (!open) return;
    setValue(initialTitle);
    const timer = window.setTimeout(() => inputRef.current?.focus({ cursor: 'all' }), 80);
    return () => window.clearTimeout(timer);
  }, [open, initialTitle]);

  return (
    <Modal
      open={open}
      title={title}
      okText={okText}
      cancelText={cancelText}
      onCancel={onCancel}
      onOk={() => onConfirm(value.trim())}
      destroyOnHidden
    >
      <Input
        ref={inputRef}
        value={value}
        maxLength={120}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onPressEnter={() => onConfirm(value.trim())}
      />
    </Modal>
  );
}
