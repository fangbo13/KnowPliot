import { describe, expect, it } from 'vitest';

import pageSource from './AdminTemplatesPage.tsx?raw';
import apiSource from '../../api/templates.ts?raw';


describe('Scenario Templates v3 contract', () => {
  it('explains the versioned starting-point and excluded-content boundary', () => {
    expect(pageSource).toContain("t('admin_template_contract_title')");
    expect(pageSource).toContain("t('admin_template_contract_description')");
    expect(pageSource).toContain("t('admin_template_create_snapshot_notice')");
    expect(pageSource).not.toContain('/assets/');
    expect(pageSource).not.toContain('retry-assets');
  });

  it('submits template-backed creation as an idempotent governed operation', () => {
    expect(apiSource).toContain("'Idempotency-Key': crypto.randomUUID()");
    expect(apiSource).toContain('current_revision_id: string | null');
    expect(apiSource).toContain('snapshot_hash: string');
    expect(pageSource).toContain('expected_revision_hash: rev.snapshot_hash');
    expect(apiSource).toContain('/revisions/${revisionId}/preview/');
    expect(apiSource).toContain('/revisions/${revisionId}/activate/');
  });
});
