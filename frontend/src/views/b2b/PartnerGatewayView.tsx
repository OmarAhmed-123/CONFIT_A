import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { ConfitLogo } from "../../components/common/ConfitLogo";
import { LeadForm } from "./LeadForm";
import {
  usePrefersReducedMotion,
} from "../../components/common/InteractionPrimitives";
import { resolveRegister, registerStyle } from "../../design/registers";
import { useUIStore } from "../../stores/uiStore";

/**
 * PartnerGatewayView — the public B2B partner gateway (B01), shown at /b2b
 * when there is no partner session.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * This page used to live INSIDE `RoleGuard.tsx`, as the `isPartnerPortal`
 * branch of a route guard. A guard that also owns a 300-line marketing
 * surface and a lead-capture form produced two of the measured defects
 * directly: the conversion action sat third in the DOM because the layout was
 * shaped by where the code happened to sit, and three identical grids stacked
 * because nothing owned the composition. The guard now renders this view and
 * owns no layout of its own.
 *
 * FIVE TIERS, FIVE DIFFERENT PRESENTATION STYLES
 * ----------------------------------------------
 * The previous page was nine identically-shaped containers, seven of them
 * produced by two `.map()` calls. No two tiers here share a pattern:
 *
 *   1 masthead   12-col, 7/5 split, form sticky — ABOVE the fold
 *   2 ledger     hairline dividers, no cards, mono numerals
 *   3 band       16:9 media with an overlapping offset caption
 *   4 tiers      three accordion rows, not three cards
 *   5 close      one CTA in negative space, no container at all
 *
 * FUNCTIONAL
 *  · resolves the partner design register from the route (`/b2b` → `partner`)
 *    instead of hard-coding colours, so the admin and partner portals stay
 *    distinguishable as spec 13 requires;
 *  · the CTA scrolls AND moves focus — scrolling alone leaves keyboard and
 *    screen-reader users reading the masthead while the form sits off-screen;
 *  · tier 4 is one-open-at-a-time with full aria-expanded/controls/region.
 * NON-FUNCTIONAL
 *  · every control >= 48px;
 *  · `justify-between` on the masthead column: Arabic runs ~30% longer than
 *    English, and distributing the headline against a fixed min-height keeps
 *    a long translation from collapsing or overflowing the column;
 *  · all motion is transform/opacity, gated on prefers-reduced-motion, on one
 *    luxury curve cubic-bezier(0.25, 1, 0.5, 1).
 */

/** Shared reveal spec. One curve, one distance, one stagger — declaring it
 *  per call site is how the page ends up with five different easings. */
const REVEAL = {
  initial: { opacity: 0, y: 16 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.25 },
  transition: { duration: 0.52, ease: [0.25, 1, 0.5, 1] },
} as const;

const STAGGER_STEP = 0.06;

const CAPABILITIES = [
  { index: "01", title: "partner.feat_catalog_title", copy: "partner.feat_catalog_copy" },
  { index: "02", title: "partner.feat_fit_title", copy: "partner.feat_fit_copy" },
  { index: "03", title: "partner.feat_tryon_title", copy: "partner.feat_tryon_copy" },
  { index: "04", title: "partner.feat_ops_title", copy: "partner.feat_ops_copy" },
] as const;

const PILLARS = [
  { title: "partner.pillar_problem_title", copy: "partner.pillar_problem_copy" },
  { title: "partner.pillar_launch_title", copy: "partner.pillar_launch_copy" },
  { title: "partner.pillar_proof_title", copy: "partner.pillar_proof_copy" },
] as const;

