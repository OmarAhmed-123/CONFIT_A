import React from 'react';

export interface IconProps {
  size?: number;
  className?: string;
  isActive?: boolean;
  isAi?: boolean;
  color?: string;
  badge?: number;
  ariaLabel?: string;
}

/**
 * Icon palette — Logo #3 "Individual Grid" (official values, sampled from
 * /public/brand/confit-logo.svg). The legacy navy/gold keys are kept as
 * aliases so existing callers keep compiling, but they now resolve to the
 * official identity:
 *   - `ink` / `navy` / `gold` (active stroke) → brand charcoal. Gold #C5A059
 *     was 2.46:1 on white and failed WCAG 1.4.11 for an active-state glyph.
 *   - `accent` → brand coral, used ONLY as a translucent active-state tint.
 * Status colours (emerald / rose) are semantic and unchanged.
 */
export const ConfitColors = {
  ink: '#242526',
  accent: '#EF826D',
  lilac: '#A99AD6',
  mint: '#89B799',
  navy: '#242526',
  gold: '#242526',
  goldLight: '#F7F6F3',
  goldHover: '#595C63',
  cream: '#FFFFFF',
  slateDark: '#242526',
  grey: '#595C63',
  lightGrey: '#E8E6E2',
  emerald: '#059669',
  rose: '#E11D48',
};

const IconWrapper: React.FC<{
  size: number;
  className: string;
  ariaLabel?: string;
  badge?: number;
  children: React.ReactNode;
}> = ({ size, className, ariaLabel, badge, children }) => (
  <span className={`relative inline-flex items-center justify-center ${className}`} aria-label={ariaLabel} role="img">
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="transition-colors duration-200"
    >
      {children}
    </svg>
    {typeof badge === 'number' && badge > 0 && (
      <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-coral px-1 text-[9px] font-bold text-white shadow-xs ring-1 ring-white">
        {badge > 99 ? '99+' : badge}
      </span>
    )}
  </span>
);

// 1. Home Icon
export const HomeIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Home' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M3 9.5L12 3L21 9.5V20C21 20.55 20.55 21 20 21H15V14H9V21H4C3.45 21 3 20.55 3 20V9.5Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}18` : 'none'} />
    </IconWrapper>
  );
};

// 2. Sparkle / AI Icon
export const SparkleIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'AI Feature' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 2L14.4 8.6L21 11L14.4 13.4L12 20L9.6 13.4L3 11L9.6 8.6L12 2Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}25` : 'none'} />
      <path d="M18.5 3.5L19.5 6.5L22.5 7.5L19.5 8.5L18.5 11.5L17.5 8.5L14.5 7.5L17.5 6.5L18.5 3.5Z" stroke={strokeColor} strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 3. Stylist Icon
export const StylistIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Stylist' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M21 15C21 15.53 20.79 16.04 20.41 16.41C20.04 16.79 19.53 17 19 17H7L3 21V5C3 4.47 3.21 3.96 3.59 3.59C3.96 3.21 4.47 3 5 3H19C19.53 3 20.04 3.21 20.41 3.59C20.79 3.96 21 4.47 21 5V15Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}15` : 'none'} />
      <path d="M9.5 8.5L12 11L14.5 8.5" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 11V13.5" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 4. Outfit Builder Icon
export const OutfitBuilderIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Outfit Builder' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="3" y="3" width="7" height="7" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
      <rect x="14" y="3" width="7" height="7" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
      <rect x="14" y="14" width="7" height="7" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
      <rect x="3" y="14" width="7" height="7" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
    </IconWrapper>
  );
};

// 5. Visual Search Icon
export const VisualSearchIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Visual Search' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M4 8V5C4 4.45 4.45 4 5 4H8" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M16 4H19C19.55 4 20 4.45 20 5V8" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M20 16V19C20 19.55 19.55 20 19 20H16" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M8 20H5C4.45 20 4 19.55 4 19V16" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <circle cx="11.5" cy="11.5" r="3.5" stroke={strokeColor} strokeWidth="1.75" />
      <path d="M14 14L17.5 17.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 6. Flame / Trending Icon
export const FlameIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Trending' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M8.5 14.5C8.5 16.43 10.07 18 12 18C13.93 18 15.5 16.43 15.5 14.5C15.5 12.5 13.5 10 12 8C10.5 10 8.5 12.5 8.5 14.5Z" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}25` : 'none'} />
      <path d="M12 2C7.5 6.5 5 10.5 5 14.5C5 18.64 8.13 22 12 22C15.87 22 19 18.64 19 14.5C19 9.5 15.5 4.5 12 2Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 7. Virtual Try-On Icon
