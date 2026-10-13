import React, { forwardRef } from 'react';

export interface ShareCardItem {
  product_title: string;
  brand_name: string;
  category_name: string;
  price: number;
  image_url: string;
  color_hex: string;
  position: string;
}

export interface ShareCardProps {
  title: string;
  occasion?: string;
  items: ShareCardItem[];
  totalPrice: number;
  compatibilityScore?: number | null;
  currency?: string;
}

/**
 * C7 — the real, renderable share card in the Logo #3 white-first brand system.
 * `html-to-image` rasterizes this exact DOM node into a PNG.
 * Clean white background with brand charcoal typography and hairline dividers.
 */
export const ShareCard = forwardRef<HTMLDivElement, ShareCardProps>(function ShareCard(
  { title, occasion, items, totalPrice, compatibilityScore, currency = 'EGP' },
  ref
) {
  return (
    <div
      ref={ref}
      data-testid="outfit-share-card"
      style={{
        width: 600,
        padding: 32,
        background: '#FFFFFF',
        color: '#252729',
        border: '1px solid #E8E6E2',
        boxShadow: '0 4px 20px -4px rgba(37,39,41,0.08)',
        fontFamily: 'Inter, system-ui, sans-serif',
        borderRadius: 16,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ letterSpacing: 4, fontSize: 14, fontWeight: 700, color: '#252729' }}>CONFIT</span>
        {occasion ? <span style={{ fontSize: 13, color: '#595C63' }}>{occasion}</span> : null}
      </div>

      <h2 style={{ fontSize: 24, margin: '16px 0 4px', fontWeight: 700, color: '#252729', fontFamily: 'Playfair Display, Georgia, serif' }}>{title}</h2>
      <div style={{ fontSize: 13, color: '#595C63', marginBottom: 20 }}>
        {items.length} item{items.length === 1 ? '' : 's'}
        {typeof compatibilityScore === 'number' ? ` · Compatibility ${compatibilityScore}%` : ''}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
        {items.map((item, idx) => (
          <div
            key={`${item.product_title}-${idx}`}
            style={{
              background: '#F7F6F3',
              border: '1px solid #E8E6E2',
              borderRadius: 12,
              padding: 12,
              display: 'flex',
              gap: 12,
              alignItems: 'center',
            }}
          >
            <img
              src={item.image_url}
              alt={item.product_title}
              crossOrigin="anonymous"
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = 'none';
              }}
              style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 8, background: '#fff' }}
            />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, color: '#595C63' }}>{item.brand_name}</div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: '#252729',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {item.product_title}
              </div>
              <div style={{ fontSize: 13, marginTop: 2, fontWeight: 600, color: '#252729' }}>
                {currency} {item.price.toFixed(2)}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          marginTop: 20,
          paddingTop: 16,
          borderTop: '1px solid #E8E6E2',
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 15,
          color: '#252729',
        }}
      >
        <span style={{ color: '#595C63' }}>Total</span>
        <strong style={{ fontWeight: 700, color: '#252729' }}>
          {currency} {totalPrice.toFixed(2)}
        </strong>
      </div>
    </div>
  );
});
