/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Dark/i18n/Layout spec §B2: title/description accept i18n keys (falling back
// to the raw string so existing tests keep passing).

import { useTranslation } from 'react-i18next';

import { PageHeader, Surface } from '../../design/primitives';

export default function ConsoleOverviewPage({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  const { t } = useTranslation('common');
  return (
    <div>
      <PageHeader title={t(title, title)} description={t(description, description)} />
      <Surface as="section" tone="subtle" className="kp-console-overview-surface">
        <h2>{t('console_overview_scope_title')}</h2>
        <p>{t('console_overview_scope_desc')}</p>
      </Surface>
    </div>
  );
}
