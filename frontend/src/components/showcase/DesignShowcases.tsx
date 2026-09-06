import React from 'react';
import { BarChart3, Camera, Layers3, PackageCheck, Sparkles } from 'lucide-react';
import { CardStack, type CardStackItem } from '../ui/card-stack';
import { CircularGallery, type GalleryItem } from '../ui/circular-gallery';

type ShowcaseTone = 'consumer' | 'tryon' | 'wardrobe' | 'commerce' | 'brand' | 'analytics';

type CardStackShowcaseProps = {
  tone?: ShowcaseTone;
  eyebrow?: string;
  title?: string;
  description?: string;
  compact?: boolean;
  className?: string;
};

type CircularGalleryShowcaseProps = {
  tone?: ShowcaseTone;
  eyebrow?: string;
  title?: string;
  description?: string;
  compact?: boolean;
  className?: string;
};

const consumerStackItems: CardStackItem[] = [
  {
    id: 'tailored-power',
    title: 'Tailored Power',
    description: 'Structured tailoring for work, dinners, and polished day-to-night moments.',
    imageSrc: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80',
    href: '/discover',
    tag: 'Workwear',
  },
  {
    id: 'evening-silk',
    title: 'Evening Silk',
    description: 'Occasion dressing with fluid gowns, satin finishes, and gold accents.',
    imageSrc: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80',
    href: '/discover',
    tag: 'Occasion',
  },
  {
    id: 'minimal-capsule',
    title: 'Minimal Capsule',
    description: 'Quiet luxury essentials built for repeat wear and easy outfit pairing.',
    imageSrc: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80',
    href: '/discover',
    tag: 'Essentials',
  },
  {
    id: 'street-utility',
    title: 'Street Utility',
    description: 'Relaxed layers, sharp proportions, and practical weekend styling.',
    imageSrc: 'https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=900&auto=format&fit=crop&q=80',
    href: '/discover',
    tag: 'Casual',
  },
  {
    id: 'resort-linen',
    title: 'Resort Linen',
    description: 'Breathable neutrals and travel-friendly summer silhouettes.',
    imageSrc: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&auto=format&fit=crop&q=80',
    href: '/discover',
    tag: 'Resort',
  },
];

const operationsStackItems: CardStackItem[] = [
  {
    id: 'catalog-quality',
    title: 'Catalog Quality Gate',
    description: 'Merchandising teams review imagery, attributes, stock signals, and fit metadata before publishing.',
    imageSrc: 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=900&auto=format&fit=crop&q=80',
    href: '/b2b/catalog',
    tag: 'Catalog',
  },
  {
    id: 'inventory-ops',
    title: 'Inventory Operations',
    description: 'Boutique teams monitor live stock, pickup readiness, replenishment, and SKU-level health.',
    imageSrc: 'https://images.unsplash.com/photo-1555529669-e69e7aa0ba9a?w=900&auto=format&fit=crop&q=80',
    href: '/b2b/inventory',
    tag: 'Inventory',
  },
  {
    id: 'placement-engine',
    title: 'Placement Engine',
    description: 'Premium placements balance brand priority with shopper intent and conversion confidence.',
    imageSrc: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&auto=format&fit=crop&q=80',
    href: '/b2b/placements',
    tag: 'Placements',
  },
  {
    id: 'analytics-control',
    title: 'Analytics Control Room',
    description: 'Executive dashboards connect visual merchandising to margin, attribution, and try-on engagement.',
    imageSrc: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=900&auto=format&fit=crop&q=80',
    href: '/b2b/analytics',
    tag: 'Analytics',
  },
  {
    id: 'fulfillment-trust',
    title: 'Fulfillment Trust',
    description: 'Operational transparency covers order status, pickup windows, courier flows, and returns.',
    imageSrc: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=900&auto=format&fit=crop&q=80',
    href: '/orders',
    tag: 'Fulfillment',
  },
];

const galleryItems: GalleryItem[] = [
  {
    common: 'Workwear Fit',
    binomial: 'Structured blazer + trouser balance',
    photo: {
      url: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80',
      text: 'tailored suit styling',
      pos: '50% 35%',
      by: 'Unsplash',
    },
  },
  {
    common: 'Evening Texture',
    binomial: 'Silk, satin, and event-ready polish',
    photo: {
      url: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80',
      text: 'evening dress styling',
      pos: '50% 30%',
      by: 'Tamara Bellis',
    },
  },
  {
    common: 'Capsule Layering',
    binomial: 'Modern neutrals for daily rotation',
    photo: {
      url: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80',
      text: 'minimal fashion styling',
      pos: '50% 40%',
      by: 'Hunters Race',
    },
  },
  {
    common: 'Visual Search Mood',
    binomial: 'Camera-led outfit inspiration matching',
    photo: {
      url: 'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=900&auto=format&fit=crop&q=80',
      text: 'fashion shopping and visual discovery',
      pos: '50% 40%',
      by: 'Unsplash',
    },
  },
  {
    common: 'Wardrobe Reuse',
    binomial: 'Owned pieces styled into new looks',
    photo: {
      url: 'https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=900&auto=format&fit=crop&q=80',
      text: 'organized clothing wardrobe',
      pos: '50% 45%',
      by: 'Sarah Brown',
    },
  },
  {
    common: 'Boutique Operations',
    binomial: 'Catalog readiness and retail execution',
    photo: {
      url: 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=900&auto=format&fit=crop&q=80',
      text: 'premium retail boutique',
      pos: '50% 45%',
      by: 'Clark Street Mercantile',
    },
  },
];

