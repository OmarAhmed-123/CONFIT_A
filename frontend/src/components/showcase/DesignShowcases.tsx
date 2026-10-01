import React from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { BarChart3, Camera, Layers3, PackageCheck, Sparkles } from 'lucide-react';
import { CardStack, type CardStackItem } from '../ui/card-stack';
import { CircularGallery, type GalleryItem } from '../ui/circular-gallery';
import { AccessibleCarousel } from '../common/AccessibleCarousel';
import { usePrefersReducedMotion } from '../common/InteractionPrimitives';

/**
 * Spec 10 pass over the showcase carousels:
 *  · AUTOPLAY REMOVED (§6.4) — the CardStack no longer has a timer at all
 *    and the circular gallery's idle rotation defaults to OFF; rotation is
 *    driven by the user's scroll only.
 *  · Reduced motion renders a genuine 2D fallback (§1): the same items in
 *    an AccessibleCarousel (native scroll-snap, real links) instead of the
 *    3D fan — full function, no springs.
 *  · Every string left this file: titles, descriptions, control labels and
 *    alt text come from i18n (EN+AR), so the Arabic page is Arabic (§7).
 */

type ShowcaseTone = 'consumer' | 'tryon' | 'wardrobe' | 'commerce' | 'brand' | 'analytics';

type CardStackShowcaseProps = {
  tone?: ShowcaseTone;
  eyebrow?: string;
  title?: string;
  description?: string;
  compact?: boolean;
  className?: string;
};

type CircularGalleryShowcaseProps = CardStackShowcaseProps;

/** Static (non-linguistic) item data; copy lives in i18n under showcase.items.* */
type StackItemBase = { id: string; key: string; imageSrc: string; href: string; tag: string };

