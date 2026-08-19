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

export const ConfitColors = {
  navy: '#1B1F3B',
  gold: '#C5A059',
  goldLight: '#FDF8EE',
  goldHover: '#E2BF70',
  cream: '#FAF9F6',
  slateDark: '#0C0E1E',
  grey: '#64748B',
  lightGrey: '#E2E8F0',
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
      <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#C5A059] px-1 text-[9px] font-bold text-slate-950 shadow-xs ring-1 ring-white">
        {badge > 99 ? '99+' : badge}
      </span>
    )}
  </span>
);

// 1. Home Icon
export const HomeIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Home' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M3 9.5L12 3L21 9.5V20C21 20.55 20.55 21 20 21H15V14H9V21H4C3.45 21 3 20.55 3 20V9.5Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}18` : 'none'} />
    </IconWrapper>
  );
};

// 2. Sparkle / AI Icon
export const SparkleIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'AI Feature' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 2L14.4 8.6L21 11L14.4 13.4L12 20L9.6 13.4L3 11L9.6 8.6L12 2Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}25` : 'none'} />
      <path d="M18.5 3.5L19.5 6.5L22.5 7.5L19.5 8.5L18.5 11.5L17.5 8.5L14.5 7.5L17.5 6.5L18.5 3.5Z" stroke={strokeColor} strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 3. Stylist Icon
export const StylistIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Stylist' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M21 15C21 15.53 20.79 16.04 20.41 16.41C20.04 16.79 19.53 17 19 17H7L3 21V5C3 4.47 3.21 3.96 3.59 3.59C3.96 3.21 4.47 3 5 3H19C19.53 3 20.04 3.21 20.41 3.59C20.79 3.96 21 4.47 21 5V15Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
      <path d="M9.5 8.5L12 11L14.5 8.5" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 11V13.5" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 4. Outfit Builder Icon
export const OutfitBuilderIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Outfit Builder' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="3" y="3" width="7" height="7" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
      <rect x="14" y="3" width="7" height="7" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
      <rect x="14" y="14" width="7" height="7" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
      <rect x="3" y="14" width="7" height="7" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
    </IconWrapper>
  );
};

// 5. Visual Search Icon
export const VisualSearchIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Visual Search' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
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
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M8.5 14.5C8.5 16.43 10.07 18 12 18C13.93 18 15.5 16.43 15.5 14.5C15.5 12.5 13.5 10 12 8C10.5 10 8.5 12.5 8.5 14.5Z" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}25` : 'none'} />
      <path d="M12 2C7.5 6.5 5 10.5 5 14.5C5 18.64 8.13 22 12 22C15.87 22 19 18.64 19 14.5C19 9.5 15.5 4.5 12 2Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 7. Virtual Try-On Icon
export const TryOnIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Virtual Try-On' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 3C8.5 3 6.5 5 6.5 7.5C6.5 9.5 7.8 11.2 9.5 11.8V19C9.5 19.55 9.95 20 10.5 20H13.5C14.05 20 14.5 19.55 14.5 19V11.8C16.2 11.2 17.5 9.5 17.5 7.5C17.5 5 15.5 3 12 3Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
      <path d="M6.5 7.5L3 9.5L4.5 14.5L7 13.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M17.5 7.5L21 9.5L19.5 14.5L17 13.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 8. Ruler / Measurement Icon
export const RulerIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Body Sizing Ruler' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M21.5 8.5L15.5 2.5C14.7 1.7 13.3 1.7 12.5 2.5L2.5 12.5C1.7 13.3 1.7 14.7 2.5 15.5L8.5 21.5C9.3 22.3 10.7 22.3 11.5 21.5L21.5 11.5C22.3 10.7 22.3 9.3 21.5 8.5Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
      <line x1="8.5" y1="8.5" x2="10.5" y2="10.5" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="5" x2="15" y2="8" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="15.5" y1="1.5" x2="19.5" y2="5.5" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="5" y1="12" x2="8" y2="15" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 9. Wardrobe Icon
