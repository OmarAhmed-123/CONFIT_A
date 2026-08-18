# CONFIT — Master Frontend Specification & MVVM Architecture

**Document Version:** 1.0.0 (Production Frontend Engineering Guide)  
**Frontend Architecture:** Model–View–ViewModel (MVVM)  
**Core Frameworks & Tools:** React 18, TypeScript 5.6+, Vite 5, Tailwind CSS 3.4+, React Router 6, TanStack Query v5, Zustand 5, React Hook Form, Zod 3.23+, i18next, Framer Motion  
**Target Viewports:** Mobile Web (Thumb-Zone Ergonomics), Tablet (Responsive Grid), Desktop (1440px+ Mega-Menu Layout)  
**Localization:** 100% English & Arabic with Dynamic RTL Direction Mirroring (`dir="rtl"`) and Cairo Typography  

---

## 1. Executive Purpose & Quality Goals

The CONFIT frontend is a high-performance, accessible, and visually captivating fashion technology platform. The frontend bridges complex generative AI, 3D garment drape simulations, and multi-brand e-commerce into a smooth boutique shopping experience.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CONFIT FRONTEND MVVM PARADIGM                                    │
├─────────────────┬────────────────────────────────────────────────────────────────────────────────┤
│ LAYER           │ RESPONSIBILITY & IMPLEMENTATION CONTRACTS                                      │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Views**       │ Pure presentation JSX components (`src/views/*`). Binds to ViewModels, renders  │
│                 │ layout shells, listens for user gestures, and delegates all actions.            │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **ViewModels**  │ Custom hooks (`src/viewmodels/*`). Manages state transformations, validation,   │
│                 │ loading/error/empty state machines, mutations, and analytics emissions.        │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Models**      │ Strong TypeScript interfaces (`src/models/index.ts`). Data transfer contracts,   │
│                 │ UI state types, form schemas, and mapped entities.                             │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Services**    │ Typed API adapters (`src/services/apiServices.ts`). Bearer token injection,     │
│                 │ session management, request wrapping, and error envelope extraction.           │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Stores**      │ Global client stores (`src/stores/*`). Zustand stores for auth session state,   │
│                 │ cart badges, active modals, and locale/theme preferences.                      │
└─────────────────┴────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Complete Frontend Folder Architecture

