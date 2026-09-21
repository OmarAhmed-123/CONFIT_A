import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useMyLooksViewModel } from '../../viewmodels/useMyLooksViewModel';
import { Outfit, ShareLink } from '../../models';
import { SavedLooksIcon, SparkleIcon } from '../../components/icons/ConfitIcons';

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
  onShare: (rotate?: boolean) => void;
  onRevoke: () => void;
}> = ({ look, link, busy, onShare, onRevoke }) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const isLive = Boolean(link?.is_active && link?.share_url);
  const absolute = link?.share_url ? `${window.location.origin}${link.share_url}` : '';

  const copy = async () => {
    if (!absolute) return;
    try {
      await navigator.clipboard.writeText(absolute);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be blocked by permissions — say so instead of pretending.
      setCopied(false);
    }
  };

  if (!isLive) {
    return (
      <div className="pt-3 border-t border-slate-100 space-y-2">
        <p className="text-[11px] text-slate-500 font-light">
          {t('my_looks.private_note')}
        </p>
        <button
          onClick={() => onShare(false)}
          disabled={busy}
          className="w-full py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 text-white text-xs font-bold transition-all"
        >
          {busy ? t('my_looks.creating') : t('my_looks.create_link')}
        </button>
      </div>
    );
  }

  return (
    <div className="pt-3 border-t border-slate-100 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">
          {t('my_looks.link_active')}
        </span>
        <span className="text-[10px] text-slate-500">
          {link?.view_count ?? 0} {t('my_looks.views')}
        </span>
      </div>

      <div className="flex gap-2">
        <input
          readOnly
          value={absolute}
          aria-label={t('my_looks.public_link_for', { title: look.title })}
          className="flex-1 text-[11px] bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600"
        />
        <button
          onClick={copy}
          className="px-3 rounded-lg border border-slate-300 text-[11px] font-semibold hover:bg-slate-100"
        >
          {copied ? t('my_looks.copied') : t('my_looks.copy')}
        </button>
      </div>

      <p className="text-[10px] text-slate-500">
        {t('my_looks.expiry_note', { date: formatDate(link?.expires_at) })}
      </p>

      <div className="flex gap-2">
        <a
          href={link!.share_url!}
          target="_blank"
          rel="noreferrer"
          className="flex-1 text-center py-2 rounded-xl border border-slate-300 text-[11px] font-semibold hover:bg-slate-100"
        >
          {t('my_looks.open')}
        </a>
        <button
          onClick={() => onShare(true)}
          disabled={busy}
          className="flex-1 py-2 rounded-xl border border-slate-300 text-[11px] font-semibold hover:bg-slate-100 disabled:opacity-40"
          title={t('my_looks.new_link_hint')}
        >
          {t('my_looks.new_link')}
        </button>
        <button
          onClick={onRevoke}
          disabled={busy}
          className="flex-1 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 disabled:opacity-40 text-white text-[11px] font-bold"
        >
          {busy ? '…' : t('my_looks.revoke')}
        </button>
      </div>
    </div>
  );
};

const LookCard: React.FC<{
  look: Outfit;
  link?: ShareLink;
  busy: boolean;
  onShare: (rotate?: boolean) => void;
  onRevoke: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}> = ({ look, link, busy, onShare, onRevoke, onDelete, onRename }) => {
  const { t } = useTranslation();
  const [title, setTitle] = useState(look.title);
  const complete = look.completeness_status === 'complete_look';

  return (
    <article className="bg-white rounded-3xl border border-slate-200/80 p-5 shadow-2xs space-y-3">
      <div className="flex items-start justify-between gap-3">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => title !== look.title && onRename(title)}
          aria-label={t('my_looks.look_title_label')}
          className="font-serif text-lg font-bold text-[#1B1F3B] bg-transparent border-b border-transparent hover:border-slate-200 focus:border-[#C5A059] focus:outline-none flex-1"
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

      <div className="flex items-center gap-3 text-xs text-slate-500">
        <span>{look.occasion}</span>
        <span>·</span>
        <span>{look.items.length} {t('my_looks.pieces')}</span>
        <span>·</span>
        <span className="font-bold text-[#1B1F3B]">
          ${Number(look.total_price ?? 0).toFixed(2)}
        </span>
      </div>

      {/* Item strip, in the canonical layer order the server returns. */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {look.items.map((item) => (
          <div key={item.id} className="shrink-0 w-16">
            <div className="h-20 w-16 rounded-lg overflow-hidden bg-slate-100">
              {item.image_url ? (
                <img
                  src={item.image_url}
                  alt={item.product_title}
                  className="w-full h-full object-cover"
                />
              ) : null}
            </div>
            <span className="text-[9px] text-slate-500 block truncate mt-0.5">
              {item.position}
            </span>
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
          className="flex-1 text-center py-2 rounded-xl border border-slate-300 text-[11px] font-semibold hover:bg-slate-100"
        >
          {t('my_looks.edit_in_composer')}
        </Link>
        <button
          onClick={onDelete}
          disabled={busy}
          className="px-3 py-2 rounded-xl border border-slate-300 text-[11px] font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-40"
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
  } = useMyLooksViewModel();

  if (state === 'loading') {
    return (
      <div className="py-24 text-center text-slate-500" role="status">
        {t('my_looks.loading')}
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className="py-24 text-center space-y-3">
        <p className="text-slate-600">{error ?? t('my_looks.something_wrong')}</p>
        <button
          onClick={() => void reload()}
          className="px-4 py-2 rounded-xl border border-slate-300 text-xs font-semibold hover:bg-slate-100"
        >
          {t('my_looks.try_again')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-24">
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <SavedLooksIcon size={24} color="#1B1F3B" />
            <h1 className="font-serif text-3xl font-bold text-[#1B1F3B] tracking-tight">
              {t('my_looks.title')}
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
            {t('my_looks.subtitle')}
          </p>
        </div>
        <Link
          to="/builder"
          className="px-5 py-2 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] text-slate-950 font-bold text-xs flex items-center gap-1.5"
        >
          <SparkleIcon size={16} color="#0C0E1E" />
          <span>{t('my_looks.build_new')}</span>
        </Link>
      </header>

      {looks.length === 0 ? (
        <div className="py-20 text-center space-y-3">
          <p className="font-serif text-xl text-[#1B1F3B]">{t('my_looks.empty_title')}</p>
          <p className="text-sm text-slate-500 font-light">
            {t('my_looks.empty_body')}
          </p>
          <Link
            to="/builder"
            className="inline-block px-5 py-2.5 rounded-xl bg-[#1B1F3B] text-white text-xs font-bold"
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
              onShare={(rotate) => void share(look.id, { rotate })}
              onRevoke={() => void revoke(look.id)}
              onDelete={() => void remove(look.id)}
              onRename={(t) => void rename(look.id, t)}
            />
          ))}
        </div>
      )}
    </div>
  );
};