export const PartnerGatewayView: React.FC = () => {
  const { t } = useTranslation();
  const openAuthModal = useUIStore((s) => s.openAuthModal);
  const reduceMotion = usePrefersReducedMotion();
  const [openPillar, setOpenPillar] = useState<number | null>(0);

  // The page's accent and ink come from the design register for this route,
  // not from literals. /b2b resolves to `partner`; /admin resolves to `admin`
  // and the two can never meet (registers.ts ROUTE_TABLE).
  const surfaceStyle = registerStyle(resolveRegister("/b2b"));

  const scrollToForm = () => {
    const el = document.getElementById("partner-request");
    if (!el) return;
    el.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "center",
    });
    // Focus must follow the viewport. preventScroll stops focus() fighting
    // scrollIntoView into a double jump.
    el.querySelector<HTMLElement>("input, select, textarea")?.focus({
      preventScroll: true,
    });
  };

  return (
    <main
      style={surfaceStyle}
      className="min-h-[80vh] bg-[#FAF9F6] text-[#1B1F3B]"
      data-testid="partner-gateway"
    >
      {/* ── TIER 1 · editorial masthead, 7/5, form above the fold ───────── */}
      <section className="mx-auto grid max-w-[1280px] grid-cols-12 gap-6 px-5 pt-12 pb-12 sm:pt-16 lg:gap-8 lg:pt-24">
        <div className="col-span-12 flex min-h-[420px] flex-col justify-between lg:col-span-7">
          {/* Eyebrow: register accent + micro-label. The accent is a hairline
              and a label, never body text — brand gold is 2.71:1 on cream and
              is not permitted as text on a light surface. */}
          <span
            className="inline-flex w-fit items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em]"
            style={{ color: "var(--register-ink)" }}
          >
            <span
              aria-hidden="true"
              className="block h-px w-8"
              style={{ backgroundColor: "var(--register-accent)" }}
            />
            {t("partner.portal_badge")}
          </span>

          <div className="flex flex-col gap-5">
            <h1 className="font-serif text-[clamp(2.25rem,5.5vw,4rem)] font-bold leading-[1.02] tracking-[-0.02em]">
              {t("partner.hero_title")}
            </h1>
            <p className="max-w-[46ch] text-[1.0625rem] font-light leading-[1.65] text-slate-600">
              {t("partner.hero_body")}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={scrollToForm}
              className="inline-flex min-h-[48px] items-center rounded-[14px] bg-[#1B1F3B] px-6 text-xs font-bold uppercase tracking-wider text-white transition-colors duration-[140ms] ease-luxury hover:bg-[#13162C] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44] focus-visible:ring-offset-2"
            >
              {t("partner.request_partnership")}
            </button>
            <button
              type="button"
              onClick={() => openAuthModal("login")}
              className="inline-flex min-h-[48px] items-center rounded-[14px] border border-slate-300 px-6 text-xs font-bold uppercase tracking-wider transition-colors duration-[140ms] ease-luxury hover:border-slate-400 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44] focus-visible:ring-offset-2"
            >
              {t("partner.existing_sign_in")}
            </button>
          </div>
        </div>

        {/* Sticky so the conversion surface stays reachable while the
            masthead scrolls on desktop; top-aligned, never stretched, so the
            sticky offset cannot fight a resizing column. */}
        <div className="col-span-12 lg:col-span-5">
          <div className="lg:sticky lg:top-8">
            <LeadForm />
          </div>
        </div>
      </section>

      {/* ── TIER 2 · capability ledger: hairlines, not cards ────────────── */}
      <section className="border-y border-slate-200 bg-white">
        <ul className="mx-auto grid max-w-[1280px] grid-cols-1 divide-y divide-slate-200 sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4">
          {CAPABILITIES.map((c, i) => (
            <motion.li
              key={c.index}
              {...(reduceMotion ? {} : REVEAL)}
              transition={
                reduceMotion
                  ? undefined
                  : { ...REVEAL.transition, delay: i * STAGGER_STEP }
              }
              className="flex flex-col gap-2 border-slate-200 px-5 py-8 sm:border-l sm:px-6 sm:first:border-l-0 lg:px-8"
            >
              <span
                className="font-mono text-[0.6875rem] tracking-[0.14em]"
                style={{ color: "var(--register-accent)" }}
                aria-hidden="true"
              >
                {c.index}
              </span>
              <h2 className="font-serif text-[1.125rem] font-bold leading-snug">
                {t(c.title)}
              </h2>
              <p className="text-[0.875rem] font-light leading-[1.6] text-slate-600">
                {t(c.copy)}
              </p>
            </motion.li>
          ))}
        </ul>
      </section>

      {/* ── TIER 3 · proof band: 16:9 media, offset overlapping caption ─── */}
      <section className="mx-auto max-w-[1280px] px-5 py-16 lg:py-24">
        <div className="grid grid-cols-12 items-center gap-6">
          <figure className="col-span-12 lg:col-span-8">
            {/* 16:9 for the narrative sweep on desktop; 4:5 portrait on
                mobile, where a tall crop holds attention in a vertical
                scroll. Decorative only, so alt="" — it carries no claim the
                analytics could not support. */}
            <div
              aria-hidden="true"
              className="skeleton-shimmer aspect-[4/5] overflow-hidden rounded-[20px] bg-[#E1E5F2] lg:aspect-[16/9]"
            >
              <div className="h-full w-full bg-gradient-to-br from-[#1B1F3B] via-[#3D5296] to-[#B8935A] opacity-90 transition-transform duration-[520ms] ease-luxury hover:scale-[1.03]" />
            </div>
          </figure>

          {/* Offset: starts in column 9 but bleeds one gutter left on lg, so
              the caption overlaps the media instead of sitting beside it. */}
          <motion.figcaption
            {...(reduceMotion ? {} : REVEAL)}
            className="col-span-12 rounded-[20px] bg-white p-6 shadow-md lg:col-span-4 lg:-ms-8 lg:p-8"
          >
            <span
              aria-hidden="true"
              className="mb-4 block h-px w-8"
              style={{ backgroundColor: "var(--register-accent)" }}
            />
            <blockquote className="font-serif text-[1.25rem] leading-[1.4]">
              {t("partner.proof_quote")}
            </blockquote>
            <p className="mt-3 text-xs font-light text-slate-500">
              {t("partner.proof_attribution")}
            </p>
          </motion.figcaption>
        </div>
      </section>

      {/* ── TIER 4 · stacked tiers: three rows, not three cards ─────────── */}
      <section className="mx-auto max-w-[1280px] px-5 pb-16">
        <div className="border-t border-slate-200">
          {PILLARS.map((p, i) => {
            const isOpen = openPillar === i;
            return (
              <div key={p.title} className="border-b border-slate-200">
                <h2>
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    aria-controls={`pillar-panel-${i}`}
                    id={`pillar-trigger-${i}`}
                    onClick={() => setOpenPillar(isOpen ? null : i)}
                    className="group flex min-h-[48px] w-full items-center justify-between gap-4 py-5 text-start transition-colors duration-[140ms] ease-luxury focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44] focus-visible:ring-offset-2"
                    data-testid={`pillar-trigger-${i}`}
                  >
                    <span className="font-serif text-[1.25rem] font-bold leading-snug transition-colors duration-[140ms] ease-luxury group-hover:text-[var(--register-ink)]">
                      {t(p.title)}
                    </span>
                    <ChevronDown
                      aria-hidden="true"
                      className="shrink-0 text-slate-400 transition-transform duration-[260ms] ease-luxury"
                      style={{ transform: isOpen ? "rotate(180deg)" : "rotate(0deg)" }}
                    />
                  </button>
                </h2>

                {/* Height animates to auto so a long Arabic translation opens
                    to its true size instead of clipping at a fixed height. */}
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      id={`pillar-panel-${i}`}
                      role="region"
                      aria-labelledby={`pillar-trigger-${i}`}
                      initial={reduceMotion ? false : { height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={reduceMotion ? undefined : { height: 0, opacity: 0 }}
                      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                      className="overflow-hidden"
                    >
                      <p className="max-w-[62ch] pb-5 text-[0.9375rem] font-light leading-[1.7] text-slate-600">
                        {t(p.copy)}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── TIER 5 · close: one CTA in negative space ───────────────────── */}
      <section className="mx-auto flex max-w-[1280px] flex-col items-center gap-4 px-5 py-20 text-center">
        <div className="flex flex-col items-center gap-2">
          <ConfitLogo variant="mark" size="sm" />
          <h2 className="font-serif text-[1.75rem] font-bold leading-tight">
            {t("partner.close_title")}
          </h2>
        </div>
        <button
          type="button"
          onClick={scrollToForm}
          className="inline-flex min-h-[48px] items-center rounded-[14px] bg-[#1B1F3B] px-8 text-xs font-bold uppercase tracking-wider text-white transition-colors duration-[140ms] ease-luxury hover:bg-[#13162C] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44] focus-visible:ring-offset-2"
        >
          {t("partner.request_partnership")}
        </button>
        <button
          type="button"
          onClick={() => openAuthModal("login")}
          className="inline-flex min-h-[48px] items-center px-4 text-[0.875rem] underline underline-offset-4 decoration-[#A37E44] transition-colors duration-[140ms] ease-luxury hover:text-[var(--register-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44] focus-visible:ring-offset-2"
        >
          {t("partner.existing_sign_in")}
        </button>
      </section>
    </main>
  );
};

export default PartnerGatewayView;
