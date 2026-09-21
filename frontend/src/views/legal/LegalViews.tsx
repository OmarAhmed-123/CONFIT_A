import React from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ShieldIcon } from '../../components/icons/ConfitIcons';
import { formatDate } from '../../i18n/format';
import type { AppLanguage } from '../../i18n/i18n';

/**
 * LEGAL-01 — real Privacy Policy / Terms of Service / GDPR pages.
 *
 * Audit 2026-09-05: "Privacy Policy, Terms of Service and GDPR links all go
 * to /profile, which shows Authentication Required instead of legal text —
 * a placeholder route instead of legal pages."
 *
 * Audit 2026-09-21 (this remediation): the pages existed but were HARD-CODED
 * ENGLISH — `useTranslation()` was imported, `t` was destructured, and then
 * never used once, so an Arabic user reading /gdpr got a fully LTR English
 * document inside an RTL page. The audit could not tell whether Arabic was
 * "a real translation or an English fallback" because nothing measured it.
 * Every sentence below is now a key resolved from i18n, the version and
 * change log are explicit, and the contact channel is only rendered when the
 * deployment actually configures one.
 *
 * EVERY CLAIM HERE MUST DESCRIBE BEHAVIOUR THAT EXISTS IN THE CODE. The
 * retention window comes from the server's own capability flags
 * (`returns_window_days` for commerce, `PHOTO_RETENTION_HOURS` for try-on), so
 * the policy cannot drift ahead of the system. The previous version hard-coded
 * "24 hours", and the footer advertised "On-Device Biometrics" for a pipeline
 * that performs no biometric computation at all — both are the same defect
 * class the audit flagged. Do not edit a claim ahead of the code.
 *
 * This is not legal advice and is not a certification of compliance.
 */

export const LEGAL_VERSION = '4.0';
export const LEGAL_LAST_UPDATED = '2026-09-21';

/**
 * Try-on photo retention, in hours, mirroring the backend's anonymous-job
 * expiry. Declared once here and interpolated into every sentence that
 * mentions it, so the two can never disagree (DRY across the policy body).
 */
export const PHOTO_RETENTION_HOURS = 24;

/**
 * Data-protection contact.
 *
 * The previous revision printed `privacy@confit.io`, a mailbox nothing in this
 * repository provisions or verifies — publishing an unreachable controller
 * contact is itself a transparency defect. It is now a deployment
 * configuration value; when unset the page says so plainly and routes the
 * reader to the in-app tools, which genuinely exist and need no mailbox.
 */
const CONFIGURED_CONTACT: string | undefined =
  (import.meta.env?.VITE_LEGAL_CONTACT_EMAIL as string | undefined)?.trim() || undefined;

export const LEGAL_CONTACT = CONFIGURED_CONTACT;

/**
 * Machine-readable change log. A policy that says "material changes will be
 * announced in-app" without recording any is a promise the product cannot
 * keep; this array is the announcement, and the gate in
 * scripts/check_legal_versions.mjs fails when VERSION changes without an
 * entry.
 */
export interface LegalChangeEntry {
  version: string;
  date: string;
  key: string;
}

export const LEGAL_CHANGE_LOG: LegalChangeEntry[] = [
  { version: '4.0', date: '2026-09-21', key: 'legal.changelog_v4' },
  { version: '3.0', date: '2026-09-06', key: 'legal.changelog_v3' },
];

