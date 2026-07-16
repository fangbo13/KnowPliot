/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

export default function ConsoleOverviewPage({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="page">
      <div className="page-inner">
        <header className="page-head">
          <h1 className="page-title">{title}</h1>
          <p style={{ maxWidth: 720, color: 'var(--color-text-secondary)', lineHeight: 1.7 }}>
            {description}
          </p>
        </header>
        <section className="glass-panel" style={{ marginTop: 24, padding: 28, borderRadius: 16 }}>
          <h2 style={{ marginTop: 0, fontFamily: 'var(--font-family-display)' }}>Your scope</h2>
          <p style={{ marginBottom: 0, color: 'var(--color-text-secondary)' }}>
            Navigation and actions in this console are resolved from the server capability contract.
          </p>
        </section>
      </div>
    </div>
  );
}
