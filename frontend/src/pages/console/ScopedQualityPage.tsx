/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { adminApi, type FeedbackReview } from '../../api/admin';
import { useAuthorization } from '../../auth/CapabilityProvider';
import { EmptyState, PageHeader, Status, Surface } from '../../design/primitives';

export default function ScopedQualityPage() {
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
        title="Workspace quality"
        description="Feedback is restricted to the selected workspace. Global reports and exports are not loaded here."
      />
      {loading && <Status role="status" tone="info">Loading feedback...</Status>}
      {error && <Status role="alert" tone="error">Feedback is temporarily unavailable.</Status>}
      {!loading && !error && reviews.length === 0 && (
        <Surface><EmptyState title="No feedback awaiting review" /></Surface>
      )}
      <div className="kp-quality-list">
        {reviews.map((review) => (
          <Surface as="article" key={review.id} className="kp-quality-review">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                <div>
                  <strong>{review.feedback_type}</strong>
                  <p style={{ color: 'var(--color-text-secondary)' }}>{review.comment || 'No comment'}</p>
                  <Status tone="neutral">{review.status}</Status>
                </div>
                {canReview && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                    <button type="button" onClick={() => void mutate(() => adminApi.claimFeedback(review.id))}>
                      Claim
                    </button>
                    <button
                      type="button"
                      onClick={() => void mutate(() => adminApi.resolveFeedback(review.id, { resolution_code: 'resolved' }))}
                    >
                      Resolve
                    </button>
                  </div>
                )}
              </div>
          </Surface>
        ))}
      </div>
    </div>
  );
}
