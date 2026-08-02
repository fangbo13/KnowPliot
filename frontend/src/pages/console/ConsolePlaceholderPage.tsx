/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Dark/i18n/Layout spec §B2/§C: i18n-driven, migrated to PageHeader/Surface.

import { useTranslation } from 'react-i18next';

import { PageHeader, Surface } from '../../design/primitives';

export default function ConsolePlaceholderPage({ title }: { title: string }) {
  const { t } = useTranslation('common');
  return (
    <div className="page section-enter">
      <PageHeader title={t(title, title)} />
      <Surface as="section" tone="subtle">
        <p style={{ margin: 0, color: 'var(--color-text-secondary)' }}>
          {t('console_placeholder_desc')}
        </p>
      </Surface>
    </div>
  );
}
