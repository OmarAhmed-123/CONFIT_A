import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useModalFocus } from '../hooks/useModalFocus';
import { PHOTO_RETENTION_HOURS } from '../views/legal/LegalViews';
import { NOTICE_VERSION, CONSENT_PURPOSE_COPY, type ConsentPurpose } from './consentStore';
import { Link } from 'react-router-dom';

export interface ConsentDialogProps {
  /** Null when closed. The dialog never renders for a purpose with no copy. */
  purpose: ConsentPurpose | null;
  onAccept: (options: { rememberForSession: boolean }) => void;
  onDecline: () => void;
}

/**
 * The consent notice, as a real dialog — the ONE component every photo
 * processing flow routes through.
 *
 * THE COPY ALREADY EXISTED AND NOTHING USED IT (audit 2026-09-21)
 *   `src/i18n/{en,ar}.json` already carried a complete, careful, fully
 *   translated `consent.*` notice — "Nothing leaves your device until you agree
 *   below", retention, no face recognition, how to withdraw. A grep for
 *   `t('consent.` across `src/` returned ZERO call sites. The notice was dead
 *   data: the app said the right things in a file no user could ever reach,
 *   while the try-on flow uploaded photos after asserting consent for them.
 *
 *   So this component is not new policy. It is the missing `t()` call — and
 *   that is the whole finding: a privacy notice that is not rendered is not a
 *   privacy notice.
 *
 * GDPR Article 7 requirements and where they live in this markup:
 *   · **Explicit** — the action is a button press. Nothing is pre-ticked and
 *     nothing is inferred; there is no "by continuing you agree", because
 *     continuing is not a signal of consent.
 *   · **Specific per purpose** — the purpose line and the retention line come
 *     from `CONSENT_PURPOSE_COPY[purpose]`, and the retentions genuinely
 *     differ: an anonymous try-on job expires in hours, while a wardrobe photo
 *     is kept until the user deletes it. One shared "photos are temporary"
 *     sentence would be false for the wardrobe.
 *   · **Informed** — what, why, where, how long, plus the two statements that
 *     stop the copy over-claiming: no training on the photo without separate
 *     opt-in, and no face recognition.
 *   · **Refusable without penalty** — Decline is a first-class button of equal
 *     weight, with `required_hint` naming the no-photo alternative, so declining
 *     costs the user a feature and not the service.
 *   · **Withdrawable** — `rights_link`, plus `/privacy`, where the record and
 *     the withdrawal control live.
 *   · **Demonstrable** — the notice version is visible to the user (v2.0): a
 *     notice a user cannot identify is not one they can prove they read.
 */
export const ConsentDialog: React.FC<ConsentDialogProps> = ({ purpose, onAccept, onDecline }) => {
  const { t } = useTranslation();
  const [rememberForSession, setRememberForSession] = useState(false);
  const isOpen = purpose !== null;
  const containerRef = useModalFocus<HTMLDivElement>(onDecline, isOpen);

  if (!purpose) return null;

  const copy = CONSENT_PURPOSE_COPY[purpose];
  const retention = { hours: PHOTO_RETENTION_HOURS };

  return (
    <div
      className="fixed inset-0 z-[120] flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="consent-dialog-title"
      aria-describedby="consent-dialog-body"
      data-testid="consent-dialog"
    >
      <div
        ref={containerRef}
        dir="auto"
        className="w-full max-w-lg rounded-t-2xl bg-white p-6 shadow-xl sm:rounded-2xl"
      >
        <h2 id="consent-dialog-title" className="text-lg font-semibold text-neutral-900">
          {t('consent.title')}
        </h2>

        <div id="consent-dialog-body" className="mt-3 space-y-3 text-sm text-neutral-700">
          <p>{t('consent.lead')}</p>

          <ul className="list-disc space-y-1.5 ps-5 text-xs">
            <li>{t(copy.purposeKey)}</li>
            <li>{t(copy.retentionKey, retention)}</li>
            <li>{t('consent.point_what')}</li>
            <li>{t('consent.point_why')}</li>
            <li>{t('consent.point_where')}</li>
            <li>{t('consent.point_training')}</li>
            <li>{t('consent.point_no_biometric_id')}</li>
          </ul>

          <label className="flex items-start gap-2 text-xs font-normal">
            <input
              type="checkbox"
              className="confit-tap-target mt-0.5 h-4 w-4 shrink-0 rounded border-neutral-400"
              checked={rememberForSession}
              onChange={(e) => setRememberForSession(e.target.checked)}
            />
            <span>{t('consent.remember')}</span>
          </label>

          <p className="text-xs text-neutral-500">
            {t('consent.required_hint')}{' '}
            <Link to="/privacy" className="underline hover:text-neutral-700">
              {t('consent.rights_link')}
            </Link>
          </p>
          <p className="text-[10px] uppercase tracking-wide text-neutral-400">
            {t('consent.notice_version', { version: NOTICE_VERSION })}
          </p>
        </div>

        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onDecline}
            className="confit-tap-target rounded-lg border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50"
            data-testid="consent-decline"
          >
            {t('consent.decline')}
          </button>
          <button
            type="button"
            onClick={() => onAccept({ rememberForSession })}
            className="confit-tap-target rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
            data-testid="consent-accept"
          >
            {t('consent.accept')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConsentDialog;
