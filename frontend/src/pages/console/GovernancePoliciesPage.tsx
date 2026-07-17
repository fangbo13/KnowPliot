import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Descriptions, InputNumber, List, Select } from 'antd';

import {
  adminApi,
  type GovernancePolicyEnvelope,
  type ModelProfile,
} from '../../api/admin';
import { spacesApi, type KnowledgeSpace } from '../../api/spaces';
import { EmptyState, PageHeader, Surface } from '../../design/primitives';

export default function GovernancePoliciesPage() {
  const { t } = useTranslation('common');
  const [spaces, setSpaces] = useState<KnowledgeSpace[]>([]);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [spaceId, setSpaceId] = useState('');
  const [policy, setPolicy] = useState<GovernancePolicyEnvelope | null>(null);
  const [fastProfileId, setFastProfileId] = useState<string>();
  const [deepProfileId, setDeepProfileId] = useState<string>();
  const [thinkingBudget, setThinkingBudget] = useState<number>();
  const [retrievalTopK, setRetrievalTopK] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([spacesApi.list(), adminApi.modelProfiles()])
      .then(([rows, modelProfiles]) => {
        setSpaces(rows);
        setProfiles(modelProfiles.filter((profile) => profile.enabled));
        setSpaceId((current) => current || rows[0]?.id || '');
      })
      .catch(() => setError(true));
  }, []);

  const loadPolicy = async (selectedSpaceId: string) => {
    setLoading(true);
    setError(false);
    try {
      setPolicy(await adminApi.governancePolicies(selectedSpaceId));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!spaceId) {
      setLoading(false);
      return;
    }
    void loadPolicy(spaceId);
  }, [spaceId]);

  const saveRevision = async () => {
    if (!spaceId) return;
    const values: Record<string, unknown> = {};
    if (fastProfileId) values.fast_model_profile_id = fastProfileId;
    if (deepProfileId) values.deep_model_profile_id = deepProfileId;
    if (thinkingBudget) values.deep_thinking_budget = thinkingBudget;
    if (retrievalTopK) values.retrieval_top_k = retrievalTopK;
    if (Object.keys(values).length === 0) return;

    setSaving(true);
    setError(false);
    try {
      await adminApi.createGovernancePolicy({ space: spaceId, values });
      setFastProfileId(undefined);
      setDeepProfileId(undefined);
      setThinkingBudget(undefined);
      setRetrievalTopK(undefined);
      await loadPolicy(spaceId);
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  const profileOptions = profiles.map((profile) => ({
    value: profile.id,
    label: `${profile.name} · ${profile.model_id}`,
  }));
  const hasRevisionValues = Boolean(
    fastProfileId || deepProfileId || thinkingBudget || retrievalTopK,
  );

  return (
    <div className="page section-enter">
      <PageHeader
        title={t('governance_policies')}
        description={t('governance_policies_description')}
      />
      <Surface style={{ display: 'grid', gap: 20 }}>
        <Select
          value={spaceId || undefined}
          onChange={setSpaceId}
          placeholder={t('select_workspace')}
          options={spaces.map((space) => ({ value: space.id, label: space.name }))}
          style={{ maxWidth: 360 }}
        />
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 12,
          }}
        >
          <Select
            allowClear
            value={fastProfileId}
            onChange={setFastProfileId}
            placeholder={t('fast_model_profile')}
            options={profileOptions}
          />
          <Select
            allowClear
            value={deepProfileId}
            onChange={setDeepProfileId}
            placeholder={t('deep_model_profile')}
            options={profileOptions}
          />
          <InputNumber
            min={1}
            max={32768}
            value={thinkingBudget}
            onChange={(value) => setThinkingBudget(value ?? undefined)}
            placeholder={t('deep_thinking_budget')}
            style={{ width: '100%' }}
          />
          <InputNumber
            min={1}
            max={20}
            value={retrievalTopK}
            onChange={(value) => setRetrievalTopK(value ?? undefined)}
            placeholder={t('retrieval_top_k')}
            style={{ width: '100%' }}
          />
          <Button
            type="primary"
            loading={saving}
            disabled={!spaceId || !hasRevisionValues}
            onClick={saveRevision}
          >
            {t('create_policy_revision')}
          </Button>
        </div>
        {error ? (
          <Alert type="error" showIcon message={t('load_error')} />
        ) : loading ? (
          <p role="status">{t('loading')}</p>
        ) : !policy ? (
          <EmptyState icon="K" title={t('governance_policy_empty')} />
        ) : (
          <>
            <Descriptions bordered column={1} title={t('effective_policy')}>
              {Object.entries(policy.effective).map(([key, value]) => (
                <Descriptions.Item key={key} label={key}>
                  {String(value)}
                </Descriptions.Item>
              ))}
            </Descriptions>
            <List
              header={t('policy_revisions')}
              dataSource={policy.revisions}
              locale={{ emptyText: t('governance_policy_empty') }}
              renderItem={(revision) => (
                <List.Item>
                  #{revision.revision} · {new Date(revision.created_at).toLocaleString()}
                </List.Item>
              )}
            />
          </>
        )}
      </Surface>
    </div>
  );
}
