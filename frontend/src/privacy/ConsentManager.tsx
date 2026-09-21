import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  useConsentStore,
  CONSENT_PURPOSES,
  CONSENT_PURPOSE_COPY,
  type ConsentPurpose,
} from './consentStore';

/**
 * The withdrawal surface required by GDPR Article 7(3): withdrawing consent
 * must be as easy as giving it — and here it is easier, because it is one
 * button with no notice to re-read first.
 *
 * WHY IT IS ON THE PRIVACY PAGE
 *   The audit's finding was that consent, retention and rights were described
 *   in the privacy policy but exercised nowhere. A policy that says "you can
 *   withdraw consent" is a promise; a button on the same page that does it is
 *   the thing itself.
 *
 * WHAT IT SHOWS, AND WHAT IT DELIBERATELY DOES NOT
 *   It shows the user's own on-device record: purpose, when it was granted, and
 *   under which notice version. It does NOT claim to be a server-side ledger —
 *   `manage_scope_note` says out loud that the record lives in the browser, so
 *   the user is not misled into thinking we hold a signed consent artifact we
 *   do not hold. Over-claiming here would be exactly the failure mode this
 *   whole feature exists to remove.
 */
export const ConsentManager: React.FC = () => {
  const { t, i18n } = useTranslation();
  const records = useConsentStore((s) => s.records);
  const withdraw = useConsentStore((s) => s.withdraw);
  const withdrawAll = useConsentStore((s) => s.withdrawAll);

  const granted = CONSENT_PURPOSES.filter((p) => records[p]);
  const locale = i18n.language === 'ar' ? 'ar-EG' : 'en-GB';

  return (
    <section aria-labelledby="consent-manager-title" data-testid="consent-manager">
      <h2 id="consent-manager-title">{t('consent.manage_title')}</h2>
      <p className="text-xs text-slate-500">{t('consent.manage_lead')}</p>

      {granted.length === 0 ? (
        <p className="text-xs text-slate-500">{t('consent.manage_empty')}</p>
      ) : (
        <>
          <table>
            <thead>
              <tr>
                <th>{t('consent.manage_purpose')}</th>
                <th>{t('consent.manage_granted_at')}</th>
                <th>{t('consent.manage_notice')}</th>
                <th>{t('consent.manage_withdraw')}</th>
              </tr>
            </thead>
            <tbody>
              {granted.map((purpose: ConsentPurpose) => {
                const record = records[purpose]!;
                return (
                  <tr key={purpose}>
                    <td>{t(CONSENT_PURPOSE_COPY[purpose].purposeKey)}</td>
                    <td>
                      {new Date(record.grantedAt).toLocaleString(locale, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })}
                    </td>
                    <td>
                      {t('consent.notice_version', { version: record.noticeVersion })}
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() => withdraw(purpose)}
                        className="confit-tap-target rounded-lg border border-slate-300 px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        {t('consent.manage_withdraw')}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <button
            type="button"
            onClick={withdrawAll}
            className="confit-tap-target mt-2 rounded-lg border border-rose-300 px-3 py-1.5 text-[11px] font-semibold text-rose-700 hover:bg-rose-50"
          >
            {t('consent.manage_withdraw_all')}
          </button>
        </>
      )}

      <p className="text-[11px] text-slate-400">{t('consent.manage_scope_note')}</p>
    </section>
  );
};

export default ConsentManager;
