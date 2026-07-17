import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Checkbox, Input, List } from 'antd';

import { adminApi, type ModelProfile } from '../../api/admin';
import { EmptyState, PageHeader, Surface } from '../../design/primitives';

export default function ModelProfilesPage() {
  const { t } = useTranslation('common');
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [name, setName] = useState('');
  const [provider, setProvider] = useState('openai-compatible');
  const [modelId, setModelId] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = async () => {
    setLoading(true); setError(false);
    try { setProfiles(await adminApi.modelProfiles()); }
    catch { setError(true); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const create = async () => {
    try {
      await adminApi.createModelProfile({ name, provider, model_id: modelId, enabled });
      setName(''); setModelId(''); await load();
    } catch { setError(true); }
  };

  return (
    <div className="page section-enter">
      <PageHeader title={t('model_profiles')} description={t('model_profiles_description')} />
      <Surface style={{ display: 'grid', gap: 20 }}>
        {error && <Alert type="error" showIcon message={t('load_error')} action={<Button onClick={load}>{t('error_retry')}</Button>} />}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder={t('profile_name')} />
          <Input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder={t('model_provider')} />
          <Input value={modelId} onChange={(event) => setModelId(event.target.value)} placeholder={t('model_id')} />
          <Checkbox checked={enabled} onChange={(event) => setEnabled(event.target.checked)}>{t('enabled')}</Checkbox>
          <Button type="primary" disabled={!name || !provider || !modelId} onClick={create}>{t('create')}</Button>
        </div>
        {loading ? <p role="status">{t('loading')}</p> : profiles.length === 0 ? <EmptyState icon="K" title={t('model_profiles_empty')} /> : (
          <List dataSource={profiles} renderItem={(profile) => (
            <List.Item extra={profile.enabled ? t('enabled') : t('disabled')}>
              <List.Item.Meta title={profile.name} description={`${profile.provider} · ${profile.model_id}`} />
            </List.Item>
          )} />
        )}
      </Surface>
    </div>
  );
}
