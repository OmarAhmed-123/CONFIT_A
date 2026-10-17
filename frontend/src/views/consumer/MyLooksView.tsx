import React, { useState } from 'react';
import { ActionButton } from '../../components/common/ActionButton';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { formatMoney } from '../../i18n/format';
import { useMyLooksViewModel } from '../../viewmodels/useMyLooksViewModel';
import { Outfit, ShareLink } from '../../models';
import { ShareActions } from '../../components/outfit/ShareActions';
import { SavedLooksIcon, SparkleIcon } from '../../components/icons/ConfitIcons';
import { TryOnButton } from '../../components/product/TryOnButton';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';

/**
 * My Looks — saved outfits plus honest, fully manageable share links.
 *
 * Audit findings this view closes:
 *  - /my-looks rendered the wardrobe, so saved outfits had no home in the UI.
 *  - "Export Look Card" implied a published public link. Here, a link only
 *    appears after the server confirms one, and its real expiry and view count
 *    are shown next to it.
 *  - There was no way to revoke a published link from the product at all.
 */

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString();
}

const SharePanel: React.FC<{
  look: Outfit;
  link?: ShareLink;
  busy: boolean;
  onShare: (rotate?: boolean) => Promise<unknown | null>;
  onRevoke: () => Promise<boolean>;
}> = ({ look, link, busy, onShare, onRevoke }) => {
  const { t } = useTranslation();
  const isLive = Boolean(link?.is_active && link?.share_url);
  const absolute = link?.share_url ? `${window.location.origin}${link.share_url}` : '';

  if (!isLive) {
    return (
      <div className="pt-3 border-t border-brand-hairline space-y-2">
        <p className="text-[11px] text-brand-muted font-light">
          {t('my_looks.private_note')}
        </p>
        {/* Spec 08: Publish is a critical action — unified kinetic CTA.
            Success only when the server returned a live link; a null
            result keeps the toast's reason and relabels actionable. */}
        {/* Motion intent “share” — minting a share link is a hand-off, not a save. */}
        <ActionButton
          intent="share"
          metricsId="looks.publish_link"
          onAction={async () => ((await onShare(false)) ? 'success' : 'error')}
          softDisabled={busy}
          labels={{
            idle: t('my_looks.create_link'),
            pending: t('my_looks.creating'),
            success: t('my_looks.published_confirm'),
            error: t('my_looks.publish_failed_retry'),
          }}
          data-testid="publish-look-cta"
          className="w-full py-2.5 rounded-xl bg-brand-charcoal hover:bg-[#1A1B1D] text-white text-xs font-bold transition-all focus-visible:outline-brand-charcoal"
        />
      </div>
    );
  }

  return (
    <div className="pt-3 border-t border-brand-hairline space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">
          {t('my_looks.link_active')}
        </span>
        <span className="text-[10px] text-brand-muted">
          {link?.view_count ?? 0} {t('my_looks.views')}
        </span>
      </div>

      {/* URLs are Latin codes — keep them LTR even inside the Arabic page. */}
      <input
        readOnly
        dir="ltr"
        value={absolute}
        aria-label={t('my_looks.public_link_for', { title: look.title })}
        className="w-full text-[11px] bg-brand-wash border border-brand-hairline rounded-lg px-2 py-1.5 text-brand-muted"
      />

      {/* Spec 06: shared copy/native-share affordance with honest, announced
          states. Mounted only here, where the server-minted link is LIVE. */}
      <ShareActions url={absolute} title={look.title} compact />

      <p className="text-[10px] text-brand-muted">
        {t('my_looks.expiry_note', { date: formatDate(link?.expires_at) })}
      </p>

      <div className="flex gap-2">
        <a
          href={link!.share_url!}
          target="_blank"
          rel="noreferrer"
          className="flex-1 text-center py-2 rounded-xl border border-brand-field text-[11px] font-semibold hover:bg-brand-wash"
        >
          {t('my_looks.open')}
        </a>
        {/* Motion intent “share” — rotating a link is the same outward hand-off. */}
        <ActionButton
          intent="share"
          metricsId="looks.rotate_link"
          onAction={async () => ((await onShare(true)) ? 'success' : 'error')}
          softDisabled={busy}
          labels={{
            idle: t('my_looks.new_link'),
            pending: t('my_looks.rotating'),
            success: t('my_looks.rotated_confirm'),
            error: t('my_looks.rotate_failed_retry'),
          }}
          data-testid="rotate-link-cta"
          className="flex-1 py-2 rounded-xl border border-brand-field text-[11px] font-semibold hover:bg-brand-wash"
        />
        {/* Motion intent “destructive” — revoking kills a live link — rose + amber, never celebratory. */}
        <ActionButton
          intent="destructive"
          metricsId="looks.revoke_link"
          onAction={async () => ((await onRevoke()) ? 'success' : 'error')}
          softDisabled={busy}
          labels={{
            idle: t('my_looks.revoke'),
            pending: t('my_looks.revoking'),
            success: t('my_looks.revoked_confirm'),
            error: t('my_looks.revoke_failed_retry'),
          }}
          data-testid="revoke-link-cta"
          className="flex-1 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-[11px] font-bold"
        />
      </div>
    </div>
  );
};