export const TryOnIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Virtual Try-On' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 3C8.5 3 6.5 5 6.5 7.5C6.5 9.5 7.8 11.2 9.5 11.8V19C9.5 19.55 9.95 20 10.5 20H13.5C14.05 20 14.5 19.55 14.5 19V11.8C16.2 11.2 17.5 9.5 17.5 7.5C17.5 5 15.5 3 12 3Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
      <path d="M6.5 7.5L3 9.5L4.5 14.5L7 13.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M17.5 7.5L21 9.5L19.5 14.5L17 13.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 8. Ruler / Measurement Icon
export const RulerIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Body Sizing Ruler' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M21.5 8.5L15.5 2.5C14.7 1.7 13.3 1.7 12.5 2.5L2.5 12.5C1.7 13.3 1.7 14.7 2.5 15.5L8.5 21.5C9.3 22.3 10.7 22.3 11.5 21.5L21.5 11.5C22.3 10.7 22.3 9.3 21.5 8.5Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
      <line x1="8.5" y1="8.5" x2="10.5" y2="10.5" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="5" x2="15" y2="8" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="15.5" y1="1.5" x2="19.5" y2="5.5" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="5" y1="12" x2="8" y2="15" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 9. Wardrobe Icon
export const WardrobeIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Wardrobe' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="4" y="3" width="16" height="18" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}15` : 'none'} />
      <line x1="12" y1="3" x2="12" y2="21" stroke={strokeColor} strokeWidth="1.75" />
      <circle cx="9.5" cy="11.5" r="1" fill={strokeColor} />
      <circle cx="14.5" cy="11.5" r="1" fill={strokeColor} />
    </IconWrapper>
  );
};

// 10. Saved Looks Icon
export const SavedLooksIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Saved Looks' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M19 21L12 16L5 21V5C5 4.45 5.45 4 6 4H18C18.55 4 19 4.45 19 5V21Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}25` : 'none'} />
    </IconWrapper>
  );
};

// 11. Gap Analysis Icon
export const GapAnalysisIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Gap Analysis' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <circle cx="12" cy="12" r="9" stroke={strokeColor} strokeWidth="1.75" />
      <path d="M12 3V12L18.5 16.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 12. Shopping Bag / Cart Icon
export const BagIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, badge, color, ariaLabel = 'Shopping Bag' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel} badge={badge}>
      <path d="M6 8H18L19.5 20C19.5 20.55 19.05 21 18.5 21H5.5C4.95 21 4.5 20.55 4.5 20L6 8Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}15` : 'none'} />
      <path d="M9 8V5C9 3.9 9.9 3 11 3H13C14.1 3 15 3.9 15 5V8" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 13. Orders & Tracking Icon
export const OrdersIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Orders' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="3" y="4" width="18" height="16" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}15` : 'none'} />
      <path d="M7 8H17" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M7 12H17" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M7 16H13" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 14. BOPIS Icon (Boutique Store Pickup)
export const BopisIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Boutique Store Pickup' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M3 9L4.5 4H19.5L21 9V19C21 19.55 20.55 20 20 20H4C3.45 20 3 19.55 3 19V9Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}15` : 'none'} />
      <path d="M3 9H21" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M9 13C9 14.66 10.34 16 12 16C13.66 16 15 14.66 15 13" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 15. User / Account Icon
export const UserIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'User Account' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <circle cx="12" cy="7.5" r="4" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
      <path d="M4.5 20C4.5 16.5 7.5 14 12 14C16.5 14 19.5 16.5 19.5 20" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 16. Brand Dashboard Icon
export const BrandDashboardIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Brand Dashboard' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="3" y="6" width="18" height="15" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}15` : 'none'} />
      <path d="M8 6V4C8 3.45 8.45 3 9 3H15C15.55 3 16 3.45 16 4V6" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <line x1="7" y1="16" x2="7" y2="13" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" />
      <line x1="12" y1="16" x2="12" y2="11" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" />
      <line x1="17" y1="16" x2="17" y2="9" stroke={ConfitColors.accent} strokeWidth="2" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 17. Lock Icon
export const LockIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Security Lock' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="5" y="11" width="14" height="10" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}15` : 'none'} />
      <path d="M8 11V7C8 4.79 9.79 3 12 3C14.21 3 16 4.79 16 7V11" stroke={strokeColor} strokeWidth="1.75" />
      <circle cx="12" cy="16" r="1.5" fill={strokeColor} />
    </IconWrapper>
  );
};

// 18. Shield Icon
export const ShieldIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Security Shield' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 3L4 6.5V12.5C4 17.5 7.5 21 12 22C16.5 21 20 17.5 20 12.5V6.5L12 3Z" stroke={strokeColor} strokeWidth="1.75" strokeLinejoin="round" fill={isActive ? `${ConfitColors.accent}15` : 'none'} />
      <path d="M9 12L11 14L15 10" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 19. Heart / Wishlist Icon
