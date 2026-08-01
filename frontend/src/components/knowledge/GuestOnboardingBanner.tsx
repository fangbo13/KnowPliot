import { ApartmentOutlined, BookOutlined, FieldTimeOutlined, RocketOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { spacesApi } from '../../api/spaces';
import { notify } from '../../utils/notifications';

export default function GuestOnboardingBanner({
  spaceId,
  onCompleted,
}: {
  spaceId: string;
  onCompleted: () => void | Promise<void>;
}) {
  const { t } = useTranslation('common');
  const [pending, setPending] = useState(false);

  const complete = async () => {
    setPending(true);
    try {
      await spacesApi.completeOnboarding(spaceId);
      await onCompleted();
      void notify('success', t('guest_onboarding_completed'));
    } catch {
      void notify('error', t('guest_onboarding_error'));
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="kp-guest-onboarding" aria-labelledby="guest-onboarding-title">
      <div>
        <div className="kp-page-header__eyebrow">{t('guest_onboarding_eyebrow')}</div>
        <h2 id="guest-onboarding-title">{t('guest_onboarding_title')}</h2>
        <p>{t('guest_onboarding_description')}</p>
        <div className="kp-guest-onboarding__features">
          <span><BookOutlined /> {t('kb_tab_documents')}</span>
          <span><ApartmentOutlined /> {t('kb_tab_graph')}</span>
          <span><FieldTimeOutlined /> {t('kb_tab_timeline')}</span>
        </div>
      </div>
      <button type="button" className="primary-btn" disabled={pending} onClick={() => void complete()}>
        <RocketOutlined /> {t('guest_onboarding_start')}
      </button>
    </section>
  );
}
