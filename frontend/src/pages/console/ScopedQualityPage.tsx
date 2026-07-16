/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { adminApi, type FeedbackReview } from '../../api/admin';
import { useAuthorization } from '../../auth/CapabilityProvider';

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
    <div className="page">
      <div className="page-inner">
        <header className="page-head">
          <h1 className="page-title">Workspace quality</h1>
          <p style={{ color: 'var(--color-text-secondary)' }}>
            Feedback is restricted to the selected workspace. Global reports and exports are not loaded here.
          </p>
        </header>
        {loading && <p role="status">Loading feedback...</p>}
        {error && <p role="alert">Feedback is temporarily unavailable.</p>}
        {!loading && !error && reviews.length === 0 && <p>No feedback awaiting review.</p>}
        <div style={{ display: 'grid', gap: 12, marginTop: 20 }}>
          {reviews.map((review) => (
            <article key={review.id} className="glass-panel" style={{ padding: 20, borderRadius: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                <div>
                  <strong>{review.feedback_type}</strong>
                  <p style={{ color: 'var(--color-text-secondary)' }}>{review.comment || 'No comment'}</p>
                  <small>{review.status}</small>
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
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}