const LookCard: React.FC<{
  look: Outfit;
  link?: ShareLink;
  busy: boolean;
  onShare: (rotate?: boolean) => Promise<unknown | null>;
  onRevoke: () => Promise<boolean>;
  onDelete: () => void;
  onRename: (title: string) => void;
}> = ({ look, link, busy, onShare, onRevoke, onDelete, onRename }) => {
  const { t, i18n: lookI18n } = useTranslation();
  const lookCardLang = lookI18n.resolvedLanguage ?? 'en';
  const [title, setTitle] = useState(look.title);
  const complete = look.completeness_status === 'complete_look';

  return (
    <article className="bg-white rounded-3xl border border-brand-hairline p-5 shadow-2xs space-y-3">
      <div className="flex items-start justify-between gap-3">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => title !== look.title && onRename(title)}
          aria-label={t('my_looks.look_title_label')}
          className="font-serif text-lg font-bold text-brand-charcoal bg-transparent border-b border-transparent hover:border-brand-hairline focus:border-brand-charcoal focus:outline-none flex-1"
        />
        <span
          className={`shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full border ${
            complete
              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
              : 'bg-amber-50 text-amber-700 border-amber-200'
          }`}
        >
          {complete ? t('my_looks.complete_look') : t('my_looks.partial_look')}
        </span>
      </div>

      <div className="flex items-center gap-3 text-xs text-brand-muted">
        <span>{look.occasion}</span>
        <span>·</span>
        <span>{t('my_looks.pieces', { count: look.items.length })}</span>
        <span>·</span>
        <span className="font-bold text-brand-charcoal">
          <bdi dir="ltr">{formatMoney(Math.round(Number(look.total_price ?? 0) * 100), 'USD', lookCardLang)}</bdi>
        </span>
      </div>

      {/* Item strip, in the canonical layer order the server returns. */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {look.items.map((item) => (
          <div key={item.id} className="shrink-0 w-16">
            <div className="h-20 w-16 rounded-lg overflow-hidden bg-brand-wash">
              {item.image_url ? (
                <img
                  src={item.image_url}
                  alt={item.product_title}
                  className="w-full h-full object-cover"
                />
              ) : null}
            </div>
            <span className="text-[9px] text-brand-muted block truncate mt-0.5">
              {item.position}
            </span>
            {/* A saved look is the surface a shopper most wants to try on,
                and it had no control at all — the tile is not a ProductCard,
                so before TryOnButton existed adding one meant copying the
                whole gate. */}
            {item.product_id ? (
              <TryOnButton
                variant="icon"
                className="mt-1 w-full"
                product={{
                  id: item.product_id,
                  title: item.product_title,
                  thumbnail_url: item.image_url ?? undefined,
                }}
              />
            ) : null}
          </div>
        ))}
      </div>

      {/* Honest incompleteness — never dressed up as a finished look. */}
      {look.missing_slots && look.missing_slots.length > 0 ? (
        <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-2 py-1.5">
          {t('my_looks.missing')}: {look.missing_slots.join(', ')}.
        </p>
      ) : null}

      <div className="flex gap-2">
        <Link
          to={`/outfits/${look.id}`}
          className="flex-1 text-center py-2 rounded-xl border border-brand-field text-[11px] font-semibold hover:bg-brand-wash"
        >
          {t('my_looks.edit_in_composer')}
        </Link>
        <button data-motion="destructive"
          onClick={onDelete}
          disabled={busy}
          className="px-3 py-2 rounded-xl border border-brand-field text-[11px] font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-40"
        >
          {t('my_looks.delete')}
        </button>
      </div>

      <SharePanel
        look={look}
        link={link}
        busy={busy}
        onShare={onShare}
        onRevoke={onRevoke}
      />
    </article>
  );
};

