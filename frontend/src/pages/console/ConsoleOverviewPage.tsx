/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { PageHeader, Surface } from '../../design/primitives';

export default function ConsoleOverviewPage({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <Surface as="section" tone="subtle" className="kp-console-overview-surface">
        <h2>Your scope</h2>
        <p>Navigation and actions in this console are resolved from the server capability contract.</p>
      </Surface>
    </div>
  );
}
