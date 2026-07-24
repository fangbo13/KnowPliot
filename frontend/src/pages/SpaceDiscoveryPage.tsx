import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Input, List, Tag } from 'antd';
import { KeyOutlined } from '@ant-design/icons';

import { spacesApi, type DiscoverableSpaceCard } from '../api/spaces';
import { getApiErrorCode, getRateLimitDetails, isAbortError } from '../api/client';
import { EmptyState, PageHeader, Surface } from '../design/primitives';

export default function SpaceDiscoveryPage() {
  const { t } = useTranslation('common');
  const [spaces, setSpaces] = useState<DiscoverableSpaceCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: 'load' | 'rate_limited'; retryAfterSeconds: number | null } | null>(null);
  const [joinCode, setJoinCode] = useState('');
  const [joinSubmitting, setJoinSubmitting] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joinSuccess, setJoinSuccess] = useState<string | null>(null);
  const [joinStatuses, setJoinStatuses] = useState<Record<string, 'joining' | 'joined' | 'failed' | 'rate_limited'>>({});
  const requestSequence = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const joinController = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      setSpaces(await spacesApi.discoverable(controller.signal));
    } catch (err: unknown) {
      if (isAbortError(err) || controller.signal.aborted || sequence !== requestSequence.current) return;
      const rateLimit = getRateLimitDetails(err);
      setError(rateLimit
        ? { code: 'rate_limited', retryAfterSeconds: rateLimit.retryAfterSeconds }
        : { code: 'load', retryAfterSeconds: null });
    } finally {
      if (sequence === requestSequence.current && !controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      requestSequence.current += 1;
      controllerRef.current?.abort();
      joinController.current?.abort();
    };
  }, [load]);

  const handleJoinByCode = async () => {
    const code = joinCode.trim();
    if (!code || joinSubmitting) return;
    joinController.current?.abort();
    const controller = new AbortController();
    joinController.current = controller;
    setJoinSubmitting(true);
    setJoinError(null);
    setJoinSuccess(null);
    try {
      const result = await spacesApi.joinByCode(code, controller.signal);
      if (controller.signal.aborted) return;
      setJoinSuccess(t('join_success', { defaultValue: `成功加入「${result.space_name}」` }));
      setJoinCode('');
      void load();
    } catch (err: unknown) {
      if (isAbortError(err) || controller.signal.aborted) return;
      const rateLimit = getRateLimitDetails(err);
      const code = getApiErrorCode(err);
      if (rateLimit) {
        setJoinError(rateLimit.retryAfterSeconds == null
          ? t('rate_limited', { defaultValue: '请求过于频繁，请稍后再试。' })
          : t('retry_after_seconds', { seconds: rateLimit.retryAfterSeconds, defaultValue: `请在 ${rateLimit.retryAfterSeconds} 秒后重试` }));
      } else if (code === 'already_member') {
        setJoinError(t('already_member', { defaultValue: '你已经是该空间的成员。' }));
      } else {
        setJoinError(t('join_code_invalid', { defaultValue: '加入码无效，请检查后重试。' }));
      }
    } finally {
      if (!controller.signal.aborted) setJoinSubmitting(false);
      if (joinController.current === controller) joinController.current = null;
    }
  };

  const handleGlobalJoin = async (space: DiscoverableSpaceCard) => {
    setJoinStatuses((current) => ({ ...current, [space.id]: 'joining' }));
    try {
      await spacesApi.globalJoin(space.id);
      setJoinStatuses((current) => ({ ...current, [space.id]: 'joined' }));
      void load();
    } catch (err: unknown) {
      if (isAbortError(err)) return;
      const rateLimit = getRateLimitDetails(err);
      setJoinStatuses((current) => ({
        ...current,
        [space.id]: rateLimit ? 'rate_limited' : 'failed',
      }));
    }
  };

  return (
    <div className="page section-enter">
      <PageHeader title={t('space_discovery', { defaultValue: '空间发现' })} description={t('space_discovery_description', { defaultValue: '浏览可加入的工作空间' })} />
      <Surface>
        {/* 凭码加入 */}
        <div style={{ marginBottom: 24, display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <Input
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            placeholder={t('join_code_placeholder', { defaultValue: '输入加入码，如 KP-AB12CD' })}
            prefix={<KeyOutlined style={{ color: 'var(--color-text-secondary)' }} />}
            style={{ flex: '1 1 320px' }}
            onPressEnter={() => void handleJoinByCode()}
            disabled={joinSubmitting}
          />
          <Button
            type="primary"
            loading={joinSubmitting}
            disabled={!joinCode.trim()}
            onClick={() => void handleJoinByCode()}
          >
            {t('join_by_code', { defaultValue: '凭码加入' })}
          </Button>
          {joinSuccess && <Alert type="success" showIcon message={joinSuccess} style={{ width: '100%' }} />}
          {joinError && <Alert type="error" showIcon message={joinError} style={{ width: '100%' }} />}
        </div>

        {/* 全局可见空间列表 */}
        {loading ? (
          <p role="status">{t('loading', { defaultValue: '加载中…' })}</p>
        ) : error ? (
          <Alert
            type="error"
            showIcon
            message={error.code === 'rate_limited'
              ? `${t('rate_limited', { defaultValue: '请求过于频繁' })}${error.retryAfterSeconds == null ? '' : ` — ${t('retry_after_seconds', { seconds: error.retryAfterSeconds, defaultValue: `${error.retryAfterSeconds} 秒后重试` })}`}`
              : t('load_error', { defaultValue: '加载失败' })}
            action={<Button onClick={() => void load()}>{t('error_retry', { defaultValue: '重试' })}</Button>}
          />
        ) : spaces.length === 0 ? (
          <EmptyState icon="K" title={t('space_discovery_empty', { defaultValue: '没有可发现的空间' })} />
        ) : (
          <List
            dataSource={spaces}
            renderItem={(space) => (
              <List.Item>
                <div style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <div style={{ flex: '1 1 300px', minWidth: 200 }}>
                    <strong>{space.name}</strong>{' '}
                    <Tag bordered={false} color="blue">{t(`join_policy_${space.join_policy}`, { defaultValue: space.join_policy === 'global' ? '全局可见' : '邀请码' })}</Tag>
                    <div style={{ color: 'var(--color-text-secondary)', marginTop: 4 }}>{space.description}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {space.is_member || joinStatuses[space.id] === 'joined' ? (
                      <Tag color="green">{t('joined', { defaultValue: '已加入' })}</Tag>
                    ) : (
                      <Button
                        type="primary"
                        loading={joinStatuses[space.id] === 'joining'}
                        disabled={joinStatuses[space.id] === 'joined' || space.is_member}
                        onClick={() => void handleGlobalJoin(space)}
                      >
                        {t('join', { defaultValue: '加入' })}
                      </Button>
                    )}
                  </div>
                  {joinStatuses[space.id] === 'failed' && (
                    <Alert type="error" showIcon message={t('join_failed', { defaultValue: '加入失败，请重试。' })} style={{ width: '100%' }} />
                  )}
                  {joinStatuses[space.id] === 'rate_limited' && (
                    <Alert type="warning" showIcon message={t('rate_limited', { defaultValue: '请求过于频繁，请稍后重试。' })} style={{ width: '100%' }} />
                  )}
                </div>
              </List.Item>
            )}
          />
        )}
      </Surface>
    </div>
  );
}
