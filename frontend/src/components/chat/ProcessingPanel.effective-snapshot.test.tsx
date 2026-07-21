// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProcessingPanel from './ProcessingPanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const baseProps = {
  answerMode: 'deep' as const,
  phase: 'generating' as const,
  citations: [],
};

describe('ProcessingPanel effective execution snapshot', () => {
  afterEach(cleanup);

  it('renders effective mode/model/thinking/budget and bounded fallback read-only', () => {
    render(<ProcessingPanel {...baseProps} executionSnapshot={{
      requested_answer_mode: 'deep',
      answer_mode: 'fast',
      requested_thinking_enabled: true,
      thinking_enabled: false,
      thinking_snapshot_known: true,
      thinking_budget: null,
      model_id: 'qwen3.6-flash',
      policy_fallback_code: 'thinking_budget_invalid',
    }} />);

    expect(screen.getAllByText('answer_mode_fast').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('qwen3.6-flash')).toBeTruthy();
    expect(screen.getByText('thinking_mode_on')).toBeTruthy();
    expect(screen.getByText('thinking_mode_off')).toBeTruthy();
    expect(screen.getByText('processing_budget_not_applicable')).toBeTruthy();
    expect(screen.getByText('processing_fallback_thinking_budget_invalid')).toBeTruthy();
    expect(screen.queryByText('reasoning_content')).toBeNull();
  });

  it('labels migrated unknown thinking details as legacy/unknown', () => {
    render(<ProcessingPanel {...baseProps} executionSnapshot={{
      requested_answer_mode: 'fast',
      answer_mode: 'fast',
      requested_thinking_enabled: false,
      thinking_enabled: false,
      thinking_snapshot_known: false,
      thinking_budget: null,
      model_id: 'legacy-model',
      policy_fallback_code: 'legacy_thinking_unknown',
    }} />);

    expect(screen.getAllByText('processing_legacy_unknown').length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText('thinking_mode_off')).toBeNull();
  });
});