const consumerStackBase: StackItemBase[] = [
  { id: 'tailored-power', key: 'tailored_power', imageSrc: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80', href: '/discover', tag: 'Workwear' },
  { id: 'evening-silk', key: 'evening_silk', imageSrc: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80', href: '/discover', tag: 'Occasion' },
  { id: 'minimal-capsule', key: 'minimal_capsule', imageSrc: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80', href: '/discover', tag: 'Essentials' },
  { id: 'street-utility', key: 'street_utility', imageSrc: 'https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=900&auto=format&fit=crop&q=80', href: '/discover', tag: 'Casual' },
  { id: 'resort-linen', key: 'resort_linen', imageSrc: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&auto=format&fit=crop&q=80', href: '/discover', tag: 'Resort' },
];

const operationsStackBase: StackItemBase[] = [
  { id: 'catalog-quality', key: 'catalog_quality', imageSrc: 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=900&auto=format&fit=crop&q=80', href: '/b2b/catalog', tag: 'Catalog' },
  { id: 'inventory-ops', key: 'inventory_ops', imageSrc: 'https://images.unsplash.com/photo-1555529669-e69e7aa0ba9a?w=900&auto=format&fit=crop&q=80', href: '/b2b/inventory', tag: 'Inventory' },
  { id: 'placement-engine', key: 'placement_engine', imageSrc: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&auto=format&fit=crop&q=80', href: '/b2b/placements', tag: 'Placements' },
  { id: 'analytics-control', key: 'analytics_control', imageSrc: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=900&auto=format&fit=crop&q=80', href: '/b2b/analytics', tag: 'Analytics' },
  { id: 'fulfillment-trust', key: 'fulfillment_trust', imageSrc: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=900&auto=format&fit=crop&q=80', href: '/orders', tag: 'Fulfillment' },
];

type GalleryItemBase = { key: string; url: string; pos?: string; by: string };

const galleryBase: GalleryItemBase[] = [
  { key: 'workwear_fit', url: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80', pos: '50% 35%', by: 'Unsplash' },
  { key: 'evening_texture', url: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80', pos: '50% 30%', by: 'Tamara Bellis' },
  { key: 'capsule_layering', url: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80', pos: '50% 40%', by: 'Hunters Race' },
  { key: 'visual_search_mood', url: 'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=900&auto=format&fit=crop&q=80', pos: '50% 40%', by: 'Unsplash' },
  { key: 'wardrobe_reuse', url: 'https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=900&auto=format&fit=crop&q=80', pos: '50% 45%', by: 'Sarah Brown' },
  { key: 'boutique_operations', url: 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=900&auto=format&fit=crop&q=80', pos: '50% 45%', by: 'Clark Street Mercantile' },
];

const toneMeta: Record<ShowcaseTone, { icon: React.ComponentType<{ className?: string }>; stack: StackItemBase[] }> = {
  consumer: { icon: Sparkles, stack: consumerStackBase },
  tryon: { icon: Camera, stack: consumerStackBase },
  wardrobe: { icon: Layers3, stack: consumerStackBase },
  commerce: { icon: PackageCheck, stack: operationsStackBase },
  brand: { icon: Layers3, stack: operationsStackBase },
  analytics: { icon: BarChart3, stack: operationsStackBase },
};

function cx(...classes: Array<string | undefined | null | false>) {
  return classes.filter(Boolean).join(' ');
}

export const CardStackShowcase: React.FC<CardStackShowcaseProps> = ({
  tone = 'consumer',
  eyebrow,
  title,
  description,
  compact = false,
  className,
}) => {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const meta = toneMeta[tone];
  const Icon = meta.icon;
  const cardWidth = compact ? 300 : 360;
  const cardHeight = compact ? 240 : 420;

  const items: CardStackItem[] = meta.stack.map((it) => ({
    id: it.id,
    title: t(`showcase.items.${it.key}.title`),
    description: t(`showcase.items.${it.key}.description`),
    imageSrc: it.imageSrc,
    href: it.href,
    tag: it.tag,
  }));

  return (
    <section className={cx('relative overflow-hidden rounded-[32px] border border-[#C5A059]/25 bg-white shadow-2xs', compact ? 'p-5' : 'p-6 sm:p-9', className)}>
      <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#C5A059]/10 blur-3xl" />
      <div className="absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-[#1B1F3B]/10 blur-3xl" />
      <div className={cx('relative z-10 grid items-center gap-6', compact ? 'lg:grid-cols-[0.95fr_1.15fr]' : 'lg:grid-cols-[0.85fr_1.35fr]')}>
        <div className="space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#C5A059]/30 bg-[#FDF8EE] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">
            <span aria-hidden="true"><Icon className="h-3.5 w-3.5" /></span>
            <span>{eyebrow || t(`showcase.tones.${tone}.label`)}</span>
          </div>
          <h2 className={cx('font-serif font-bold leading-tight text-[#1B1F3B]', compact ? 'text-2xl' : 'text-3xl sm:text-4xl')}>
            {title || t(`showcase.tones.${tone}.title`)}
          </h2>
          <p className="text-sm font-light leading-relaxed text-slate-500">
            {description || t(`showcase.tones.${tone}.description`)}
          </p>
        </div>
        <div className="min-w-0 overflow-hidden py-2">
          {reduceMotion ? (
            /* Spec 10 §1: honest 2D fallback — same items, native scroll,
               real links, zero springs. Hierarchy is unchanged (§5). */
            <AccessibleCarousel
              items={items}
              getKey={(it) => it.id}
              label={t('showcase.stack_region')}
              data-testid="cardstack-2d-fallback"
              renderItem={(it) => (
                <Link
                  to={it.href ?? '/discover'}
                  className="block overflow-hidden rounded-2xl border border-[#C5A059]/25 bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44]"
                >
                  <img
                    src={it.imageSrc}
                    alt=""
                    loading="lazy"
                    className="h-40 w-full object-cover"
                  />
                  <div className="space-y-1 p-4">
                    <h3 className="text-sm font-bold text-[#1B1F3B]">{it.title}</h3>
                    <p className="text-xs leading-relaxed text-slate-500">{it.description}</p>
                  </div>
                </Link>
              )}
            />
          ) : (
            <CardStack
              items={items}
              cardWidth={cardWidth}
              cardHeight={cardHeight}
              maxVisible={5}
              spreadDeg={compact ? 28 : 34}
              overlap={compact ? 0.6 : 0.55}
              showDots
              labels={{
                carousel: t('showcase.stack_region'),
                previous: t('carousel.previous'),
                next: t('carousel.next'),
                goTo: (itemTitle) => t('carousel.go_to', { title: itemTitle }),
                open: (itemTitle) => t('carousel.open_item', { title: itemTitle }),
                position: (current, total) => t('carousel.position', { current, total }),
              }}
            />
          )}
        </div>
      </div>
    </section>
  );
};

export const CircularGalleryShowcase: React.FC<CircularGalleryShowcaseProps> = ({
  tone = 'consumer',
  eyebrow,
  title,
  description,
  compact = false,
  className,
}) => {
  const { t } = useTranslation();
  const meta = toneMeta[tone];
  const Icon = meta.icon;

  const galleryItems: GalleryItem[] = galleryBase.map((g) => ({
    common: t(`showcase.gallery_items.${g.key}.name`),
    binomial: t(`showcase.gallery_items.${g.key}.caption`),
    photo: {
      url: g.url,
      text: t(`showcase.gallery_items.${g.key}.alt`),
      pos: g.pos,
      by: g.by,
    },
  }));

  return (
    <section className={cx('relative overflow-hidden rounded-[32px] border border-[#C5A059]/25 bg-gradient-to-b from-[#FAF9F6] via-white to-[#F0F2F8] shadow-2xs', compact ? 'p-5' : 'p-6 sm:p-9', className)}>
      <div className="pointer-events-none absolute inset-x-0 top-12 mx-auto h-56 w-2/3 rounded-full bg-[#C5A059]/10 blur-3xl" />
      <div className="relative z-10 mx-auto max-w-3xl text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-[#C5A059]/30 bg-white px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[#7A5C28] backdrop-blur">
          <span aria-hidden="true"><Icon className="h-3.5 w-3.5" /></span>
          <span>{eyebrow || `${t(`showcase.tones.${tone}.label`)} — ${t('showcase.gallery_eyebrow_suffix')}`}</span>
        </div>
        <h2 className={cx('mt-3 font-serif font-bold leading-tight text-[#1B1F3B]', compact ? 'text-2xl' : 'text-3xl sm:text-4xl')}>
          {title || t('showcase.gallery_title')}
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-sm font-light leading-relaxed text-slate-500">
          {description || t('showcase.gallery_description')}
        </p>
      </div>
      <div className={cx('relative z-0 overflow-hidden', compact ? 'h-[430px]' : 'h-[540px]')}>
        {/* No autoRotateSpeed: idle rotation stays OFF (§6.4); rotation
            follows the user's scroll only. */}
        <CircularGallery
          items={galleryItems}
          radius={compact ? 360 : 520}
          ariaLabel={t('showcase.gallery_region')}
        />
      </div>
    </section>
  );
};
