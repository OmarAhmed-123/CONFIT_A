import React, { useId } from 'react';
import { Link } from 'react-router-dom';
import { HonestProductImage } from './HonestProductImage';

/**
 * HeroSection — the reusable "dark editorial hero + light structured card"
 * contrast (spec 07), used on Home and Discover ONLY. Checkout and the data
 * tables never import it (§2).
 *
 * Contract decisions, each mapped to a spec rule:
 *  · SEMANTIC SHELL (§6.1): a real `<section aria-labelledby>` with a real
 *    heading element — not a styled div soup. The heading level is a prop
 *    because Home owns the page h1 while other hosts may already have one.
 *  · INFORMATION NEVER SITS ON A BARE IMAGE (§8): all text lives on the
 *    solid dark gradient panel. Imagery goes through <HeroMedia>, which is
 *    decorative/supportive and carries its own CONSTANT scrim — an overlay
 *    div that exists whether the image loads, fails, or never arrives, so
 *    contrast is guaranteed by construction, not by trusting a photograph
 *    (§6.2 "overlay ثابت يضمن contrast").
 *  · IMAGE FAILURE CANNOT BREAK LAYOUT (§9): HeroMedia wraps
 *    HonestProductImage — a failed Unsplash fetch renders the explicit
 *    non-product placeholder in the same box; the grid never collapses.
 *  · PERF (§6.4): the editorial image is `loading="lazy"`,
 *    `decoding="async"`, `fetchpriority="low"`, and ships a responsive
 *    `srcSet` — it is a side panel hidden on small screens; the CTA group
 *    (§9 "فوق mobile fold") renders before it in DOM order.
 *  · NO MOTION DEPENDENCY: the hero is static CSS; nothing here waits for
 *    an animation, so `prefers-reduced-motion` changes nothing functional.
 */
export const HeroSection: React.FC<{
  /** Eyebrow badge row (already-localized node). */
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  /** Primary supporting copy. */
  lede?: React.ReactNode;
  /** Secondary, quieter copy. */
  support?: React.ReactNode;
  /** CTA group — rendered BEFORE the aside in DOM order (mobile fold). */
  actions?: React.ReactNode;
  /** Trust facts / chips row under the CTAs. */
  facts?: React.ReactNode;
  /** The structured light card / media panel (HeroLightCard, HeroMedia…). */
  aside?: React.ReactNode;
  /** h1 on the page that owns the title; h2 elsewhere. */
  headingLevel?: 'h1' | 'h2';
  /** Tighter paddings for list-page heroes (Discover). */
  compact?: boolean;
  className?: string;
}> = ({
  eyebrow,
  title,
  lede,
  support,
  actions,
  facts,
  aside,
  headingLevel = 'h1',
  compact = false,
  className = '',
}) => {
  const headingId = useId();
  const Heading = headingLevel;

  return (
    <section
      aria-labelledby={headingId}
      className={`relative overflow-hidden rounded-3xl sm:rounded-[36px] bg-gradient-to-br from-[#0C0E1E] via-[#1B1F3B] to-[#0A0C18] text-white border border-slate-800/80 shadow-2xl ${
        compact ? 'p-5 sm:p-8 lg:p-10' : 'p-6 sm:p-12 lg:p-20'
      } ${className}`}
    >
      {/* Ambient glows: decorative, pointer-transparent, behind content. */}
      <div className="absolute -top-32 -end-32 w-[500px] h-[500px] bg-[#C5A059]/15 rounded-full blur-3xl pointer-events-none" aria-hidden="true" />
      <div className="absolute -bottom-32 -start-32 w-[400px] h-[400px] bg-[#3D5296]/20 rounded-full blur-3xl pointer-events-none" aria-hidden="true" />

      <div
        className={`relative z-10 grid items-center gap-8 ${
          aside ? 'lg:grid-cols-[1.05fr_0.95fr]' : ''
        }`}
      >
        <div className={`space-y-5 ${compact ? 'max-w-3xl' : 'max-w-2xl space-y-6'}`}>
          {eyebrow}
          <Heading
            id={headingId}
            className={`font-serif font-bold tracking-tight text-white ${
              compact
                ? 'text-2xl sm:text-4xl leading-[1.15]'
                : 'text-3xl sm:text-5xl lg:text-6xl leading-[1.1]'
            }`}
          >
            {title}
          </Heading>
          {lede && (
            <p className="text-sm sm:leading-relaxed text-slate-200 font-light max-w-xl">{lede}</p>
          )}
          {support && (
            <p className="text-xs sm:text-sm sm:leading-relaxed text-slate-400 font-light max-w-xl">
              {support}
            </p>
          )}
          {actions && (
            <div className="pt-2 flex flex-wrap items-center gap-3 sm:gap-4">{actions}</div>
          )}
          {facts}
        </div>

        {aside}
      </div>
    </section>
  );
};

