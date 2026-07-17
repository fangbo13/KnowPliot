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
  ProcessingTimings,
  SafeProcessingPhase,
} from '../../store/chatStore';

interface ProcessingPanelProps {
  answerMode: AnswerMode;
  phase: SafeProcessingPhase;
  timings?: ProcessingTimings;
  citations: Citation[];
}

function formatDuration(value: number | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null;
  if (value < 1_000) return `${Math.round(value)} ms`;
  return `${(value / 1_000).toFixed(1)} s`;
}

/** Renders only application-owned progress and permission-safe citation titles. */
export default function ProcessingPanel({
  answerMode,
  phase,
  timings = {},
  citations,
}: ProcessingPanelProps) {
  const { t } = useTranslation('chat');
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
        <span className="processing-panel-mode">{t(`answer_mode_${answerMode}`)}</span>
      </button>
      {expanded ? (
        <div className="processing-panel-body">
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