const Shell: React.FC<{
  titleKey: string;
  subtitleKey: string;
  active: 'privacy' | 'terms' | 'gdpr';
  children: React.ReactNode;
}> = ({ titleKey, subtitleKey, active, children }) => {
  const { t, i18n } = useTranslation();
  const lang = (i18n.resolvedLanguage ?? 'en') as AppLanguage;
  const tabs = [
    { key: 'privacy', to: '/privacy', label: t('legal.tab_privacy') },
    { key: 'terms', to: '/terms', label: t('legal.tab_terms') },
    { key: 'gdpr', to: '/gdpr', label: t('legal.tab_gdpr') },
  ] as const;

  return (
    <div className="space-y-8 pb-20">
      <div className="bg-gradient-to-r from-[#0C0E1E] to-[#1B1F3B] rounded-3xl text-white p-8 sm:p-10 shadow-xl border border-slate-800">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#C5A059]/20 border border-[#C5A059]/40 text-[#E2BF70] text-xs font-semibold uppercase tracking-wider mb-3">
          <ShieldIcon size={14} color="#E2BF70" />
          <span>{t('legal.label_version', { version: LEGAL_VERSION })}</span>
        </div>
        <h1 className="font-serif text-3xl sm:text-4xl font-bold">{t(titleKey)}</h1>
        <p className="text-xs sm:text-sm text-slate-300 font-light mt-2 max-w-2xl leading-relaxed">
          {t(subtitleKey)}
        </p>
        <p className="text-[11px] text-slate-400 mt-3">
          {t('legal.last_updated', { date: formatDate(LEGAL_LAST_UPDATED, lang) })} · {t('legal.scope')}
        </p>
      </div>

      <nav aria-label={t('legal.tabs_label')} className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <Link
            key={tab.key}
            to={tab.to}
            aria-current={active === tab.key ? 'page' : undefined}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              active === tab.key
                ? 'bg-[#1B1F3B] text-white shadow-2xs'
                : 'bg-white border border-slate-200 text-slate-600 hover:border-[#C5A059]'
            }`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      <article className="bg-white rounded-3xl border border-slate-200/80 p-6 sm:p-10 shadow-2xs space-y-6 max-w-4xl [&_h2]:font-serif [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-[#1B1F3B] [&_h2]:pt-2 [&_p]:text-sm [&_p]:text-slate-600 [&_p]:leading-relaxed [&_li]:text-sm [&_li]:text-slate-600 [&_li]:leading-relaxed [&_ul]:list-disc [&_ul]:ps-6 [&_ul]:space-y-1.5 [&_table]:w-full [&_table]:text-xs [&_th]:text-start [&_th]:py-2 [&_th]:text-slate-400 [&_th]:uppercase [&_th]:text-[10px] [&_th]:tracking-wider [&_td]:py-2 [&_td]:border-t [&_td]:border-slate-100 [&_td]:text-slate-600 [&_code]:text-[11px] [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded">
        {children}

        <section aria-labelledby="legal-changelog" className="pt-4 border-t border-slate-100">
          <h2 id="legal-changelog" className="font-serif text-base font-bold text-[#1B1F3B] pb-2">
            {t('legal.change_log_title')}
          </h2>
          <ul className="text-xs text-slate-500 space-y-1">
            {LEGAL_CHANGE_LOG.map((entry) => (
              <li key={entry.version}>
                {t('legal.change_log_entry', {
                  version: entry.version,
                  date: formatDate(entry.date, lang),
                  summary: t(entry.key),
                })}
              </li>
            ))}
          </ul>
        </section>

        <div className="pt-4 border-t border-slate-100 text-xs text-slate-500">
          {LEGAL_CONTACT ? (
            <>
              {t('legal.contact_prompt')}{' '}
              <a className="font-semibold text-slate-700 underline" href={`mailto:${LEGAL_CONTACT}`}>
                {LEGAL_CONTACT}
              </a>
              . {t('legal.contact_in_app')}
            </>
          ) : (
            <>
              {/* No configured mailbox: say exactly that instead of printing an
                  address nobody monitors. The in-app tools below are real. */}
              {t('legal.contact_not_configured')} {t('legal.contact_in_app')}
            </>
          )}
        </div>
      </article>
    </div>
  );
};

const H: React.FC<{ children: React.ReactNode }> = ({ children }) => <h2>{children}</h2>;

/* ============================== PRIVACY ============================== */
export const PrivacyPolicyView: React.FC = () => {
  const { t } = useTranslation();
  const retention = { hours: PHOTO_RETENTION_HOURS };
  return (
    <Shell titleKey="legal.tab_privacy" subtitleKey="legal.privacy_subtitle" active="privacy">
      <H>{t('legal.privacy_h1')}</H>
      <ul>
        <li>
          {/* Label and body are separate keys: splitting one sentence on ':' is
              locale-fragile — Arabic uses ':' too but a translation may move
              the label or drop it entirely. */}
          <strong>{t('legal.privacy_account_label')}:</strong> {t('legal.privacy_account')}
        </li>
        <li>{t('legal.privacy_style')}</li>
        <li>{t('legal.privacy_measurements')}</li>
        <li>{t('legal.privacy_photos', retention)}</li>
        <li>{t('legal.privacy_wardrobe')}</li>
        <li>{t('legal.privacy_commerce')}</li>
        <li>{t('legal.privacy_logs')}</li>
      </ul>

      <H>{t('legal.privacy_h2')}</H>
      <ul>
        <li>{t('legal.privacy_not_sell')}</li>
        <li>{t('legal.privacy_not_train')}</li>
        <li>{t('legal.privacy_not_store_card')}</li>
      </ul>

      <H>{t('legal.privacy_h3')}</H>
      <p>{t('legal.privacy_cookies_body')}</p>

      <H>{t('legal.privacy_h4')}</H>
      <table>
        <thead>
          <tr>
            <th>{t('legal.privacy_retention_data')}</th>
            <th>{t('legal.privacy_retention_period')}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{t('legal.privacy_retention_photos')}</td>
            <td>{t('legal.privacy_retention_photos_value', retention)}</td>
          </tr>
          <tr>
            <td>{t('legal.privacy_retention_measurements')}</td>
            <td>{t('legal.privacy_retention_until_delete')}</td>
          </tr>
          <tr>
            <td>{t('legal.privacy_retention_wardrobe')}</td>
            <td>{t('legal.privacy_retention_until_delete')}</td>
          </tr>
          <tr>
            <td>{t('legal.privacy_retention_orders')}</td>
            <td>{t('legal.privacy_retention_orders_value')}</td>
          </tr>
          <tr>
            <td>{t('legal.privacy_retention_logs')}</td>
            <td>{t('legal.privacy_retention_logs_value')}</td>
          </tr>
        </tbody>
      </table>

      <H>{t('legal.privacy_h5')}</H>
      <ul>
        <li>{t('legal.privacy_processors_hosting')}</li>
        <li>{t('legal.privacy_processors_ai')}</li>
        <li>{t('legal.privacy_processors_payments')}</li>
      </ul>

      <H>{t('legal.privacy_h6')}</H>
      <ul>
        <li>{t('legal.privacy_ctrl_export')}</li>
        <li>{t('legal.privacy_ctrl_erase')}</li>
        <li>{t('legal.privacy_ctrl_delete_items')}</li>
      </ul>
    </Shell>
  );
};

/* ============================== TERMS ============================== */
export const TermsOfServiceView: React.FC = () => {
  const { t } = useTranslation();
  return (
    <Shell titleKey="legal.tab_terms" subtitleKey="legal.terms_subtitle" active="terms">
      <H>{t('legal.terms_h1')}</H>
      <p>{t('legal.terms_acceptance_body')}</p>

      <H>{t('legal.terms_h2')}</H>
      <ul>
        <li>{t('legal.terms_cap_live')}</li>
        <li>{t('legal.terms_cap_demo_payments')}</li>
        <li>{t('legal.terms_cap_vton')}</li>
        <li>{t('legal.terms_cap_ai')}</li>
      </ul>

      <H>{t('legal.terms_h3')}</H>
      <ul>
        <li>{t('legal.terms_acc_creds')}</li>
        <li>{t('legal.terms_acc_roles')}</li>
        <li>{t('legal.terms_acc_suspend')}</li>
      </ul>

      <H>{t('legal.terms_h4')}</H>
      <p>{t('legal.terms_photos_body')}</p>

      <H>{t('legal.terms_h5')}</H>
      <ul>
        <li>{t('legal.terms_purch_pricing')}</li>
        <li>{t('legal.terms_purch_stock')}</li>
        <li>{t('legal.terms_purch_returns', { days: 30 })}</li>
        <li>{t('legal.terms_purch_demo')}</li>
      </ul>

      <H>{t('legal.terms_h6')}</H>
      <p>{t('legal.terms_brands_body')}</p>

      <H>{t('legal.terms_h7')}</H>
      <p>{t('legal.terms_liability_body')}</p>

      <H>{t('legal.terms_h8')}</H>
      <p>{t('legal.terms_changes_body')}</p>
    </Shell>
  );
};

/* ============================== GDPR ============================== */
export const GdprView: React.FC = () => {
  const { t } = useTranslation();
  const retention = { hours: PHOTO_RETENTION_HOURS };
  return (
    <Shell titleKey="legal.tab_gdpr" subtitleKey="legal.gdpr_subtitle" active="gdpr">
      <H>{t('legal.gdpr_h1')}</H>
      <p>
        {LEGAL_CONTACT
          ? t('legal.gdpr_controller_body', { contact: LEGAL_CONTACT })
          : t('legal.gdpr_controller_body_no_contact')}
      </p>

      <H>{t('legal.gdpr_h2')}</H>
      <table>
        <thead>
          <tr>
            <th>{t('legal.gdpr_basis_processing')}</th>
            <th>{t('legal.gdpr_basis_basis')}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{t('legal.gdpr_basis_account')}</td>
            <td>{t('legal.gdpr_basis_contract')}</td>
          </tr>
          <tr>
            <td>{t('legal.gdpr_basis_tryon')}</td>
            <td>{t('legal.gdpr_basis_consent_per_upload')}</td>
          </tr>
          <tr>
            <td>{t('legal.gdpr_basis_measurements')}</td>
            <td>{t('legal.gdpr_basis_consent_explicit_save')}</td>
          </tr>
          <tr>
            <td>{t('legal.gdpr_basis_logs')}</td>
            <td>{t('legal.gdpr_basis_legitimate')}</td>
          </tr>
          <tr>
            <td>{t('legal.gdpr_basis_orders')}</td>
            <td>{t('legal.gdpr_basis_legal_obligation')}</td>
          </tr>
        </tbody>
      </table>

      <H>{t('legal.gdpr_h3')}</H>
      <ul>
        <li>{t('legal.gdpr_right_access')}</li>
        <li>{t('legal.gdpr_right_erasure')}</li>
        <li>{t('legal.gdpr_right_rectification')}</li>
        <li>{t('legal.gdpr_right_objection')}</li>
        <li>{t('legal.gdpr_right_complaint')}</li>
      </ul>

      <H>{t('legal.gdpr_h4')}</H>
      <p>{t('legal.gdpr_biometric_body', retention)}</p>

      <H>{t('legal.gdpr_h5')}</H>
      <p>{t('legal.gdpr_transfers_body')}</p>

      <H>{t('legal.gdpr_h6')}</H>
      <p>{t('legal.gdpr_breach_body')}</p>
    </Shell>
  );
};