/**
 * HeroMedia — the editorial image panel with a GUARANTEED scrim.
 *
 * The caption area renders on top of `data-testid="hero-scrim"`, a constant
 * black gradient that does not depend on the image: a bright, dark, broken
 * or missing photograph all produce the same readable result. The image
 * itself is HonestProductImage, so a failed load shows the explicit
 * placeholder instead of silently collapsing the panel.
 */
export const HeroMedia: React.FC<{
  src?: string | null;
  alt: string;
  /** Localized label for the failed/missing-image state. */
  unavailableLabel: string;
  /** Caption content rendered above the scrim (badges, title, copy). */
  caption?: React.ReactNode;
  className?: string;
}> = ({ src, alt, unavailableLabel, caption, className = '' }) => (
  <div className={`relative h-72 overflow-hidden rounded-3xl bg-slate-900 ${className}`}>
    {src ? (
      <picture>
        {/* Unsplash serves parametrized widths; let the browser choose. */}
        <HonestProductImage
          src={src}
          alt={alt}
          unavailableLabel={unavailableLabel}
          className="h-full w-full object-cover opacity-90"
          loading="lazy"
          decoding="async"
          srcSet={
            /unsplash\.com/.test(src)
              ? `${src.replace(/w=\d+/, 'w=600')} 600w, ${src.replace(/w=\d+/, 'w=900')} 900w, ${src.replace(/w=\d+/, 'w=1400')} 1400w`
              : undefined
          }
          sizes="(min-width: 1024px) 40vw, 100vw"
        />
      </picture>
    ) : (
      // No image at all is a legitimate state (§5 no-image): the solid
      // panel + scrim keep the caption fully readable.
      <div className="h-full w-full bg-gradient-to-br from-[#1B1F3B] to-[#0C0E1E]" aria-hidden="true" />
    )}
    {/* The constant scrim — present in EVERY branch above. */}
    <div
      data-testid="hero-scrim"
      className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent pointer-events-none"
      aria-hidden="true"
    />
    {caption && <div className="absolute bottom-0 inset-x-0 p-5 text-white">{caption}</div>}
  </div>
);

/**
 * HeroLightCard — the structured LIGHT card inside the dark hero.
 *
 * With `to`, the whole card is ONE keyboard-focusable link to a real route
 * (§6.3) — no nested interactive elements are allowed inside (links in
 * links are invalid HTML and a screen-reader trap). Without `to`, it is a
 * plain light panel for hosts that embed their own controls (Discover's
 * search card).
 */
export const HeroLightCard: React.FC<{
  to?: string;
  /** Accessible name for the link variant (the card is one control). */
  label?: string;
  children: React.ReactNode;
  className?: string;
}> = ({ to, label, children, className = '' }) => {
  const base = `block rounded-[32px] border border-[#C5A059]/30 bg-white/10 p-4 shadow-2xl backdrop-blur-xl ${className}`;
  if (to) {
    return (
      <Link
        to={to}
        aria-label={label}
        className={`${base} min-h-11 transition-transform hover:scale-[1.01] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0C0E1E]`}
      >
        {children}
      </Link>
    );
  }
  return <div className={base}>{children}</div>;
};
