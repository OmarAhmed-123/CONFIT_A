import React from 'react';

export interface IconProps {
  className?: string;
  size?: number;
  color?: string;
  isActive?: boolean;
  isAi?: boolean;
  badge?: number | string;
  ariaLabel?: string;
}

export const ConfitColors = {
  navy: '#1B1F3B',
  gold: '#B8935A',
  grey: '#777777',
  white: '#FFFFFF',
  lightGold: '#FDF8EE',
  red: '#EF4444',
};

// Base SVG wrapper ensuring 24x24 grid, 2px stroke, and rounded joins
const IconWrapper: React.FC<{
  children: React.ReactNode;
  size?: number;
  className?: string;
  badge?: number | string;
  ariaLabel?: string;
}> = ({ children, size = 24, className = '', badge, ariaLabel }) => {
  return (
    <div className={`relative inline-flex items-center justify-center ${className}`} role="img" aria-label={ariaLabel}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="transition-colors duration-150"
      >
        {children}
      </svg>
      {badge !== undefined && Number(badge) > 0 && (
        <span className="absolute -top-1 -right-1 bg-[#B8935A] text-white text-[10px] font-bold min-w-[16px] h-[16px] rounded-full flex items-center justify-center px-1 shadow-sm animate-pulse">
          {badge}
        </span>
      )}
    </div>
  );
};

// 1. Home Dashboard Icon: House outline
export const HomeIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Home Dashboard' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path
        d="M3 10.5L12 3L21 10.5V20C21 20.5523 20.5523 21 20 21H4C3.44772 21 3 20.5523 3 20V10.5Z"
        stroke={strokeColor}
        fill={isActive ? `${ConfitColors.navy}15` : 'none'}
      />
      <path d="M9 21V12H15V21" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 2. Style & Discover Parent Icon: 4-Point Luxury Gold Sparkle
export const SparkleIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Style & Discover' }) => {
  const strokeColor = color || ConfitColors.gold;
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path
        d="M12 3L14.2 8.8L20 11L14.2 13.2L12 19L9.8 13.2L4 11L9.8 8.8L12 3Z"
        stroke={strokeColor}
        fill={isActive ? ConfitColors.gold : `${ConfitColors.gold}25`}
      />
      <path d="M19 3L19.8 5.2L22 6L19.8 6.8L19 9L18.2 6.8L16 6L18.2 5.2L19 3Z" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 3. AI Virtual Stylist Icon: Speech Bubble + Sparkle
export const StylistIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'AI Virtual Stylist' }) => {
  const strokeColor = color || ConfitColors.gold;
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path
        d="M20 12C20 7.58172 16.4183 4 12 4C7.58172 4 4 7.58172 4 12C4 13.8487 4.62723 15.551 5.68452 16.9067L4.5 20.5L8.35824 19.4678C9.47952 19.8136 10.7067 20 12 20C16.4183 20 20 16.4183 20 12Z"
        stroke={strokeColor}
        fill={isActive ? `${ConfitColors.gold}20` : 'none'}
      />
      {/* 4-point sparkle inside bubble */}
      <path d="M12 8L12.9 10.6L15.5 11.5L12.9 12.4L12 15L11.1 12.4L8.5 11.5L11.1 10.6L12 8Z" stroke={strokeColor} fill={ConfitColors.gold} />
    </IconWrapper>
  );
};

// 4. Outfit Builder Icon: Hanger with Plus Sign
export const OutfitBuilderIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Outfit Builder' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 4C10.8954 4 10 4.89543 10 6C10 7.10457 10.8954 8 12 8C13.1046 8 14 7.10457 14 6C14 5.3 13.6 4.7 13 4.3" stroke={strokeColor} />
      <path d="M12 8L3 14V17H21V14L12 8Z" stroke={strokeColor} fill={isActive ? `${ConfitColors.navy}15` : 'none'} />
      {/* Plus symbol in corner */}
      <path d="M19 6V10M17 8H21" stroke={ConfitColors.gold} strokeWidth="2.5" />
    </IconWrapper>
  );
};

// 5. Visual Search Icon: Camera + Magnifier Glass
export const VisualSearchIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Visual Search & Style Match' }) => {
  const strokeColor = color || ConfitColors.gold;
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M4 8H7L8.5 5.5H15.5L17 8H20C21.1 8 22 8.9 22 10V18C22 19.1 21.1 20 20 20H4C2.9 20 2 19.1 2 18V10C2 8.9 2.9 8 4 8Z" stroke={strokeColor} />
      <circle cx="11.5" cy="14" r="3.5" stroke={strokeColor} />
      <path d="M14 16.5L17.5 20" stroke={strokeColor} strokeWidth="2.5" />
    </IconWrapper>
  );
};

