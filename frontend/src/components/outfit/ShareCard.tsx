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
 * C7 — the real, renderable share card. `html-to-image` rasterizes this exact
 * DOM node into a PNG; there is no server-side card URL and none is claimed.
 * Product images that fail to load are hidden so a broken image never makes
 * it into the exported card.
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
        background: 'linear-gradient(160deg, #1B1F3B 0%, #2A2F55 100%)',
        color: '#F8F6F2',
        fontFamily: 'Georgia, serif',
        borderRadius: 16,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ letterSpacing: 4, fontSize: 14, opacity: 0.85 }}>CONFIT</span>
        {occasion ? <span style={{ fontSize: 13, opacity: 0.75 }}>{occasion}</span> : null}
      </div>

      <h2 style={{ fontSize: 28, margin: '16px 0 4px', fontWeight: 700 }}>{title}</h2>
      <div style={{ fontSize: 13, opacity: 0.8, marginBottom: 20 }}>
        {items.length} item{items.length === 1 ? '' : 's'}
        {typeof compatibilityScore === 'number' ? ` · Compatibility ${compatibilityScore}%` : ''}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
        {items.map((item, idx) => (
          <div
            key={`${item.product_title}-${idx}`}
            style={{
              background: 'rgba(255,255,255,0.06)',
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
              <div style={{ fontSize: 12, opacity: 0.7 }}>{item.brand_name}</div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {item.product_title}
              </div>
              <div style={{ fontSize: 13, marginTop: 2 }}>
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
          borderTop: '1px solid rgba(255,255,255,0.2)',
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 15,
        }}
      >
        <span style={{ opacity: 0.8 }}>Total</span>
        <strong>
          {currency} {totalPrice.toFixed(2)}
        </strong>
      </div>
    </div>
  );
});