```
frontend/
├── src/
│   ├── models/                          # Typed client domain interfaces
│   │   └── index.ts                     # User, Product, Outfit, TryOn, Wardrobe, Cart, Order, Brand
│   ├── services/                        # Typed API network adapters
│   │   ├── apiClient.ts                 # Fetch wrapper, session token & auth bearer header injection
│   │   └── apiServices.ts               # Endpoints for G1–G6 domains
│   ├── stores/                          # Zustand client-state stores
│   │   ├── authStore.ts                 # User authentication, tokens, RBAC roles
│   │   ├── cartStore.ts                 # Shopping bag, duplicate alert interceptor, quantities
│   │   └── uiStore.ts                   # Modals (Try-On, Ruler, Visual Search, Auth), Toast, Language
│   ├── viewmodels/                      # MVVM ViewModels isolating presentation logic
│   │   ├── useStylistViewModel.ts       # Conversational chat, speech simulation, outfit recommendations
│   │   ├── useTryOnViewModel.ts         # VTON diffusion rendering, avatar selection, ruler calculation
│   │   ├── useOutfitBuilderViewModel.ts # Mix & match canvas, live running budget tracker, compatibility
│   │   ├── useWardrobeViewModel.ts      # Closet items, category filtering, auto-tagging, gap analysis
│   │   ├── useCatalogViewModel.ts       # Product filtering, category selection, faceted search, sorting
│   │   └── useBrandViewModel.ts         # B2B telemetry, SKU inventory, CPC placement bidding
│   ├── components/
│   │   ├── icons/
│   │   │   └── ConfitIcons.tsx          # 18 CONFIT UI/UX specification vector icons
│   │   ├── navigation/                  # Primary application shells
│   │   │   ├── ConsumerNavbar.tsx       # Desktop mega-menu & 5-item mobile bottom nav
│   │   │   ├── BrandNavbar.tsx          # B2B Portal application shell & top header
│   │   │   └── LanguageSwitcher.tsx     # Instant EN/AR RTL toggle
│   │   ├── common/                      # Reusable UI primitives
│   │   │   └── CommonComponents.tsx     # Toast, Modal, FitScoreBadge, BNPLBadge, Loader, EmptyState
│   │   ├── stylist/
│   │   │   └── VirtualStylistDrawer.tsx # Conversational AI stylist drawer
│   │   ├── tryon/
│   │   │   ├── VirtualTryOnModal.tsx    # Side-by-side VTON drape renderer
│   │   │   ├── NoPhotoFitModal.tsx      # Anthropometric ruler fit calculator
│   │   │   └── VisualSearchModal.tsx    # Vision AI image search & attribute matcher
│   │   ├── wardrobe/
│   │   │   └── DuplicateAlertModal.tsx  # Add-to-cart wardrobe duplicate warning
│   │   └── commerce/
│   │       └── CartDrawer.tsx           # Multi-brand cart with BNPL split quote
│   ├── views/                           # Screen views bound to ViewModels
│   │   ├── consumer/
│   │   │   ├── HomeView.tsx             # Hero, 3 CTAs, Today's Picks, 4 Occasion tiles, Trending
│   │   │   ├── DiscoverView.tsx         # Catalog with category filters, search, sorting
│   │   │   ├── OutfitBuilderView.tsx    # Mix & match canvas with live budget tracker
│   │   │   ├── TryOnFitView.tsx         # Dedicated Try-On & Fit studio
│   │   │   ├── WardrobeView.tsx         # My Closet, My Looks, Gap Analysis
│   │   │   ├── ProductDetailView.tsx    # Product details, AI sizing, BOPIS stock
│   │   │   ├── CheckoutView.tsx         # Unified checkout with BNPL & BOPIS
│   │   │   ├── OrderTrackingView.tsx    # Real-time milestone status timeline
│   │   │   └── UserProfileView.tsx      # USP, 5-step quiz, encrypted body data, GDPR
│   │   ├── b2b/
│   │   │   ├── BrandDashboardView.tsx   # Return reduction telemetry & rankings
│   │   │   ├── BrandCatalogView.tsx     # SKU editor & stock synchronizer
│   │   │   ├── BrandInventoryView.tsx   # BOPIS store node statuses
│   │   │   ├── BrandAnalyticsView.tsx   # Try-on conversion funnel
│   │   │   ├── BrandPlacementsView.tsx  # Sponsored CPC bidding manager
│   │   │   └── AdminAnalyticsView.tsx   # Platform GMV & style heatmaps
│   │   └── auth/
│   │       └── AuthModal.tsx            # Login, register, demo 1-click personas
│   ├── layouts/
│   │   ├── ConsumerLayout.tsx           # Consumer storefront layout
│   │   └── BrandLayout.tsx              # B2B Brand & Admin portal layout
│   ├── router/
│   │   └── AppRoutes.tsx                # Client-side route tree
│   ├── i18n/
│   │   ├── en.json                      # English localization dictionary
│   │   ├── ar.json                      # Arabic localization dictionary
│   │   └── i18n.ts                      # i18next configuration & dynamic RTL handler
│   ├── styles/
│   │   └── index.css                    # Tailwind tokens, Cairo Arabic typography
│   ├── App.tsx                          # App root with TanStack Query provider
│   └── main.tsx                         # Entry point
```

---

## 3. Application Shells & Navigation Architecture

### 3.1 Strict Shell Separation
- **Consumer Shell (`src/layouts/ConsumerLayout.tsx`):**
  - Warm luxury design palette (Warm Cream `#FAF9F6`, Navy `#1B1F3B`, Gold `#B8935A`).
  - Desktop: Top navigation with task-oriented mega-menu + right utility cluster (Search, Bag badge, Account).
  - Mobile: Top bar for logo/account + 5-item bottom bar with elevated central **Try-On Action Button**.
  - Persistent Floating Action Button (FAB) for conversational AI Stylist.
- **Brand & Admin Shell (`src/layouts/BrandLayout.tsx`):**
  - Completely separate B2B application shell with dark-slate styling (`#0F172A`).
  - Top navigation tabs: Dashboard, Catalog & SKUs, BOPIS Inventory, Return-Reduction Analytics, Sponsored Placements, Platform Overview.
  - Zero consumer navigation mixing, eliminating B2B/B2C role confusion.

```
DESKTOP TOP NAVIGATION BAR
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [CONFIT LOGO]   Home   Style & Discover ▾   Try-On & Fit ▾   My Wardrobe ▾   Shop ▾   [🔍] [🛍️²] [👤 Layla]│
└─────────────────────────────┬─────────────────────────────────────────────────────────────────────────────┘
                              ▼ (Mega-Menu Dropdown)
                ┌──────────────────────────────────────────────────┐
                │ 💬 AI Virtual Stylist      (Conversational AI)   │
                │ ➕ Outfit Builder Canvas   (Mix & Match Outfits) │
                │ 📷 Visual Search           (Photo Style Match)   │
                │ 🔥 Trending Looks          (Curated Silhouettes) │
                └──────────────────────────────────────────────────┘

MOBILE BOTTOM NAVIGATION BAR (Thumb Zone Optimized)
┌───────────────────────────────────────────────────────────────────────────┐
│     [🏠]            [✨]             [ 🪞 ]            [🚪]          [🛍️²]    │
│     Home          Discover       Virtual Try-On     Wardrobe        Cart      │
│                                  (Raised Navy FAB)                        │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 4. UI/UX Design System & Token Specifications

### 4.1 Design Tokens (Tailwind Extension)
- **Colors:**
  - `confit-navy`: Primary brand anchor (`#1B1F3B`), Dark slate surface (`#0F172A`), Deep navy (`#13162C`).
  - `confit-gold`: AI & Luxury highlights (`#B8935A`), Light gold tint (`#FDF8EE`), Deep gold (`#9C7844`).
  - `confit-cream`: Warm luxury background (`#FAF9F6`).
  - `confit-muted`: Neutral inactive grey (`#777777`).