const toneConfig = {
  consumer: {
    icon: Sparkles,
    stack: consumerStackItems,
    label: 'Consumer Style System',
    title: 'Interactive premium fashion discovery',
    description: 'Swipe through real editorial outfit directions and jump into catalog exploration with visual continuity.',
  },
  tryon: {
    icon: Camera,
    stack: consumerStackItems,
    label: 'Virtual Try-On Journey',
    title: 'From inspiration to body-aware fit',
    description: 'Use the same design language to connect moodboards, garments, visual search, and fit decisions.',
  },
  wardrobe: {
    icon: Layers3,
    stack: consumerStackItems,
    label: 'Wardrobe Reuse',
    title: 'Turn saved garments into styled rotations',
    description: 'Card stacks present reusable outfit formulas while circular galleries add premium visual browsing moments.',
  },
  commerce: {
    icon: PackageCheck,
    stack: operationsStackItems,
    label: 'Checkout Confidence',
    title: 'A premium purchase and fulfillment journey',
    description: 'Show delivery, returns, and pickup trust signals using the same tactile visual system.',
  },
  brand: {
    icon: Layers3,
    stack: operationsStackItems,
    label: 'Brand Partner UI',
    title: 'Operational storytelling for partners',
    description: 'B2B pages use the components for catalog, inventory, placements, and executive decisions.',
  },
  analytics: {
    icon: BarChart3,
    stack: operationsStackItems,
    label: 'Performance Intelligence',
    title: 'Visualize the path from styling to margin',
    description: 'Analytics surfaces stay visual and decision-oriented without becoming decorative or cartoonish.',
  },
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
  const config = toneConfig[tone];
  const Icon = config.icon;
  const cardWidth = compact ? 300 : 360;
  const cardHeight = compact ? 240 : 420;

  return (
    <section className={cx('relative overflow-hidden rounded-[32px] border border-[#C5A059]/25 bg-white shadow-2xs', compact ? 'p-5' : 'p-6 sm:p-9', className)}>
      <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#C5A059]/10 blur-3xl" />
      <div className="absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-[#1B1F3B]/10 blur-3xl" />
      <div className={cx('relative z-10 grid items-center gap-6', compact ? 'lg:grid-cols-[0.95fr_1.15fr]' : 'lg:grid-cols-[0.85fr_1.35fr]')}>
        <div className="space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#C5A059]/30 bg-[#FDF8EE] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">
            <Icon className="h-3.5 w-3.5" />
            <span>{eyebrow || config.label}</span>
          </div>
          <h2 className={cx('font-serif font-bold leading-tight text-[#1B1F3B]', compact ? 'text-2xl' : 'text-3xl sm:text-4xl')}>
            {title || config.title}
          </h2>
          <p className="text-sm font-light leading-relaxed text-slate-500">
            {description || config.description}
          </p>
        </div>
        <div className="min-w-0 overflow-hidden py-2">
          <CardStack
            items={config.stack}
            cardWidth={cardWidth}
            cardHeight={cardHeight}
            maxVisible={compact ? 5 : 5}
            spreadDeg={compact ? 28 : 34}
            overlap={compact ? 0.6 : 0.55}
            autoAdvance
            intervalMs={compact ? 2300 : 2600}
            pauseOnHover
            showDots
          />
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
  const config = toneConfig[tone];
  const Icon = config.icon;

  return (
    <section className={cx('relative overflow-hidden rounded-[32px] border border-[#C5A059]/25 bg-gradient-to-b from-[#FAF9F6] via-white to-[#F0F2F8] shadow-2xs', compact ? 'p-5' : 'p-6 sm:p-9', className)}>
      <div className="pointer-events-none absolute inset-x-0 top-12 mx-auto h-56 w-2/3 rounded-full bg-[#C5A059]/10 blur-3xl" />
      <div className="relative z-10 mx-auto max-w-3xl text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-[#C5A059]/30 bg-white px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[#7A5C28] backdrop-blur">
          <Icon className="h-3.5 w-3.5" />
          <span>{eyebrow || `${config.label} Gallery`}</span>
        </div>
        <h2 className={cx('mt-3 font-serif font-bold leading-tight text-[#1B1F3B]', compact ? 'text-2xl' : 'text-3xl sm:text-4xl')}>
          {title || 'Rotating visual system for every journey'}
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-sm font-light leading-relaxed text-slate-500">
          {description || 'A real, reusable 3D gallery brings collection stories, fit journeys, and operational insights into one premium interface.'}
        </p>
      </div>
      <div className={cx('relative z-0 overflow-hidden', compact ? 'h-[430px]' : 'h-[540px]')}>
        <CircularGallery items={galleryItems} radius={compact ? 360 : 520} autoRotateSpeed={compact ? 0.018 : 0.014} />
      </div>
    </section>
  );
};
