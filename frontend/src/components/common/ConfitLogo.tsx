import React from 'react';
import { useTranslation } from 'react-i18next';

/**
 * CONFIT brand logo — "Individual Grid" (Logo #3, official identity).
 *
 * Geometry and colours mirror /public/brand/*.svg exactly (the SVG files are the
 * asset source of truth; keep both in sync). The wordmark is drawn as outline paths,
 * so it renders identically without any web-font dependency.
 *
 * Variants keep the historical API so every existing caller keeps working:
 *   - 'full'    symbol + wordmark + tagline
 *   - 'compact' symbol + wordmark
 *   - 'mark'    symbol only
 *
 * `theme="light"` means "placed on a dark surface": the charcoal quadrant and
 * the wordmark switch to the brand cream so the mark keeps its four-part
 * structure. The coloured quadrants stay exactly as specified.
 */

export const BRAND_COLORS = {
  coral: '#EF826D',
  lilac: '#A99AD6',
  mint: '#89B799',
  charcoal: '#242526',
  cream: '#FAF9F6',
} as const;

// Symbol — 100×100 grid, cells 44, gap 12
const SYMBOL_PATHS = {
  coral: 'M22 44H44V12Q44 0 32 0H22A22 22 0 0 0 22 44Z',
  lilac: 'M56 0H100V22A22 22 0 0 1 56 22Z',
  mint: 'M22 100H44V68Q44 56 32 56H22A22 22 0 0 0 22 100Z',
  charcoal: 'M78 56A22 22 0 1 1 78 100A22 22 0 1 1 78 56Z',
} as const;

// Wordmark — cap height 100, stroke weight 17, letter gap 12
const GLYPHS: Array<{ d: string; w: number }> = [
  { d: 'M85.8 19.2A48 50 0 1 0 85.8 80.8L72.4 70.3A31 33 0 1 1 72.4 29.7Z', w: 96 },
  { d: 'M0 50A50 50 0 1 0 100 50A50 50 0 1 0 0 50ZM17 50A33 33 0 1 1 83 50A33 33 0 1 1 17 50Z', w: 100 },
  { d: 'M0 0H22L63 60V0H80V100H58L17 40V100H0Z', w: 80 },
  { d: 'M0 0H66V17H17V42H58V59H17V100H0Z', w: 66 },
  { d: 'M0 0H17V100H0Z', w: 17 },
  { d: 'M0 0H70V17H43.5V100H26.5V17H0Z', w: 70 },
];
const LETTER_GAP = 12;
const WORDMARK_UNITS = GLYPHS.reduce((s, g) => s + g.w, 0) + LETTER_GAP * (GLYPHS.length - 1);
const CAP_SCALE = 0.52;   // wordmark cap height relative to the symbol
const SYMBOL_GAP = 22;    // symbol → wordmark gap, in symbol units
const RIGHT_PAD = 2;      // prevents the final T from touching the viewBox edge

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
  const { t } = useTranslation();
  const onDark = theme === 'light';

  const symbolPx = size === 'sm' ? 28 : size === 'lg' ? 44 : 36;
  const tagSize = size === 'sm' ? 'text-[8px]' : 'text-[9px]';

  const ink = onDark ? BRAND_COLORS.cream : BRAND_COLORS.charcoal;
  const charcoalQuadrant = onDark ? BRAND_COLORS.cream : BRAND_COLORS.charcoal;

  const showWordmark = variant !== 'mark';
  const wordmarkW = WORDMARK_UNITS * CAP_SCALE;
  const totalW = showWordmark ? 100 + SYMBOL_GAP + wordmarkW + RIGHT_PAD : 100;
  const wordmarkY = (100 - 100 * CAP_SCALE) / 2;

  let x = 0;
  const glyphs = GLYPHS.map((g, i) => {
    const el = <path key={i} transform={`translate(${x} 0)`} d={g.d} />;
    x += g.w + LETTER_GAP;
    return el;
  });

  // Height is driven by the symbol; width follows the viewBox so nothing distorts.
  const svgHeight = symbolPx;
  const svgWidth = (totalW / 100) * symbolPx;

  return (
    <div className={`inline-flex flex-col items-start select-none ${className}`}>
      <div className="inline-flex items-center">
        <svg
          width={svgWidth}
          height={svgHeight}
          viewBox={`0 0 ${totalW.toFixed(2)} 100`}
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="shrink-0"
          role="img"
          aria-label="CONFIT"
          focusable="false"
        >
          <path fill={BRAND_COLORS.coral} d={SYMBOL_PATHS.coral} />
          <path fill={BRAND_COLORS.lilac} d={SYMBOL_PATHS.lilac} />
          <path fill={BRAND_COLORS.mint} d={SYMBOL_PATHS.mint} />
          <path fill={charcoalQuadrant} d={SYMBOL_PATHS.charcoal} />
          {showWordmark && (
            <g transform={`translate(${100 + SYMBOL_GAP} ${wordmarkY.toFixed(2)}) scale(${CAP_SCALE})`} fill={ink}>
              {glyphs}
            </g>
          )}
        </svg>
      </div>

      {variant === 'full' && (
        <span
          className={`uppercase tracking-[0.25em] font-medium mt-1 ${onDark ? 'text-slate-300' : 'text-slate-600'} ${tagSize}`}
        >
          {t('brand.tagline')}
        </span>
      )}
    </div>
  );
};

export default ConfitLogo;