- **Typography:**
  - Latin Display: `Playfair Display`, serif.
  - Latin Body: `Inter`, -apple-system, sans-serif.
  - Arabic Display & Body: `Cairo`, `Tajawal`, `IBM Plex Sans Arabic`, system-ui, sans-serif.
- **Elevation & Radius:**
  - Modals & Drawers: `rounded-3xl` ($24\text{ px}$), `shadow-2xl`.
  - Cards & Modules: `rounded-2xl` ($16\text{ px}$), `shadow-sm` / `shadow-md`.
  - Buttons & Inputs: `rounded-xl` ($12\text{ px}$) or `rounded-full`.

---

## 5. Screen Specifications & ViewModels (MVVM)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND VIEW–VIEWMODEL MAPPING                                  │
├───────────────────────┬───────────────────────────────┬──────────────────────────────────────────┤
│ VIEW SCREEN           │ VIEWMODEL HOOK                │ MANAGED STATE & ACTIONS                  │
├───────────────────────┼───────────────────────────────┼──────────────────────────────────────────┤
│ `HomeView`            │ `useCatalogViewModel`         │ Today's picks, 3 CTAs, 4 occasion tiles  │
│ `DiscoverView`        │ `useCatalogViewModel`         │ Category filters, price sliders, sorting │
│ `OutfitBuilderView`   │ `useOutfitBuilderViewModel`   │ Multi-brand canvas, live budget tracker  │
│ `TryOnFitView`        │ `useTryOnViewModel`           │ VTON rendering, avatar models, ruler fit │
│ `WardrobeView`        │ `useWardrobeViewModel`        │ Closet items, auto-tagging, gap analysis │
│ `ProductDetailView`   │ `useTryOnViewModel` + Cart    │ Size charts, BOPIS stock check, Try-On   │
│ `CheckoutView`        │ `useCartStore` + Commerce     │ Home vs BOPIS, BNPL 4-split payments     │
│ `OrderTrackingView`   │ `commerceService`             │ Milestone stages, BOPIS digital QR code  │
│ `UserProfileView`     │ `profileService`              │ 5-step quiz wizard, Fernet biometrics    │
│ `BrandDashboardView`  │ `useBrandViewModel`           │ Return-reduction (-71.4%), outfit ROI    │
│ `BrandCatalogView`    │ `useBrandViewModel`           │ SKU stock overrides, BOPIS sync          │
│ `BrandPlacementsView` │ `useBrandViewModel`           │ CPC ad bidding, daily budget controls    │
│ `AdminAnalyticsView`  │ `useBrandViewModel`           │ Platform GMV, AI revenue attribution     │
└───────────────────────┴───────────────────────────────┴──────────────────────────────────────────┘
```

---

### 5.1 Virtual Stylist & Conversational AI (G2.1)
- **Component:** `src/components/stylist/VirtualStylistDrawer.tsx`
- **ViewModel:** `src/viewmodels/useStylistViewModel.ts`
- **Key Capabilities:**
  - Natural language input with voice recording simulation.
  - Intent parser extracting occasion, aesthetic, and budget limits.
  - Multi-brand outfit recommendation cards with color harmony scoring.
  - Direct 1-click **Add Complete Look to Bag** command.

### 5.2 Interactive Outfit Builder Canvas (G2.3)
- **View:** `src/views/consumer/OutfitBuilderView.tsx`
- **ViewModel:** `src/viewmodels/useOutfitBuilderViewModel.ts`
- **Key Capabilities:**
  - Interactive multi-slot canvas (Outerwear, Top, Bottom, Footwear).
  - **Live Running Budget Tracker Overlay:** Real-time calculation of running total vs. user USP target budget with visual *Within Budget* / *Exceeds Allocation* status pills.
  - Live algorithmic compatibility evaluation (Color harmony verdict & silhouette cohesion).
  - Outfit saving to *My Looks* and PNG card export.

### 5.3 Virtual Try-On Studio (VTON) & Ruler Fit (G3.1 & G3.2)
- **Modals:** `src/components/tryon/VirtualTryOnModal.tsx` & `NoPhotoFitModal.tsx`
- **ViewModel:** `src/viewmodels/useTryOnViewModel.ts`
- **Key Capabilities:**
  - Multi-ethnic 3D body avatar selector (Athletic M, Hourglass F, Curvy F, Tall M) and photo upload flow.
  - **Side-by-Side Comparison:** Garment Only vs. Rendered Garment on Silhouette.
  - Verified VTON certificate disclosure (`VTON-CERT-*`) and 24-hour privacy retention notice.
  - **No-Photo Fit Finder:** 100% privacy-friendly anthropometric ruler calculator computing recommended size, zone fit breakdown (chest, waist, shoulders, length), and brand pattern tendency analysis.

### 5.4 Smart Wardrobe, Gap Analysis & Duplicate Alert (G4)
- **View:** `src/views/consumer/WardrobeView.tsx`
- **Modal:** `src/components/wardrobe/DuplicateAlertModal.tsx`
- **ViewModel:** `src/viewmodels/useWardrobeViewModel.ts`
- **Key Capabilities:**
  - Digital closet filtered by category tabs (Tops, Bottoms, Outerwear, Footwear, Accessories) and wear frequency.
  - AI Image Auto-Tagger predicting category, subcategory, color hex, pattern, and occasions.
  - **Wardrobe Gap Analysis:** Diagnostic algorithm identifying missing essential wardrobe staples and mapping them directly to catalog items unlocking +3 to +5 new outfit combinations.
  - **Smart Duplicate Purchase Alert:** Real-time interceptor when adding items to cart, alerting users if they already own an aesthetically overlapping piece with side-by-side comparison and "Style What I Own First" affordance.

### 5.5 Multi-Brand Checkout, BNPL & BOPIS (G5)
- **View:** `src/views/consumer/CheckoutView.tsx`
- **Drawer:** `src/components/commerce/CartDrawer.tsx`
- **Key Capabilities:**
  - Unified multi-brand cart with size confirmations and live BNPL installment quotes.
  - Fulfillment Mode Switcher: **Home Delivery** vs. **BOPIS Store Pickup** with physical boutique selector.
  - Payment Gateways: Tabby / Tamara 4-installment zero-interest split, Card, Apple Pay, and COD.
  - Real-Time Order Tracking timeline with carrier tracking numbers and BOPIS digital pickup codes (`PICKUP-*`).

### 5.6 B2B Brand Command Center & Admin Telemetry (G6)
- **Views:** `src/views/b2b/BrandDashboardView.tsx`, `BrandCatalogView.tsx`, `BrandPlacementsView.tsx`, `AdminAnalyticsView.tsx`
- **ViewModel:** `src/viewmodels/useBrandViewModel.ts`
- **Key Capabilities:**
  - **Return Reduction Telemetry:** Side-by-side visualization proving a **71.4% reduction in returns** for VTON-assisted purchases (8% post-VTON vs 28% pre-VTON benchmark).
  - Outfit Appearance Rankings ("Most Styled Items") measuring stylist ROI.
  - Real-time SKU stock editor syncing warehouse inventory with physical store BOPIS availability.
  - Sponsored Placement ad bidding manager for featured AI Stylist and Trending Hero slots with CPC bids and daily budgets.
  - Platform Admin overview detailing GMV, revenue attribution breakdown, and regional style heatmaps.

---

## 6. Internationalization & Dynamic RTL Layout Mirroring

The frontend incorporates full bilingual support (`en` and `ar`) via `i18next`:
- **Document Direction:** Toggling language invokes `setAppLanguage('ar')`, updating `document.documentElement.setAttribute('dir', 'rtl')`.
- **Layout Mirroring:** Flexbox and grid directions automatically mirror.
- **Typography Swap:** Body font dynamically adds `font-arabic` (Cairo / Tajawal) with serif headings mapped to Arabic calligraphic display fonts.

```typescript
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

---

## 7. Frontend Security & Correctness Rules

1. **Zero Client Secret Exposure:** No third-party API keys, OpenAI tokens, or Fernet cipher secrets exist in client bundles. All requests route to the backend proxy `/api/v1/*`.
2. **Session Persistence:** Authenticated tokens (`access_token`, `refresh_token`) and persistent guest session tokens (`X-Session-Token`) are managed through `src/services/apiClient.ts`.
3. **Form Validation:** All inputs across onboarding quizzes, measurements, checkout, and B2B SKU updates are strictly validated client-side with Zod and React Hook Form.

---

## 8. Verification & Deliverable Assets

The complete frontend specification document has been saved to:  
📁 `/home/user/docs/CONFIT_Frontend_Master_Specification.md` (and presented in the interactive viewer).
