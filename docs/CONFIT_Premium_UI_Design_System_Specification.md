# CONFIT — Premium UI Design System Specification

**Document Version:** 1.0.0 (Design System & Frontend Visual Architecture)  
**Target Positioning:** Luxury Fashion-Tech Platform for Affluent Multi-Brand Shoppers & Discerning Fashion Houses  
**Core Frameworks:** React 18, TypeScript, Tailwind CSS 3.4+, Framer Motion, i18next, Lucide Vector Iconography  
**Visual Direction:** Realistic, Modern, Premium, Editorial, Commercially Credible, and Accessible (WCAG 2.1 AA)  

---

## 1. Executive Design System Philosophy

CONFIT is designed as a **luxury fashion-tech editorial commerce experience**. The visual interface is built upon the following principles:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                CONFIT DESIGN SYSTEM CORE PILLARS                                 │
├─────────────────┬─────────────────┬─────────────────┬─────────────────┬──────────────────────────┤
│     CLARITY     │    RESTRAINT    │    HIERARCHY    │     POLISH      │      ACCESSIBILITY       │
│  - No clutter   │  - Selective    │  - High-contrast│  - Glassmorphic │  - 44x44px touch targets │
│  - Clear states │    Champagne    │    serif titles │    subtle frost │  - 4.5:1 text contrast   │
│  - Active tags  │    Gold accents │  - Clean body   │  - 0.5px borders│  - Dynamic RTL engine    │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┴──────────────────────────┘
```

### Visual Standards:
- **No Cartoon Artifacts:** Avoid overly saturated candy gradients, oversized playful borders, childish 3D stickers, or emoji clutter.
- **Restrained Color Palette:** Deep Midnight Navy (`#0C0E1E`), Classic Tailored Navy (`#1B1F3B`), Champagne Gold (`#C5A059`), and Alabaster Cream (`#FAF9F6`).
- **Editorial Typography Scale:** `Playfair Display` serif headlines, `Inter` body text, and `Cairo` / `Tajawal` Arabic font stacks.

---

## 2. Token Architecture (Tailwind CSS Configuration)

```javascript
// tailwind.config.js Design Tokens
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        confit: {
          navy: {
            DEFAULT: '#1B1F3B',   // Primary brand tone
            surface: '#0C0E1E',   // Dark luxury surface & B2B background
            dark: '#13162C',      // Deep indigo backdrop
            subtle: '#2A3C78',    // Active accent tone
          },
          gold: {
            DEFAULT: '#C5A059',   // Primary Champagne Gold accent
            light: '#FDF8EE',     // Subtle AI highlight background
            dark: '#A37E44',      // Hover & active gold
            deep: '#7E5E33',      // Contrast gold for dark mode
          },
          cream: '#FAF9F6',       // Alabaster background canvas
          slate: {
            border: '#E2E8F0',    // Delicate card border
            muted: '#64748B',     // Metadata text
            subtle: '#777777',    // Inactive icon stroke
          }
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['Playfair Display', 'Georgia', 'serif'],
        arabic: ['Cairo', 'Tajawal', 'IBM Plex Sans Arabic', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        '2xs': '0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'xs': '0 1px 3px 0 rgba(0, 0, 0, 0.05)',
        'luxury': '0 10px 30px -10px rgba(12, 14, 30, 0.08)',
        'glow': '0 0 20px -5px rgba(197, 160, 89, 0.25)',
      },
      borderRadius: {
        '3xl': '24px',
        '2xl': '16px',
        'xl': '12px',
      }
    }
  }
}
```

---

