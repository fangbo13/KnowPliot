/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useState } from 'react';
import { Button } from 'antd';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { adminApi, type FeedbackReview } from '../../api/admin';
import { useAuthorization } from '../../auth/CapabilityProvider';
import { EmptyState, PageHeader, Status, Surface } from '../../design/primitives';

export default function ScopedQualityPage() {
  const { t } = useTranslation('common');
  const { spaceId } = useParams<{ spaceId: string }>();
  const access = useAuthorization();
  const [reviews, setReviews] = useState<FeedbackReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    if (!spaceId) return;
    setLoading(true);
    setError(false);
    try {
      setReviews(await adminApi.feedbackReviews({ space: spaceId }));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [spaceId]);

  useEffect(() => { void load(); }, [load]);

  const mutate = async (operation: () => Promise<FeedbackReview>) => {
    await operation();
    await load();
  };

  const canReview = access.has('quality.review');
  return (
    <div>
      <PageHeader
        title={t('scoped_quality_title')}
        description={t('scoped_quality_description')}
      />
      {loading && <Status role="status" tone="info">{t('loading')}</Status>}
      {error && <Status role="alert" tone="error">{t('scoped_quality_unavailable')}</Status>}
      {!loading && !error && reviews.length === 0 && (
        <Surface><EmptyState title={t('scoped_quality_empty')} /></Surface>
      )}
      <div className="kp-quality-list">
        {reviews.map((review) => (
          <Surface as="article" key={review.id} className="kp-quality-review">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                <div>
                  <strong>{review.feedback_type}</strong>
                  <p style={{ color: 'var(--color-text-secondary)' }}>{review.comment || t('scoped_quality_no_comment')}</p>
                  <Status tone="neutral">{review.status}</Status>
                </div>
                {canReview && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                    <Button size="small" onClick={() => void mutate(() => adminApi.claimFeedback(review.id))}>
                      {t('quality_claim')}
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      onClick={() => void mutate(() => adminApi.resolveFeedback(review.id, { resolution_code: 'resolved' }))}
                    >
                      {t('quality_resolve')}
                    </Button>
                  </div>
                )}
              </div>
          </Surface>
        ))}
      </div>
    </div>
  );
}