// 6. Trending Looks Icon: Flame
export const FlameIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Trending Looks' }) => {
  const strokeColor = color || ConfitColors.gold;
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path
        d="M12 2C10 6 7 8 7 12C7 15.3137 9.23858 18 12 18C14.7614 18 17 15.3137 17 12C17 10 16 8.5 15 7C14.5 9 13 10 12 10C11 10 10.5 9 11 8C11.5 7 12.5 5 12 2Z"
        stroke={strokeColor}
        fill={isActive ? ConfitColors.gold : `${ConfitColors.gold}20`}
      />
    </IconWrapper>
  );
};

// 7. Virtual Try-On Icon: Oval Mirror with Silhouette
export const TryOnIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, isAi = true, color, ariaLabel = 'Virtual Try-On' }) => {
  const strokeColor = color || (isAi ? ConfitColors.gold : ConfitColors.navy);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      {/* Oval Mirror Outline */}
      <ellipse cx="12" cy="11.5" rx="7.5" ry="9" stroke={strokeColor} fill={isActive ? `${ConfitColors.gold}25` : 'none'} />
      {/* Silhouette Head & Shoulders */}
      <circle cx="12" cy="9.5" r="2.2" stroke={strokeColor} fill={strokeColor} />
      <path d="M8.5 16.5C8.5 14.2 10.1 13 12 13C13.9 13 15.5 14.2 15.5 16.5" stroke={strokeColor} />
      {/* Stand base */}
      <path d="M9 21.5H15M12 20.5V21.5" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 8. No-Photo Fit Finder Icon: Ruler with Tick Marks
export const RulerIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'No-Photo Fit Finder' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M4 17L17 4C17.5 3.5 18.5 3.5 19 4L20 5C20.5 5.5 20.5 6.5 20 7L7 20C6.5 20.5 5.5 20.5 5 20L4 19C3.5 18.5 3.5 17.5 4 17Z" stroke={strokeColor} />
      <path d="M7 6.5L9 8.5M10.5 10L12.5 12M14 13.5L16 15.5M17.5 17L19.5 19" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 9. My Wardrobe Icon: Double Door Closet
export const WardrobeIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'My Wardrobe' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="4" y="3" width="16" height="17" rx="1.5" stroke={strokeColor} fill={isActive ? `${ConfitColors.navy}15` : 'none'} />
      <line x1="12" y1="3" x2="12" y2="20" stroke={strokeColor} />
      <circle cx="10" cy="11.5" r="0.8" fill={strokeColor} />
      <circle cx="14" cy="11.5" r="0.8" fill={strokeColor} />
      <path d="M6 20V22M18 20V22" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 10. My Looks / Saved Outfits: Hanger with Heart
export const SavedLooksIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'My Looks' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 4C10.9 4 10 4.9 10 6C10 7.1 10.9 8 12 8C13.1 8 14 7.1 14 6" stroke={strokeColor} />
      <path d="M12 8L4 13.5V16H20V13.5L12 8Z" stroke={strokeColor} fill={isActive ? `${ConfitColors.gold}20` : 'none'} />
      {/* Heart */}
      <path d="M12 18.5L9.5 16C8.5 15 8.5 13.5 9.5 12.5C10.5 11.5 12 12 12 12C12 12 13.5 11.5 14.5 12.5C15.5 13.5 15.5 15 14.5 16L12 18.5Z" stroke={ConfitColors.gold} fill={ConfitColors.gold} />
    </IconWrapper>
  );
};

// 11. Gap Analysis Icon: Dashed Square with Crosshair
export const GapAnalysisIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Wardrobe Gap Analysis' }) => {
  const strokeColor = color || ConfitColors.gold;
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M4 9V5C4 4.44772 4.44772 4 5 4H9" stroke={strokeColor} strokeWidth="2" strokeDasharray="3 2" />
      <path d="M15 4H19C19.5523 4 20 4.44772 20 5V9" stroke={strokeColor} strokeWidth="2" strokeDasharray="3 2" />
      <path d="M20 15V19C20 19.5523 19.5523 20 19 20H15" stroke={strokeColor} strokeWidth="2" strokeDasharray="3 2" />
      <path d="M9 20H5C4.44772 20 4 19.5523 4 19V15" stroke={strokeColor} strokeWidth="2" strokeDasharray="3 2" />
      {/* Central Search Plus */}
      <circle cx="12" cy="12" r="3.5" stroke={strokeColor} />
      <path d="M12 9.5V14.5M9.5 12H14.5" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 12. Duplicate Purchase Alert Icon: Overlapping Squares + Alert Dot