export const WardrobeIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Wardrobe' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="4" y="3" width="16" height="18" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
      <line x1="12" y1="3" x2="12" y2="21" stroke={strokeColor} strokeWidth="1.75" />
      <circle cx="9.5" cy="11.5" r="1" fill={strokeColor} />
      <circle cx="14.5" cy="11.5" r="1" fill={strokeColor} />
    </IconWrapper>
  );
};

// 10. Saved Looks Icon
export const SavedLooksIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Saved Looks' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M19 21L12 16L5 21V5C5 4.45 5.45 4 6 4H18C18.55 4 19 4.45 19 5V21Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}25` : 'none'} />
    </IconWrapper>
  );
};

// 11. Gap Analysis Icon
export const GapAnalysisIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Gap Analysis' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <circle cx="12" cy="12" r="9" stroke={strokeColor} strokeWidth="1.75" />
      <path d="M12 3V12L18.5 16.5" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 12. Shopping Bag / Cart Icon
export const BagIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, badge, color, ariaLabel = 'Shopping Bag' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel} badge={badge}>
      <path d="M6 8H18L19.5 20C19.5 20.55 19.05 21 18.5 21H5.5C4.95 21 4.5 20.55 4.5 20L6 8Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
      <path d="M9 8V5C9 3.9 9.9 3 11 3H13C14.1 3 15 3.9 15 5V8" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </IconWrapper>
  );
};

// 13. Orders & Tracking Icon
export const OrdersIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Orders' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="3" y="4" width="18" height="16" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
      <path d="M7 8H17" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M7 12H17" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M7 16H13" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 14. BOPIS Icon (Boutique Store Pickup)
export const BopisIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Boutique Store Pickup' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M3 9L4.5 4H19.5L21 9V19C21 19.55 20.55 20 20 20H4C3.45 20 3 19.55 3 19V9Z" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
      <path d="M3 9H21" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M9 13C9 14.66 10.34 16 12 16C13.66 16 15 14.66 15 13" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 15. User / Account Icon
export const UserIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'User Account' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <circle cx="12" cy="7.5" r="4" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
      <path d="M4.5 20C4.5 16.5 7.5 14 12 14C16.5 14 19.5 16.5 19.5 20" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 16. Brand Dashboard Icon
export const BrandDashboardIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Brand Dashboard' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="3" y="6" width="18" height="15" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
      <path d="M8 6V4C8 3.45 8.45 3 9 3H15C15.55 3 16 3.45 16 4V6" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <line x1="7" y1="16" x2="7" y2="13" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" />
      <line x1="12" y1="16" x2="12" y2="11" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" />
      <line x1="17" y1="16" x2="17" y2="9" stroke={ConfitColors.gold} strokeWidth="2" strokeLinecap="round" />
    </IconWrapper>
  );
};

// 17. Lock Icon
export const LockIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Security Lock' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="5" y="11" width="14" height="10" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
      <path d="M8 11V7C8 4.79 9.79 3 12 3C14.21 3 16 4.79 16 7V11" stroke={strokeColor} strokeWidth="1.75" />
      <circle cx="12" cy="16" r="1.5" fill={strokeColor} />
    </IconWrapper>
  );
};

// 18. Shield Icon
export const ShieldIcon: React.FC<IconProps> = ({ size = 20, className = '', isActive = false, color, ariaLabel = 'Security Shield' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 3L4 6.5V12.5C4 17.5 7.5 21 12 22C16.5 21 20 17.5 20 12.5V6.5L12 3Z" stroke={strokeColor} strokeWidth="1.75" strokeLinejoin="round" fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
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
  const strokeColor = color || (isActive ? ConfitColors.gold : 'currentColor');
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="8" y="8" width="12" height="12" rx="2" stroke={strokeColor} strokeWidth="1.75" fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
      <path d="M4 16V6C4 4.9 4.9 4 6 4H16" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <path d="M14 11V14" stroke={strokeColor} strokeWidth="1.75" strokeLinecap="round" />
      <circle cx="14" cy="17" r="0.75" fill={strokeColor} />
    </IconWrapper>
  );
};