export const MyLooksView: React.FC = () => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuthStore();
  const { openAuthModal } = useUIStore();
  const {
    looks,
    state,
    error,
    busyId,
    shareLinks,
    share,
    revoke,
    remove,
    rename,
    reload,
  } = useMyLooksViewModel({ enabled: isAuthenticated });

  /* A signed-out visitor has no looks to fetch: GET /outfits can only answer
     401, and the old generic error card offered a "Try again" that could never
     succeed. Name what is missing and offer the one action that resolves it. */
  if (!isAuthenticated) {
    return (
      <div className="mx-auto max-w-xl py-24 text-center">
        <div className="rounded-[32px] border border-brand-hairline bg-white p-8 shadow-2xs">
          <h1 className="font-serif text-2xl font-bold text-brand-charcoal">
            {t('my_looks.signin_title')}
          </h1>
          <p className="mt-2 text-sm font-light leading-relaxed text-brand-muted">
            {t('my_looks.signin_body')}
          </p>
          <button data-motion="progressive"
            type="button"
            onClick={() => openAuthModal('login')}
            className="mt-6 inline-flex min-h-11 items-center rounded-2xl bg-brand-charcoal px-5 py-2.5 text-xs font-bold text-white transition-colors hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white"
          >
            {t('auth.sign_in')}
          </button>
        </div>
      </div>
    );
  }

  if (state === 'loading') {
    return (
      <div className="py-24 text-center text-brand-muted" role="status">
        {t('my_looks.loading')}
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className="py-24 text-center space-y-3">
        <p className="text-brand-muted">{error ?? t('my_looks.something_wrong')}</p>
        <button data-motion="recovery"
          onClick={() => void reload()}
          className="px-4 py-2 rounded-xl border border-brand-field text-xs font-semibold hover:bg-brand-wash"
        >
          {t('my_looks.try_again')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-24">
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-brand-hairline pb-6">
        <div>
          <div className="flex items-center gap-2">
            <SavedLooksIcon size={24} color="#252729" />
            <h1 className="font-serif text-3xl font-bold text-brand-charcoal tracking-tight">
              {t('my_looks.title')}
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-brand-muted mt-1 font-light">
            {t('my_looks.subtitle')}
          </p>
        </div>
        <Link
          to="/builder"
          className="px-5 py-2 rounded-xl bg-brand-charcoal hover:bg-[#1A1B1D] text-white font-bold text-xs flex items-center gap-1.5 focus-visible:outline-brand-charcoal"
        >
          <SparkleIcon size={16} color="#FFFFFF" />
          <span>{t('my_looks.build_new')}</span>
        </Link>
      </header>

      {looks.length === 0 ? (
        <div className="py-20 text-center space-y-3">
          <p className="font-serif text-xl text-brand-charcoal">{t('my_looks.empty_title')}</p>
          <p className="text-sm text-brand-muted font-light">
            {t('my_looks.empty_body')}
          </p>
          <Link
            to="/builder"
            className="inline-block px-5 py-2.5 rounded-xl bg-brand-charcoal text-white text-xs font-bold focus-visible:outline-brand-charcoal"
          >
            {t('my_looks.open_composer')}
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {looks.map((look) => (
            <LookCard
              key={look.id}
              look={look}
              link={shareLinks[look.id]}
              busy={busyId === look.id}
              onShare={(rotate) => share(look.id, { rotate })}
              onRevoke={() => revoke(look.id)}
              onDelete={() => void remove(look.id)}
              onRename={(t) => void rename(look.id, t)}
            />
          ))}
        </div>
      )}
    </div>
  );
};
