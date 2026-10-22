import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../stores/authStore';
import { membersService } from '../../services/apiServices';
import { ApiError } from '../../services/apiClient';
import { useUIStore } from '../../stores/uiStore';
import { ConfitLogo } from '../../components/common/ConfitLogo';
import { SkipLink, SKIP_MAIN_ID } from '../../components/common/SkipLink';

/**
 * BrandTeamAcceptView — public acceptance surface for brand invitations
 * (GET /b2b/team/accept?token=…, the exact link delivered by email).
 *
 * The route is deliberately OUTSIDE the partner boundary: an invited account
 * is still a 'consumer' until acceptance, and membership can only be granted
 * by the authenticated POST /partner/members/invitations/accept call — the
 * token is an invitation capability, never a session. The view renders the
 * server's honest outcome: valid-and-accepted, already-a-member, or one
 * uniform invalid/expired/revoked error (the API never distinguishes those).
 */

type State =
  | { kind: 'awaiting_login' }
  | { kind: 'working' }
  | { kind: 'accepted'; brandId: number }
  | { kind: 'already'; brandId: number }
  | { kind: 'invalid' }
  | { kind: 'multi_brand' };

const card = 'bg-white border border-slate-200/80 rounded-3xl shadow-2xl p-8 space-y-5';
const btnPrimary =
  'inline-flex items-center justify-center gap-2 min-h-11 px-5 rounded-xl bg-brand-charcoal text-white '
  + 'text-xs font-bold tracking-wider uppercase shadow-xs transition-all hover:bg-black '
  + 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2';

const BrandTeamAcceptView: React.FC = () => {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const { isAuthenticated, hasAttemptedBootstrap, loadBrandMemberships } = useAuthStore();
  const { openAuthModal } = useUIStore();
  const [state, setState] = useState<State>({ kind: 'working' });
  const attempted = useRef<string | null>(null);

  const acceptOnce = useCallback(async (value: string) => {
    setState({ kind: 'working' });
    try {
      const res = await membersService.accept(value);
      // Refresh tenant identity so RoleGuard admits the new member immediately.
      void loadBrandMemberships();
      setState(res?.already_member ? { kind: 'already', brandId: res.brand_id } : { kind: 'accepted', brandId: res.brand_id });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'MULTI_BRAND_NOT_SUPPORTED') {
        setState({ kind: 'multi_brand' });
      } else {
        // 401 from the endpoint means "sign in first" — show the gateway, not an error.
        setState(err instanceof ApiError && err.status === 401
          ? { kind: 'awaiting_login' }
          : { kind: 'invalid' });
      }
    }
  }, [loadBrandMemberships]);

  useEffect(() => {
    if (!hasAttemptedBootstrap) return;
    if (!token) { setState({ kind: 'invalid' }); return; }
    if (!isAuthenticated) { setState({ kind: 'awaiting_login' }); return; }
    if (attempted.current === token) return; // one shot per token (StrictMode-safe)
    attempted.current = token;
    void acceptOnce(token);
  }, [hasAttemptedBootstrap, isAuthenticated, token, acceptOnce]);

  const inner = (() => {
    if (!token) {
      return (
        <div className={card} role="alert">
          <h1 className="font-serif text-2xl font-bold text-brand-charcoal">{t('brand_team.accept.missing_title')}</h1>
          <p className="text-sm text-brand-muted font-light">{t('brand_team.accept.missing_body')}</p>
        </div>
      );
    }
    switch (state.kind) {
      case 'working':
        return (
          <div className={card}>
            <div role="status" aria-live="polite" className="flex items-center gap-3 text-brand-muted">
              <span className="w-8 h-8 rounded-full border-2 border-slate-200 border-t-brand-charcoal motion-safe:animate-spin" aria-hidden="true" />
              <span className="text-[11px] tracking-widest uppercase font-semibold">{t('guard.verifying_session')}</span>
            </div>
            <h1 className="font-serif text-2xl font-bold text-brand-charcoal">{t('brand_team.accept.working_title')}</h1>
          </div>
        );
      case 'awaiting_login': {
        return (
          <div className={card}>
            <h1 className="font-serif text-2xl font-bold text-brand-charcoal">{t('brand_team.accept.signin_title')}</h1>
            <p className="text-sm text-brand-muted font-light">{t('brand_team.accept.signin_body')}</p>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" data-motion="send" className={btnPrimary}
                onClick={() => openAuthModal('login', { returnTo: window.location.pathname + window.location.search })}>
                {t('brand_team.accept.signin_button')}
              </button>
              <span className="text-[11px] text-brand-muted">{t('brand_team.accept.signin_hint')}</span>
            </div>
          </div>
        );
      }
      case 'accepted':
      case 'already':
        return (
          <div className={card} role="status">
            <h1 className="font-serif text-2xl font-bold text-brand-charcoal">
              {state.kind === 'accepted' ? t('brand_team.accept.ok_title') : t('brand_team.accept.already_title')}
            </h1>
            <p className="text-sm text-brand-muted font-light">{t('brand_team.accept.ok_body')}</p>
            <Link to="/b2b" data-motion="send" className={btnPrimary}>{t('brand_team.accept.enter_portal')}</Link>
          </div>
        );
      case 'multi_brand':
        return (
          <div className={card} role="alert">
            <h1 className="font-serif text-2xl font-bold text-brand-charcoal">{t('brand_team.accept.multi_title')}</h1>
            <p className="text-sm text-brand-muted font-light">{t('brand_team.accept.multi_body')}</p>
            <Link to="/b2b" className="text-sm text-brand-charcoal underline">{t('brand_team.accept.enter_portal')}</Link>
          </div>
        );
      case 'invalid':
      default:
        return (
          <div className={card} role="alert">
            <h1 className="font-serif text-2xl font-bold text-brand-charcoal">{t('brand_team.accept.invalid_title')}</h1>
            <p className="text-sm text-brand-muted font-light">{t('brand_team.accept.invalid_body')}</p>
            <Link to="/" className="text-sm text-brand-charcoal underline">{t('brand_team.accept.back_home')}</Link>
          </div>
        );
    }
  })();

  return (
    <>
      <SkipLink />
      <main id={SKIP_MAIN_ID} tabIndex={-1} className="min-h-screen bg-brand-wash px-4 py-16 flex flex-col items-center outline-none">
        <div className="flex items-center gap-3 mb-8">
          <ConfitLogo variant="compact" size="sm" />
          <span className="text-[10px] font-bold tracking-widest text-brand-muted uppercase">{t('brand_team.eyebrow')}</span>
        </div>
        <div className="w-full max-w-lg">{inner}</div>
      </main>
    </>
  );
};

export { BrandTeamAcceptView };
export default BrandTeamAcceptView;