export const DuplicateAlertIcon: React.FC<IconProps> = ({ size = 24, className = '', color, ariaLabel = 'Duplicate Purchase Alert' }) => {
  const strokeColor = color || ConfitColors.gold;
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="4" y="4" width="10" height="10" rx="1.5" stroke={ConfitColors.grey} />
      <rect x="9" y="9" width="10" height="10" rx="1.5" stroke={strokeColor} fill={`${ConfitColors.gold}20`} />
      <circle cx="17.5" cy="6.5" r="2.5" fill="#EF4444" stroke="#FAF9F6" strokeWidth="1" />
    </IconWrapper>
  );
};

// 13. Shopping Bag / Cart Icon: Bag with Handles and Badge
export const BagIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, badge, color, ariaLabel = 'Shopping Cart & Checkout' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} badge={badge} ariaLabel={ariaLabel}>
      <path d="M6 8H18L19.5 20C19.5 20.6 19 21 18.4 21H5.6C5 21 4.5 20.6 4.5 20L6 8Z" stroke={strokeColor} fill={isActive ? `${ConfitColors.navy}15` : 'none'} />
      <path d="M9 10V6C9 4.34315 10.3431 3 12 3C13.6569 3 15 4.34315 15 6V10" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 14. Orders & Tracking Icon: Delivery Truck + Box
export const OrdersIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Orders & Tracking' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M3 5H14V17H3V5Z" stroke={strokeColor} fill={isActive ? `${ConfitColors.navy}15` : 'none'} />
      <path d="M14 8H18.5L21 12V17H14V8Z" stroke={strokeColor} />
      <circle cx="7" cy="18" r="2" stroke={strokeColor} />
      <circle cx="17.5" cy="18" r="2" stroke={strokeColor} />
      <path d="M6 10H11" stroke={ConfitColors.gold} />
    </IconWrapper>
  );
};

// 15. BOPIS / Store Pickup Icon: Map Pin with Storefront
export const BopisIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'BOPIS Store Pickup' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <path d="M12 2C8.13 2 5 5.13 5 9C5 14.25 12 22 12 22C12 22 19 14.25 19 9C19 5.13 15.87 2 12 2Z" stroke={strokeColor} fill={isActive ? `${ConfitColors.navy}15` : 'none'} />
      {/* Storefront inside pin */}
      <path d="M9 8H15V13H9V8Z" stroke={ConfitColors.gold} />
      <path d="M8 8L12 6L16 8" stroke={ConfitColors.gold} />
      <line x1="11" y1="13" x2="11" y2="10.5" stroke={ConfitColors.gold} />
    </IconWrapper>
  );
};

// 16. Notifications Bell Icon
export const BellIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, badge, color, ariaLabel = 'Notifications' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} badge={badge} ariaLabel={ariaLabel}>
      <path d="M18 8A6 6 0 0 0 6 8C6 15 3 17 3 17H21S18 15 18 8" stroke={strokeColor} fill={isActive ? `${ConfitColors.navy}15` : 'none'} />
      <path d="M13.73 21A2 2 0 0 1 10.27 21" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 17. Account / Profile User Circle Icon
export const UserIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Account & Profile' }) => {
  const strokeColor = color || (isActive ? ConfitColors.navy : ConfitColors.grey);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <circle cx="12" cy="12" r="9" stroke={strokeColor} fill={isActive ? `${ConfitColors.navy}15` : 'none'} />
      <circle cx="12" cy="9" r="3" stroke={strokeColor} />
      <path d="M6.5 18C7.5 15.5 9.5 14 12 14C14.5 14 16.5 15.5 17.5 18" stroke={strokeColor} />
    </IconWrapper>
  );
};

// 18. Brand Dashboard (B2B) Icon: Briefcase + Analytics Chart
export const BrandDashboardIcon: React.FC<IconProps> = ({ size = 24, className = '', isActive = false, color, ariaLabel = 'Brand Management Dashboard' }) => {
  const strokeColor = color || (isActive ? ConfitColors.gold : ConfitColors.navy);
  return (
    <IconWrapper size={size} className={className} ariaLabel={ariaLabel}>
      <rect x="3" y="7" width="18" height="14" rx="2" stroke={strokeColor} fill={isActive ? `${ConfitColors.gold}15` : 'none'} />
      <path d="M8 7V5C8 3.9 8.9 3 10 3H14C15.1 3 16 3.9 16 5V7" stroke={strokeColor} />
      {/* Upward mini-bars */}
      <line x1="7" y1="16" x2="7" y2="14" stroke={strokeColor} strokeWidth="2" />
      <line x1="11" y1="16" x2="11" y2="12" stroke={strokeColor} strokeWidth="2" />
      <line x1="15" y1="16" x2="15" y2="10" stroke={ConfitColors.gold} strokeWidth="2" />
    </IconWrapper>
  );
};
