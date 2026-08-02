import { BookOutlined, ClockCircleOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import type { SpaceRole } from '../api/spaces';
import { AppShell, EmptyState, PageHeader, Status, Surface } from '../design/primitives';
import { useSpaceStore } from '../store/spaceStore';

const RECENT_KEY = 'knowpilot-recent-knowledge-spaces';
const MANAGING_ROLES: ReadonlySet<SpaceRole> = new Set(['owner', 'space_admin', 'knowledge_admin', 'reviewer']);

function readRecent(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').slice(0, 5) : [];
  } catch {
    return [];
  }
}

export default function KnowledgeSpacesPage() {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const { spaces, loading, error, loadSpaces, setActiveSpace } = useSpaceStore();
  const [query, setQuery] = useState('');
  const [recentIds, setRecentIds] = useState(readRecent);
  const [enteringId, setEnteringId] = useState<string | null>(null);

  useEffect(() => {
    if (!spaces.length && !loading) void loadSpaces();
  }, [loadSpaces, loading, spaces.length]);

  const visibleSpaces = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const filtered = spaces.filter((space) => !normalized
      || space.name.toLocaleLowerCase().includes(normalized)
      || space.description?.toLocaleLowerCase().includes(normalized));
    return filtered.sort((left, right) => {
      const leftIndex = recentIds.indexOf(left.id);
      const rightIndex = recentIds.indexOf(right.id);
      if (leftIndex === -1 && rightIndex === -1) return left.name.localeCompare(right.name);
      if (leftIndex === -1) return 1;
      if (rightIndex === -1) return -1;
      return leftIndex - rightIndex;
    });
  }, [query, recentIds, spaces]);

  const enter = async (spaceId: string) => {
    setEnteringId(spaceId);
    try {
      await setActiveSpace(spaceId);
      const next = [spaceId, ...recentIds.filter((id) => id !== spaceId)].slice(0, 5);
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      setRecentIds(next);
      navigate(`/workspace/${spaceId}/knowledge`);
    } finally {
      setEnteringId(null);
    }
  };

  return (
    <AppShell width="management" className="kp-knowledge-spaces section-enter">
      <PageHeader
        eyebrow={t('nav_knowledge')}
        title={t('knowledge_spaces_title')}
        description={t('knowledge_spaces_description')}
      />
      <div className="kp-directory-toolbar">
        <SearchOutlined aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('knowledge_spaces_search')}
          aria-label={t('knowledge_spaces_search')}
        />
      </div>
      {error ? <div role="alert" className="kp-inline-error">{error}</div> : null}
      {!loading && visibleSpaces.length === 0 ? (
        <EmptyState icon={<BookOutlined />} title={t('knowledge_spaces_empty')} body={t('knowledge_spaces_empty_body')} />
      ) : (
        <div className="kp-directory-grid" aria-busy={loading}>
          {visibleSpaces.map((space) => {
            const recent = recentIds.includes(space.id);
            return (
              <Surface as="article" className="kp-directory-card" key={space.id}>
                <div className="kp-directory-card__mark"><BookOutlined /></div>
                <div className="kp-directory-card__copy">
                  <div className="kp-directory-card__meta">
                    <Status tone={space.my_role === 'guest' ? 'neutral' : 'info'}>{space.my_role}</Status>
                    {recent ? <span><ClockCircleOutlined /> {t('knowledge_spaces_recent')}</span> : null}
                  </div>
                  <h2>{space.name}</h2>
                  <p>{space.description || t('knowledge_spaces_no_description')}</p>
                </div>
                <div className="kp-directory-card__actions">
                  <button
                    type="button"
                    className="primary-btn"
                    disabled={enteringId === space.id}
                    onClick={() => void enter(space.id)}
                  >
                    {t('knowledge_spaces_enter')}
                  </button>
                  {space.my_role && MANAGING_ROLES.has(space.my_role) ? (
                    <Link className="secondary-btn" to={`/workspace/${space.id}/manage`}>
                      <SettingOutlined /> {t('knowledge_spaces_manage')}
                    </Link>
                  ) : null}
                </div>
              </Surface>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
