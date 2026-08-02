import { BookOutlined, SearchOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { libraryApi, type ReferenceLibrary } from '../api/knowledge';
import { AppShell, EmptyState, PageHeader, Surface } from '../design/primitives';
import { notify } from '../utils/notifications';

export default function ReferenceLibrariesPage() {
  const { t } = useTranslation('common');
  const [libraries, setLibraries] = useState<ReferenceLibrary[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setLibraries(await libraryApi.catalog());
    } catch {
      void notify('error', t('reference_libraries_load_error'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return libraries.filter((library) => !normalized
      || library.name.toLocaleLowerCase().includes(normalized)
      || (library.description || '').toLocaleLowerCase().includes(normalized)
      || (library.space_name || '').toLocaleLowerCase().includes(normalized));
  }, [libraries, query]);

  const favorites = useMemo(() => libraries
    .filter((library) => library.is_favorite)
    .sort((left, right) => (left.favorite_position || 99) - (right.favorite_position || 99)), [libraries]);
  const favoriteLimitReached = favorites.length >= 5;

  const toggleFavorite = async (library: ReferenceLibrary) => {
    setPendingId(library.id);
    try {
      if (library.is_favorite) await libraryApi.unfavorite(library.id);
      else await libraryApi.favorite(library.id);
      await load();
    } catch {
      void notify('error', t('reference_libraries_favorite_error'));
    } finally {
      setPendingId(null);
    }
  };

  return (
    <AppShell width="management" className="kp-reference-libraries section-enter">
      <PageHeader
        eyebrow={t('nav_reference_libraries')}
        title={t('reference_libraries_title')}
        description={t('reference_libraries_description')}
      />
      <Surface className="kp-reference-favorites" aria-label={t('reference_libraries_favorites_title')}>
        <div className="kp-reference-favorites__intro">
          <div>
            <span className="kp-reference-favorites__eyebrow">{t('reference_libraries_favorites_title')}</span>
            <strong>{t('reference_libraries_favorite_count', { count: favorites.length })}</strong>
          </div>
          <p>{t(favoriteLimitReached
            ? 'reference_libraries_replace_hint'
            : 'reference_libraries_favorites_hint')}</p>
        </div>
        <div className="kp-reference-favorites__slots">
          {Array.from({ length: 5 }, (_, index) => {
            const favorite = favorites[index];
            return (
              <div className={`kp-reference-slot${favorite ? ' is-filled' : ''}`} key={favorite?.id || `empty-${index}`}>
                <span>{index + 1}</span>
                <strong>{favorite?.name || t('reference_libraries_empty_slot')}</strong>
              </div>
            );
          })}
        </div>
      </Surface>
      <div className="kp-directory-toolbar">
        <SearchOutlined aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('reference_libraries_search')}
          aria-label={t('reference_libraries_search')}
        />
        <span>{t('reference_libraries_catalog_count', { count: libraries.length })}</span>
      </div>
      {!loading && visible.length === 0 ? (
        <EmptyState icon={<BookOutlined />} title={t('reference_libraries_empty')} />
      ) : (
        <div className="kp-directory-grid" aria-busy={loading}>
          {visible.map((library) => {
            const requiresReplacement = favoriteLimitReached && !library.is_favorite;
            const actionKey = library.is_favorite
              ? 'reference_libraries_unfavorite'
              : requiresReplacement
                ? 'reference_libraries_replace_required'
                : 'reference_libraries_favorite';
            return (
              <Surface as="article" className={`kp-directory-card${library.is_favorite ? ' is-favorite' : ''}`} key={library.id}>
                <div className="kp-directory-card__mark"><BookOutlined /></div>
                <div className="kp-directory-card__copy">
                  <div className="kp-directory-card__meta">
                    <span>{(library.category || 'OTHER').toUpperCase()}</span>
                    <span>{t('reference_libraries_official')}</span>
                    {library.is_favorite && <span>{t('reference_libraries_in_favorites')}</span>}
                  </div>
                  <h2>{library.name}</h2>
                  <p>{library.description || library.space_name}</p>
                </div>
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={pendingId === library.id || requiresReplacement}
                  aria-label={t(actionKey)}
                  title={requiresReplacement ? t('reference_libraries_replace_hint') : undefined}
                  onClick={() => void toggleFavorite(library)}
                >
                  {library.is_favorite ? <StarFilled /> : <StarOutlined />}
                  {t(actionKey)}
                </button>
              </Surface>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
