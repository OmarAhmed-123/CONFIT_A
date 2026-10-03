import React from 'react';
import {
  HomeIcon,
  SparkleIcon,
  StylistIcon,
  OutfitBuilderIcon,
  VisualSearchIcon,
  FlameIcon,
  TryOnIcon,
  RulerIcon,
  WardrobeIcon,
  SavedLooksIcon,
  GapAnalysisIcon,
  BagIcon,
  OrdersIcon,
} from '../icons/ConfitIcons';

/**
 * ONE navigation vocabulary for the consumer shell (spec 05 §6.1).
 *
 * Desktop disclosure menus, the mobile drawer and active-state matching all
 * read from this table. Before it existed the desktop menu, the (absent)
 * mobile menu and the active-route logic each hard-coded their own copy of
 * the destinations — which is how mobile shipped with NO primary nav at all.
 *
 * Everything here is data: labels are i18n KEYS (resolved at the render
 * boundary in the active language), destinations are router paths, and
 * `match` lists the pathname prefixes that make the section "current".
 * Store-backed actions (stylist drawer, visual search) are named intents the
 * navbar maps to its own handlers — metadata never imports a store.
 */

export type NavAction = 'open-stylist' | 'open-visual-search';

export interface NavItem {
  id: string;
  labelKey: string;
  /** Secondary line in menus/drawer. Optional: top-level links have none. */
  descKey?: string;
  /** Router destination. Exactly one of `href` | `action` is set. */
  href?: string;
  /** Store-backed intent (drawer/modal) instead of a navigation. */
  action?: NavAction;
  icon: React.ComponentType<{ size?: number; color?: string; isActive?: boolean }>;
  /** Gold-accent treatment in menus (visual hierarchy only, never meaning). */
  accent?: boolean;
}

export interface NavSection {
  id: string;
  labelKey: string;
  icon: React.ComponentType<{ size?: number; color?: string; isActive?: boolean }>;
  /** Sections WITHOUT children are plain links. */
  href?: string;
  /** Sections WITH children render as disclosure menus / drawer groups. */
  children?: NavItem[];
  /**
   * Pathname prefixes that mark this section active. Matched as exact or
   * `prefix + '/'` so `/fit-finder` does not light up a `/fit` section twice.
   */
  match: string[];
}

export const CONSUMER_NAV: readonly NavSection[] = [
  {
    id: 'home',
    labelKey: 'nav.home',
    icon: HomeIcon,
    href: '/',
    match: ['/'],
  },
  {
    id: 'discover',
    labelKey: 'nav.style_discover',
    icon: SparkleIcon,
    match: ['/discover', '/builder', '/stylist'],
    children: [
      { id: 'stylist', labelKey: 'nav.stylist', descKey: 'nav_desc.stylist', action: 'open-stylist', icon: StylistIcon, accent: true },
      { id: 'builder', labelKey: 'nav.outfit_builder', descKey: 'nav_desc.builder_canvas', href: '/builder', icon: OutfitBuilderIcon },
      { id: 'visual-search', labelKey: 'nav.visual_search', descKey: 'nav_desc.visual_search', action: 'open-visual-search', icon: VisualSearchIcon, accent: true },
      { id: 'trending', labelKey: 'nav.trending', descKey: 'nav_desc.trending', href: '/discover', icon: FlameIcon },
    ],
  },
  {
    id: 'tryon',
    labelKey: 'nav.tryon_fit',
    icon: TryOnIcon,
    match: ['/tryon-studio', '/try-on', '/fit', '/fit-finder', '/visual-search'],
    children: [
      { id: 'virtual-tryon', labelKey: 'nav.virtual_tryon', descKey: 'nav_desc.virtual_tryon', href: '/tryon-studio', icon: TryOnIcon, accent: true },
      { id: 'no-photo-fit', labelKey: 'nav.no_photo_fit', descKey: 'nav_desc.no_photo_fit', href: '/fit', icon: RulerIcon },
    ],
  },
  {
    id: 'wardrobe',
    labelKey: 'nav.my_wardrobe',
    icon: WardrobeIcon,
    match: ['/wardrobe', '/my-looks', '/outfits'],
    children: [
      { id: 'closet', labelKey: 'nav.my_closet', descKey: 'nav_desc.wardrobe', href: '/wardrobe', icon: WardrobeIcon },
      { id: 'looks', labelKey: 'nav.my_looks', descKey: 'nav_desc.my_looks', href: '/wardrobe?tab=looks', icon: SavedLooksIcon },
      { id: 'gaps', labelKey: 'nav.gap_analysis', descKey: 'nav_desc.gap_analysis', href: '/wardrobe?tab=gaps', icon: GapAnalysisIcon, accent: true },
    ],
  },
  {
    id: 'shop',
    labelKey: 'nav.shop',
    icon: BagIcon,
    match: ['/products', '/product', '/orders', '/returns', '/cart', '/checkout'],
    children: [
      { id: 'collections', labelKey: 'nav.all_collections', descKey: 'nav_desc.catalog', href: '/discover', icon: BagIcon },
      { id: 'orders', labelKey: 'nav.orders_tracking', descKey: 'nav_desc.orders_timeline', href: '/orders', icon: OrdersIcon },
    ],
  },
];

/**
 * Is `section` the one the visitor is on? `/` matches only exactly — the home
 * anchor must not light up on every route of the app.
 */
export function isSectionActive(section: NavSection, pathname: string): boolean {
  return section.match.some((prefix) =>
    prefix === '/' ? pathname === '/' : pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/** Active check for a single destination (exact path; query ignored). */
export function isItemActive(item: NavItem, pathname: string): boolean {
  if (!item.href) return false;
  const clean = item.href.split('?')[0];
  return clean === '/' ? pathname === '/' : pathname === clean || pathname.startsWith(`${clean}/`);
}
