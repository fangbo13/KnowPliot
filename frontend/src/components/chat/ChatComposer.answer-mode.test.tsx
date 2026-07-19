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

  it('renders the independent thinking switch only when all gates are already true', () => {
    const onThinkingChange = vi.fn();
    const { rerender } = render(<ChatComposer {...({
      ...baseProps,
      canUseThinking: true,
      thinkingEnabled: false,
      onThinkingChange,
    } as any)} />);

    const control = screen.getByRole('switch', { name: 'thinking_mode_label' });
    expect(control.getAttribute('aria-checked')).toBe('false');
    fireEvent.click(control);
    expect(onThinkingChange).toHaveBeenCalledWith(true);

    rerender(<ChatComposer {...({
      ...baseProps,
      canUseThinking: false,
      thinkingEnabled: true,
      onThinkingChange,
    } as any)} />);
    expect(screen.queryByRole('switch', { name: 'thinking_mode_label' })).toBeNull();
  });

  it('keeps thinking independent from fast/deep mode controls', () => {
    const onAnswerModeChange = vi.fn();
    const onThinkingChange = vi.fn();
    render(<ChatComposer {...({
      ...baseProps,
      answerMode: 'deep',
      canUseDeep: true,
      thinkingEnabled: true,
      canUseThinking: true,
      onAnswerModeChange,
      onThinkingChange,
    } as any)} />);

    fireEvent.click(screen.getByRole('button', { name: 'answer_mode_fast' }));
    expect(onAnswerModeChange).toHaveBeenCalledWith('fast');
    expect(screen.getByRole('switch', { name: 'thinking_mode_label' }).getAttribute('aria-checked')).toBe('true');
    fireEvent.click(screen.getByRole('switch', { name: 'thinking_mode_label' }));
    expect(onThinkingChange).toHaveBeenCalledWith(false);
  });
});
