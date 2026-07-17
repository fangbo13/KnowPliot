// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ChatComposer from './ChatComposer';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@ant-design/icons', () => ({
  SendOutlined: () => null,
  ArrowUpOutlined: () => null,
}));

const baseProps = {
  value: 'Question',
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  placeholder: 'Ask',
  ariaLabel: 'Question',
  isStreaming: false,
};

describe('ChatComposer answer mode control', () => {
  afterEach(cleanup);

  it('shows governed deep alongside fast and reports an explicit selection', () => {
    const onAnswerModeChange = vi.fn();

    render(<ChatComposer {...({
      ...baseProps,
      answerMode: 'fast',
      canUseDeep: true,
      onAnswerModeChange,
    } as any)} />);

    expect(screen.getByRole('button', { name: 'answer_mode_fast' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'answer_mode_deep' }));
    expect(onAnswerModeChange).toHaveBeenCalledWith('deep');
  });

  it('does not render a deep affordance when server eligibility is absent', () => {
    render(<ChatComposer {...({
      ...baseProps,
      answerMode: 'fast',
      canUseDeep: false,
      onAnswerModeChange: vi.fn(),
    } as any)} />);

    expect(screen.getByRole('button', { name: 'answer_mode_fast' })).not.toBeNull();
    expect(screen.queryByRole('button', { name: 'answer_mode_deep' })).toBeNull();
  });
});