export const HeartIcon: React.FC<IconProps & { isLiked?: boolean }> = ({ size = 20, className = '', isLiked = false, color, ariaLabel = 'Wishlist' }) => {
  const strokeColor = isLiked ? '#E11D48' : (color || 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path
        d="M12 21.35L10.55 20.03C5.4 15.36 2 12.28 2 8.5C2 5.42 4.42 3 7.5 3C9.24 3 10.91 3.81 12 5.09C13.09 3.81 14.76 3 16.5 3C19.58 3 22 5.42 22 8.5C22 12.28 18.6 15.36 13.45 20.04L12 21.35Z"
        stroke={strokeColor}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill={isLiked ? '#E11D48' : 'none'}
      />
    </IconWrapper>
  );
};

// 20. Duplicate Alert Icon
export const DuplicateAlertIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Duplicate Purchase Alert' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="8" y="8" width="12" height="12" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
      <path d="M4 16V6C4 4.9 4.9 4 6 4H16" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M14 11V14" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <circle cx="14" cy="17" r="0.75" fill={strokeColor} />
    </IconWrapper>
  );
};

// 21. Microphone (voice input) — replaces the 🎙️ emoji that rendered as an
// uncontrolled platform glyph in a production control (spec 14: no emoji as
// production state). Stroke-based, inherits the house icon grammar.
export const MicIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Voice input' }) => {
  const strokeColor = color || (isActive ? ConfitColors.ink : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="9.5" y="4" width="5" height="9" rx="2.5" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.accent}20` : 'none'} />
      <path d="M6 11.5C6 14.8 8.7 17.5 12 17.5C15.3 17.5 18 14.8 18 11.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M12 17.5V20.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   FUNCTIONAL VERB GLYPHS — Part 3

   The set above names PLACES (Home, Wardrobe, Bag, Orders): it tells a user
   where a control goes. These name ACTIONS, so a control can tell a user what
   it is about to do — an upload arrow that rises, a download arrow that falls
   into a tray, a paper plane that flies, a play triangle that becomes a pause
   bar, a bookmark outline that fills, a bin that empties.

   Two deliberate differences from the icons above:

   1 · Every part that moves carries a `confit-glyph-*` class. The motion lives
       in `src/styles/button-glyph-motion.css`, keyed off the same
       `data-motion` + state attributes the background engine already reads, so
       a glyph cannot animate in a state the product does not publish.
   2 · They are DECORATIVE by default (aria-hidden), because they are authored
       for use INSIDE a labelled control. The icons above default to
       role="img" + aria-label, which is correct for a standalone icon and
       wrong inside a button: the label would be read twice (once for the icon,
       once for the text). Pass `ariaLabel` explicitly to opt back in.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface VerbIconProps extends IconProps {
  /** Overrides the decorative default; only for standalone use. */
  label?: string;
}

const VerbWrapper: React.FC<{
  size: number;
  glyph: string;
  className: string;
  label?: string;
  children: React.ReactNode;
}> = ({ size, glyph, className, label, children }) => (
  <span
    className={`confit-glyph confit-glyph--${glyph} relative inline-flex shrink-0 items-center justify-center ${className}`}
    {...(label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': 'true' })}
  >
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="confit-glyph-svg transition-colors duration-200"
      style={{ overflow: 'visible' }}
    >
      {children}
    </svg>
  </span>
);

// 23. Upload — an arrow lifting out of a tray.
export const UploadIcon: React.FC<VerbIconProps> = ({ size = 20, className = '', color, label }) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="upload" className={className} label={label}>
      <path className="confit-glyph-tray" d="M4 16.5V19C4 19.55 4.45 20 5 20H19C19.55 20 20 19.55 20 19V16.5" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <path className="confit-glyph-shaft" d="M12 15.5V4.5" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" />
      <path className="confit-glyph-head" d="M7.5 9L12 4.5L16.5 9" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </VerbWrapper>
  );
};

// 24. Download — the same arrow, received by the tray.
export const DownloadIcon: React.FC<VerbIconProps> = ({ size = 20, className = '', color, label }) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="download" className={className} label={label}>
      <path className="confit-glyph-tray" d="M4 16.5V19C4 19.55 4.45 20 5 20H19C19.55 20 20 19.55 20 19V16.5" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <path className="confit-glyph-shaft" d="M12 4.5V15.5" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" />
      <path className="confit-glyph-head" d="M7.5 11L12 15.5L16.5 11" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </VerbWrapper>
  );
};

// 25. Send — a paper plane, for submit/ask/publish.
export const SendIcon: React.FC<VerbIconProps> = ({ size = 20, className = '', color, label }) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="send" className={className} label={label}>
      <path className="confit-glyph-body" d="M21 3L10.8 13.2" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <path className="confit-glyph-body" d="M21 3L14.4 21L10.8 13.2L3 9.6L21 3Z" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </VerbWrapper>
  );
};

// 26. Retry — an arrow chasing its own tail.
export const RetryIcon: React.FC<VerbIconProps> = ({ size = 20, className = '', color, label }) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="retry" className={className} label={label}>
      <path className="confit-glyph-ring" d="M20 12C20 16.42 16.42 20 12 20C7.58 20 4 16.42 4 12C4 7.58 7.58 4 12 4C15.1 4 17.8 5.76 19.1 8.35" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" />
      <path className="confit-glyph-head" d="M19.5 4V8.75H14.75" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </VerbWrapper>
  );
};

// 27. Trash — a lid that lifts and a bin that empties.
export const TrashIcon: React.FC<VerbIconProps> = ({ size = 20, className = '', color, label }) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="trash" className={className} label={label}>
      <path className="confit-glyph-lid" d="M4 7H20" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" />
      <path className="confit-glyph-lid" d="M9.5 7V4.8C9.5 4.36 9.86 4 10.3 4H13.7C14.14 4 14.5 4.36 14.5 4.8V7" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <path className="confit-glyph-body" d="M6.5 7L7.4 19.2C7.44 19.65 7.82 20 8.27 20H15.73C16.18 20 16.56 19.65 16.6 19.2L17.5 7" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path className="confit-glyph-fill" d="M10.5 11V16.5" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" />
      <path className="confit-glyph-fill" d="M13.5 11V16.5" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" />
    </VerbWrapper>
  );
};

// 28. Bookmark — the outline that fills when something is saved.
export const BookmarkIcon: React.FC<VerbIconProps & { isSaved?: boolean }> = ({
  size = 20, className = '', color, label, isSaved = false,
}) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="bookmark" className={className} label={label}>
      <path
        className="confit-glyph-body"
        d="M7 4H17C17.55 4 18 4.45 18 5V20L12 16.3L6 20V5C6 4.45 6.45 4 7 4Z"
        stroke={stroke}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill={isSaved ? stroke : 'none'}
        fillOpacity={isSaved ? 0.9 : 0}
      />
    </VerbWrapper>
  );
};

// 29. Play / Pause — two glyphs in one control, swapped by state.
export const PlayPauseIcon: React.FC<VerbIconProps & { isPlaying?: boolean }> = ({
  size = 20, className = '', color, label, isPlaying = false,
}) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="playpause" className={className} label={label}>
      <path className="confit-glyph-play" d="M8.5 5.6V18.4L19 12L8.5 5.6Z" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isPlaying ? 'none' : stroke} fillOpacity={isPlaying ? 0 : 0.9} />
      <path className="confit-glyph-pause" d="M9.5 6V18" stroke={stroke} strokeWidth="2.25" strokeLinecap="round" />
      <path className="confit-glyph-pause" d="M14.5 6V18" stroke={stroke} strokeWidth="2.25" strokeLinecap="round" />
    </VerbWrapper>
  );
};

// 30. Share — the outward hand-off (link / invite / publish).
export const ShareGlyph: React.FC<VerbIconProps> = ({ size = 20, className = '', color, label }) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="share" className={className} label={label}>
      <circle className="confit-glyph-node confit-glyph-node-a" cx="17.5" cy="5.5" r="2.6" stroke={stroke} strokeWidth="1.75" />
      <circle className="confit-glyph-node confit-glyph-node-b" cx="6.5" cy="12" r="2.6" stroke={stroke} strokeWidth="1.75" />
      <circle className="confit-glyph-node confit-glyph-node-c" cx="17.5" cy="18.5" r="2.6" stroke={stroke} strokeWidth="1.75" />
      <path className="confit-glyph-link" d="M8.9 10.7L15.1 6.7" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" />
      <path className="confit-glyph-link" d="M8.9 13.3L15.1 17.3" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" />
    </VerbWrapper>
  );
};

// 31. Check — the confirmation a finite action earns.
export const CheckIcon: React.FC<VerbIconProps> = ({ size = 20, className = '', color, label }) => {
  const stroke = color || 'currentColor';
  return (
    <VerbWrapper size={size} glyph="check" className={className} label={label}>
      <path className="confit-glyph-check" d="M5 12.8L9.8 17.5L19 6.5" stroke={stroke} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </VerbWrapper>
  );
};
