import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import type { Category } from "../../models";
import {
  SparkleIcon,
  RulerIcon,
  WardrobeIcon,
} from "../icons/ConfitIcons";
import { usePrefersReducedMotion } from "../common/InteractionPrimitives";

/**
 * Collection navigation rail — the homepage's primary wayfinding.
 *
 * Why it exists (Baymard category-page research, applied to the home page):
 * fashion shoppers think in collections and occasions, not product names, and
 * navigation must outrank every curated/promotional section. Before this rail
 * the home page had NO route into the catalogue's six categories at all — a
 * shopper had to open Discover and find the filter chips there.
 *
 * Honesty contract:
 * - Every tile is a REAL category from GET /catalog/categories (bilingual
 *   name/name_ar straight from the API — no invented collections).
 * - Every tile is a real deep link: /discover?category=<slug> lands on
 *   Discover with that filter applied (DiscoverView reads the param).
 * - No per-category counts are shown because the list API does not publish
 *   them — a number we cannot source is a number we do not render.
 *
 * Motion: entrance is opacity/translate only, staggered, `whileInView` once;
 * fully disabled under prefers-reduced-motion. Hover affordances use
 * `motion-safe:` so they vanish for reduced-motion users too.
 */

/** `icon_name` values the categories API actually emits today. */
const CATEGORY_ICONS: Record<
  string,
  React.FC<{ size?: number; color?: string; className?: string }>
> = {
  sparkle: SparkleIcon,
  hanger: WardrobeIcon,
  ruler: RulerIcon,
};

export const CollectionRail: React.FC<{
  categories: Category[];
  isLoading: boolean;
}> = ({ categories, isLoading }) => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? "en";
  const isArabic = lang.startsWith("ar");
  const reduceMotion = usePrefersReducedMotion();

  if (!isLoading && categories.length === 0) {
    // No categories, no rail — an empty shell is filler, not navigation.
    return null;
  }

  const label = (cat: Category) =>
    isArabic && cat.name_ar ? cat.name_ar : cat.name;

  return (
    <section aria-labelledby="home-collections-title" className="space-y-5">
      <div className="flex items-end justify-between border-b border-slate-200/80 pb-4">
        <div>
          <span className="block text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">
            {t("home.collections_eyebrow")}
          </span>
          <h2
            id="home-collections-title"
            className="mt-1 font-serif text-2xl font-bold text-[#1B1F3B]"
          >
            {t("home.collections_title")}
          </h2>
        </div>
      </div>

      <nav aria-label={t("home.collections_aria")}>
        {isLoading ? (
          <div
            className="grid grid-cols-3 gap-3 sm:grid-cols-6"
            aria-hidden="true"
          >
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="h-32 animate-pulse rounded-3xl border border-slate-200/60 bg-slate-100"
              />
            ))}
          </div>
        ) : (
          <ul className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:mx-0 sm:px-0 lg:grid lg:grid-cols-6 lg:overflow-visible lg:pb-0">
            {categories.map((cat, index) => {
              const Icon = CATEGORY_ICONS[cat.icon_name] ?? SparkleIcon;
              const tile = (
                <Link
                  to={`/discover?category=${encodeURIComponent(cat.slug)}`}
                  className="group flex h-full flex-col items-start gap-3 rounded-3xl border border-slate-200/80 bg-white p-4 shadow-2xs transition-all duration-300 hover:border-[#C5A059]/60 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
                >
                  <span
                    aria-hidden="true"
                    className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#1B1F3B] shadow-xs transition-transform duration-300 motion-safe:group-hover:scale-110"
                  >
                    <Icon size={20} color="#C5A059" />
                  </span>
                  <span className="min-h-10 text-sm font-semibold leading-snug text-[#1B1F3B] transition-colors group-hover:text-[#7A5C28]">
                    {label(cat)}
                  </span>
                  <span
                    aria-hidden="true"
                    className="block h-0.5 w-6 rounded-full bg-[#C5A059] transition-all duration-300 motion-safe:group-hover:w-12"
                  />
                </Link>
              );
              return (
                <li
                  key={cat.id}
                  className="w-36 shrink-0 snap-start lg:w-auto"
                >
                  {reduceMotion ? (
                    tile
                  ) : (
                    <motion.div
                      className="h-full"
                      initial={{ opacity: 0, y: 14 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, margin: "-40px" }}
                      transition={{
                        duration: 0.4,
                        delay: index * 0.06,
                        ease: "easeOut",
                      }}
                    >
                      {tile}
                    </motion.div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </nav>
    </section>
  );
};
