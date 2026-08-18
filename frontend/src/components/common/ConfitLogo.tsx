import React from 'react';

export interface ConfitLogoProps {
  className?: string;
  variant?: 'full' | 'compact' | 'mark';
  theme?: 'dark' | 'light';
  size?: 'sm' | 'md' | 'lg';
}

export const ConfitLogo: React.FC<ConfitLogoProps> = ({
  className = '',
  variant = 'compact',
  theme = 'dark',
  size = 'md',
}) => {
  const isLight = theme === 'light';

  const markSize = size === 'sm' ? 28 : size === 'lg' ? 44 : 36;
  const textSize = size === 'sm' ? 'text-lg' : size === 'lg' ? 'text-2xl' : 'text-xl';
  const tagSize = size === 'sm' ? 'text-[8px]' : 'text-[9px]';

  const primaryColor = isLight ? '#FFFFFF' : '#1B1F3B';
  const goldColor = '#C5A059';

  return (
    <div className={`inline-flex items-center gap-2.5 select-none ${className}`}>
      {/* Precision Interlocking C+F Fashion Monogram Mark */}
      <svg
        width={markSize}
        height={markSize}
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0 transition-transform duration-300 hover:scale-105"
        role="img"
        aria-label="CONFIT Brand Monogram"
      >
        {/* Luxury Background Tile */}
        <rect
          width="40"
          height="40"
          rx="10"
          fill={isLight ? '#1B1F3B' : '#0C0E1E'}
          className="shadow-sm"
        />

        {/* Outer Elegant Arc 'C' for Confidence */}
        <path
          d="M26 12C23.5 9.8 19.8 9.5 16.5 11.2C13.2 12.9 11 16.3 11 20C11 23.7 13.2 27.1 16.5 28.8C19.8 30.5 23.5 30.2 26 28"
          stroke={goldColor}
          strokeWidth="2.75"
          strokeLinecap="round"
        />

        {/* Inner Structural 'F' for Fit */}
        <path
          d="M18 15.5H27M18 20.5H24M18 15.5V26"
          stroke="#FFFFFF"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Precision Balance Dot */}
        <circle cx="28" cy="20.5" r="1.5" fill={goldColor} />
      </svg>

      {/* Typography Wordmark */}
      {variant !== 'mark' && (
        <div className="flex flex-col justify-center">
          <div className="flex items-center gap-1">
            <span
              className={`font-serif font-black tracking-[0.2em] leading-none ${textSize}`}
              style={{ color: primaryColor }}
            >
              CONFIT
            </span>
            <span
              className="w-1.5 h-1.5 rounded-full mb-0.5"
              style={{ backgroundColor: goldColor }}
            />
          </div>

          {variant === 'full' && (
            <span
              className={`uppercase tracking-[0.25em] font-semibold -mt-0.5 text-slate-400 ${tagSize}`}
            >
              Confidence + Fit
            </span>
          )}
        </div>
      )}
    </div>
  );
};
