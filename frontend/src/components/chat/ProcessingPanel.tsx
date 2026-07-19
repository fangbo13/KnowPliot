/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type {
  AnswerMode,
  Citation,
  ChatExecutionSnapshot,
  ProcessingTimings,
  SafeProcessingPhase,
} from '../../store/chatStore';

interface ProcessingPanelProps {
  answerMode: AnswerMode;
  phase: SafeProcessingPhase;
  timings?: ProcessingTimings;
  citations: Citation[];
  /** Read-only server snapshot; never populated from composer controls. */
  executionSnapshot?: ChatExecutionSnapshot | null;
  /** Backwards-compatible aliases for callers that use generic snapshot names. */
  snapshot?: ChatExecutionSnapshot | null;
  effectiveSnapshot?: ChatExecutionSnapshot | null;
}

function formatDuration(value: number | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null;
  if (value < 1_000) return `${Math.round(value)} ms`;
  return `${(value / 1_000).toFixed(1)} s`;
}

const SAFE_FALLBACK_CODES = new Set([
  'deep_mode_disabled',
  'thinking_mode_disabled',
  'deep_policy_unavailable',
  'thinking_not_allowed',
  'thinking_budget_invalid',
  'model_policy_not_ready',
  'legacy_thinking_unknown',
]);

function fallbackLabel(code: string | undefined, t: (key: string, options?: Record<string, unknown>) => string): string | null {
  if (!code) return null;
  const safeCode = SAFE_FALLBACK_CODES.has(code) ? code : 'policy_fallback';
  return t(`processing_fallback_${safeCode}`);
}

/** Renders only application-owned progress and permission-safe citation titles. */
export default function ProcessingPanel({
  answerMode,
  phase,
  timings = {},
  citations,
  executionSnapshot = null,
  snapshot = null,
  effectiveSnapshot = null,
}: ProcessingPanelProps) {
  const { t } = useTranslation('chat');
  const resolvedSnapshot = executionSnapshot ?? effectiveSnapshot ?? snapshot;
  const [expanded, setExpanded] = useState(true);
  const basisTitles = useMemo(
    () => [...new Set(citations.map((citation) => citation.document_title.trim()).filter(Boolean))].slice(0, 3),
    [citations],
  );
  const timingRows = [
    ['processing_connection', formatDuration(timings.connectionMs)],
    ['processing_first_answer', formatDuration(timings.firstAnswerMs)],
    ['processing_total', formatDuration(timings.totalMs)],
  ].filter((row): row is [string, string] => row[1] !== null);

  const requestedMode = resolvedSnapshot?.requested_answer_mode
    ?? resolvedSnapshot?.requestedAnswerMode;
  const effectiveMode = resolvedSnapshot?.answer_mode
    ?? resolvedSnapshot?.effectiveAnswerMode
    ?? answerMode;
  const snapshotKnown = Boolean(resolvedSnapshot) && (resolvedSnapshot?.thinking_snapshot_known
    ?? resolvedSnapshot?.thinkingSnapshotKnown) !== false;
  const requestedThinking = resolvedSnapshot?.requested_thinking_enabled
    ?? resolvedSnapshot?.requestedThinkingEnabled;
  const effectiveThinking = resolvedSnapshot?.thinking_enabled
    ?? resolvedSnapshot?.thinkingEnabled;
  const thinkingBudget = resolvedSnapshot?.thinking_budget
    ?? resolvedSnapshot?.thinkingBudget;
  const modelId = resolvedSnapshot?.model_id ?? resolvedSnapshot?.modelId;
  const rawFallbackCode = resolvedSnapshot?.policy_fallback_code
    ?? resolvedSnapshot?.policyFallbackCode
    ?? '';
  const fallbackCode = rawFallbackCode || (!snapshotKnown ? 'legacy_thinking_unknown' : '');
  const requestedThinkingLabel = !snapshotKnown
    ? t('processing_legacy_unknown')
    : requestedThinking
      ? t('thinking_mode_on')
      : t('thinking_mode_off');
  const effectiveThinkingLabel = !snapshotKnown
    ? t('processing_legacy_unknown')
    : effectiveThinking
      ? t('thinking_mode_on')
      : t('thinking_mode_off');
  const budgetLabel = !snapshotKnown
    ? t('processing_legacy_unknown')
    : effectiveThinking && thinkingBudget != null
      ? String(thinkingBudget)
      : t('processing_budget_not_applicable');
  const modelLabel = modelId || t('processing_legacy_unknown');
  const fallback = fallbackLabel(fallbackCode, t);
  const fallbackCodeLabel = fallbackCode && SAFE_FALLBACK_CODES.has(fallbackCode)
    ? fallbackCode
    : fallbackCode ? 'policy_fallback' : null;

  return (
    <section className="processing-panel" aria-label={t('processing_panel_label')}>
      <button
        type="button"
        className="processing-panel-toggle"
        aria-label={t('processing_panel_toggle')}
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="processing-panel-dot" aria-hidden="true" />
        <span>{t(`processing_phase_${phase}`)}</span>
        <span className="processing-panel-mode">{t(`answer_mode_${effectiveMode}`)}</span>
      </button>
      {expanded ? (
        <div className="processing-panel-body">
          <dl className="processing-panel-snapshot" aria-label={t('processing_effective_snapshot')}>
            <div>
              <dt>{t('processing_requested_mode')}</dt>
              <dd>{requestedMode ? t(`answer_mode_${requestedMode}`) : t(`answer_mode_${answerMode}`)}</dd>
            </div>
            <div>
              <dt>{t('processing_effective_mode')}</dt>
              <dd>{t(`answer_mode_${effectiveMode}`)}</dd>
            </div>
            <div>
              <dt>{t('processing_model')}</dt>
              <dd>{modelLabel}</dd>
            </div>
            <div>
              <dt>{t('processing_requested_thinking')}</dt>
              <dd>{requestedThinkingLabel}</dd>
            </div>
            <div>
              <dt>{t('processing_effective_thinking')}</dt>
              <dd>{effectiveThinkingLabel}</dd>
            </div>
            <div>
              <dt>{t('processing_budget')}</dt>
              <dd>{budgetLabel}</dd>
            </div>
            {fallback ? (
              <div>
                <dt>{t('processing_fallback')}</dt>
                <dd>
                  <span>{fallback}</span>
                  {fallbackCodeLabel ? <code data-testid="processing-fallback-code">{fallbackCodeLabel}</code> : null}
                </dd>
              </div>
            ) : null}
          </dl>
          {timingRows.length > 0 ? (
            <dl className="processing-panel-timings">
              {timingRows.map(([label, value]) => (
                <div key={label}>
                  <dt>{t(label)}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {basisTitles.length > 0 ? (
            <div className="processing-panel-basis">
              <span>{t('processing_answer_basis')}</span>
              <ul>{basisTitles.map((title) => <li key={title}>{title}</li>)}</ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