## 3. Brand Identity & Vector Logo System

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CONFIT BRAND IDENTITY SYSTEM                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│       [ 𝓒 + 𝓕 ]  C O N F I T •                                                                   │
│       ──────────────────────                                                                     │
│       CONFIDENCE + FIT                                                                           │
│                                                                                                  │
│  - Architectural Monogram: Interlocking C (Confidence) + F (Fit) in Champagne Gold (#C5A059)     │
│  - Wordmark Typography: High-contrast luxury serif with refined letter-spacing                   │
│  - Brand Color Palette: Deep Midnight (#0C0E1E), Classic Indigo (#1B1F3B), Alabaster (#FAF9F6)   │
│  - Dynamic RTL Mirroring: Full English/Arabic support with Cairo typography                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Logo Variants (`src/components/common/ConfitLogo.tsx`):
1. **`full` Variant:** Monogram mark + `CONFIT` serif wordmark + `CONFIDENCE + FIT` uppercase subtitle.
2. **`compact` Variant:** Monogram mark + `CONFIT` serif wordmark (used in Top Navigation & Auth Headers).
3. **`mark` Variant:** Standalone $40 \times 40\text{ px}$ interlocking C+F monogram (used in Mobile App Headers, Favicons, and Splash Screens).
4. **Themes:** `light` (on dark/navy backgrounds) and `dark` (on light/cream backgrounds).

---

## 4. Component Design System & States

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               COMPONENT DESIGN SYSTEM MATRIX                                     │
├───────────────────┬───────────────────────────────────┬──────────────────────────────────────────┤
│ COMPONENT         │ VISUAL TREATMENT & RADII          │ INTERACTION & ACCESSIBILITY STATES       │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ **Buttons**       │ `rounded-xl`, `px-5 py-3`,        │ Hover: scale-102, Active: scale-98,      │
│                   │ `#1B1F3B` / `#C5A059`             │ Focus: gold 2px ring, Disabled: op-40.   │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ **Product Cards** │ `rounded-3xl`, `bg-white`,        │ Image scale on hover, inline Try-On      │
│                   │ `border-slate-200/80`, `p-3.5`    │ quick button, AI Fit Score badge top-left│
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ **Badges & Pills**│ `rounded-full`, `px-3 py-1`,      │ Compact, subtle gold border (#C5A059/30),│
│                   │ `bg-[#FDF8EE]`, `#A37E44`         │ leading sparkle vector icon.             │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ **Modals/Drawers**│ `rounded-3xl`, `shadow-2xl`,      │ Backdrop blur `bg-slate-950/75`,         │
│                   │ `bg-white`, `border-slate-200`    │ smooth slide-in entry animation.         │
├───────────────────┼───────────────────────────────────┼──────────────────────────────────────────┤
│ **Form Inputs**   │ `rounded-xl`, `px-4 py-2.5`,      │ Focus: border `#C5A059`, clear labels,   │
│                   │ `border-slate-200`, `bg-white`    │ inline field validation messages.        │
└───────────────────┴───────────────────────────────────┴──────────────────────────────────────────┘
```

---

## 5. Screen-by-Screen Premium UI Standards

### 5.1 Home Dashboard (`HomeView.tsx`)
- High-contrast editorial hero banner with generous padding (`p-8 sm:p-20`).
- 3 Clear Quick Action CTAs: *Build an Outfit*, *Virtual Try-On*, *Find My Style*.
- 4 Occasion Shortcut tiles featuring atmospheric fashion photography (*Work*, *Party*, *Wedding*, *Casual*).
- Refined *Today's Style Picks* side-by-side outfit cards with multi-brand SKU tags.

### 5.2 Product Detail Page (`ProductDetailView.tsx`)
- Editorial media gallery with thumbnail strip selector.
- AI Fit Score badge prominently anchored at the top of the buying box.
- Interactive Size selector with real-time BOPIS store stock check dropdown.
- Floating Virtual Try-On launcher button with frosted glassmorphism.

### 5.3 Interactive Outfit Builder (`OutfitBuilderView.tsx`)
- 4-slot silhouette canvas (`outerwear`, `top`, `bottom`, `footwear`).
- **Live Running Budget Tracker Overlay:** Real-time running total calculation compared against user target budget with visual status indicators (*Within Budget* / *Exceeds Allocation*).
- Algorithmic Silhouette Compatibility Rating badge ($0\text{--}100\%$).

### 5.4 Virtual Try-On Studio (`VirtualTryOnModal.tsx` & `NoPhotoFitModal.tsx`)
- Silhouette Avatar picker (*Athletic M*, *Hourglass F*, *Curvy F*, *Tall Structured M*).
- Side-by-Side comparative drape output (Item Alone vs. Item on User).
- Signed VTON audit hash watermark (`VTON-CERT-*`) and 24-hour privacy purge notice.
- Minimalist No-Photo Fit Finder ruler sliders with zone-by-zone contour breakdowns.

### 5.5 Checkout & Payments (`CheckoutView.tsx`)
- Step-by-step layout: 1. Fulfillment Mode (Delivery vs. BOPIS) ──► 2. Address Details ──► 3. Payment Method.
- "Browse-First, Auth-at-Purchase" inline account gate for guest shoppers.
- Tabby / Tamara 4-installment zero-interest split schedule breakdown.

### 5.6 B2B Brand Partner Hub (`BrandDashboardView.tsx` to `AdminAnalyticsView.tsx`)
- Distinct dark-slate aesthetic (`#0C0E1E`) tailored for operational data density.
- Return-Reduction comparative metric cards (**71.4% reduction in returns**).
- Real-time SKU stock editor and self-serve CPC placement ad bidding manager.

---

## 6. Bilingual & Dynamic RTL Mirroring Engine

```typescript
// Dynamic Document Direction Flip in src/i18n/i18n.ts
export const setAppLanguage = (lang: 'en' | 'ar') => {
  i18n.changeLanguage(lang);
  localStorage.setItem('confit_lang', lang);
  const dir = lang === 'ar' ? 'rtl' : 'ltr';
  document.documentElement.setAttribute('dir', dir);
  document.documentElement.setAttribute('lang', lang);
  if (lang === 'ar') {
    document.body.classList.add('font-arabic');
  } else {
    document.body.classList.remove('font-arabic');
  }
};
```

- Arabic viewports automatically mirror horizontal layouts, icon placements, and margin offsets.
- Typography swaps seamlessly to `Cairo` / `Tajawal` font families with calligraphic serif hierarchy.

---

## 7. Deliverable Assets

The complete Premium UI Design System specification document has been saved to:  
📁 `/home/user/docs/CONFIT_Premium_UI_Design_System_Specification.md` (and presented in the interactive viewer).
