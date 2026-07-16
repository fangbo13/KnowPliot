/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import {
  scopedConsoleApi,
  type SpaceAccessRequest,
} from '../../api/scopedConsole';

export default function AccessRequestsPage() {
  const { spaceId } = useParams<{ spaceId: string }>();
  const [requests, setRequests] = useState<SpaceAccessRequest[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!spaceId) {
      setLoading(false);
      return;
    }
    void scopedConsoleApi.accessRequests(spaceId).then(
      (rows) => {
        if (!cancelled) {
          setRequests(rows);
          setLoading(false);
        }
      },
      () => { if (!cancelled) setLoading(false); },
    );
    return () => { cancelled = true; };
  }, [spaceId]);

  return (
    <div className="page">
      <div className="page-inner">
        <header className="page-head"><h1 className="page-title">Access requests</h1></header>
        {loading && <p role="status">Loading requests…</p>}
        {!loading && requests.length === 0 && <p>No pending requests in this workspace.</p>}
        <ul>
          {requests.map((request) => (
            <li key={request.id}>{request.user_email ?? request.user} — {request.status}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
