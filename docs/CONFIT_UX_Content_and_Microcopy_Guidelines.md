# CONFIT — UX Content & Microcopy Master Guidelines

**Document Version:** 1.0.0 (Editorial & Interface Copy Standard)  
**Tone of Voice:** Refined, Calm, Confident, Modern, Fashion-Commerce Credible, and Trustworthy  
**Bilingual Strategy:** Authentic, natural English and Arabic (avoiding awkward literal translations or stiff formality)  
**Applicability:** Consumer Storefront, AI Styling Interactions, Virtual Try-On Disclosures, Late-Auth Purchase Gate, Checkout, BOPIS Notifications, and B2B Operations  

---

## 1. Brand Tone of Voice & UX Principles

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CONFIT BRAND VOICE SPECTRUM                                    │
├────────────────────────────────────────────────────────┬─────────────────────────────────────────┤
│ WHAT CONFIT SOUNDS LIKE                                │ WHAT CONFIT NEVER SOUNDS LIKE           │
├────────────────────────────────────────────────────────┼─────────────────────────────────────────┤
│ - "Find a look that fits the occasion."                │ - "Magic fit experience!!!"             │
│ - "See a preview before you decide."                   │ - "Your dream AI closet companion"      │
│ - "Prefer not to upload a photo? Use size guidance."   │ - "This will definitely look perfect"   │
│ - "Sign in to continue to checkout."                   │ - "Buy now with futuristic algorithms"  │
│ - "Pickup ready at selected boutiques."                │ - "Guaranteed 100% flawless body match" │
└────────────────────────────────────────────────────────┴─────────────────────────────────────────┘
```

### 1.1 Core UX Writing Principles
1. **Direct & Direct-to-Value:** Keep headers and microcopy concise, active, and immediate.
2. **Honest Probabilistic Framing:** Avoid absolute certainty claims (e.g. *"Results may vary based on image quality and garment drape"* instead of *"Flawless fit guaranteed"*).
3. **Respect Privacy Transparently:** Explain why data or authentication is requested in calm, plain language.
4. **Restrained Elegance:** Luxury fashion-tech is expressed through confident simplicity and deliberate whitespace, not hyperbolic buzzwords.
5. **Clear Financial & Checkout Rules:** Payment terms, installment schedules, shipping fees, and return conditions must be unmistakable.

---

## 2. "Browse-First, Auth-at-Checkout" Microcopy Standard

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                GUEST EXPLORATION vs AUTH GATEWAY                                 │
├────────────────────────────────────────────────────────┬─────────────────────────────────────────┤
│ OPEN GUEST EXPLORATION (No Login Required)             │ AUTHENTICATED PURCHASE BOUNDARY         │
├────────────────────────────────────────────────────────┼─────────────────────────────────────────┤
│ - Home Dashboard & Today's Style Picks                 │ - Checkout Confirmation (`/checkout`)   │
│ - Multi-Brand Catalog Discovery & Filtering            │ - Payment Submission & BNPL Splits      │
│ - Product Detail Pages (PDP), Fit Scores & Sizing      │ - Order Creation & Inventory Deduction  │
│ - Interactive Outfit Builder Canvas & Budget Tracker   │ - Permanent Look Saving (`/my-looks`)   │
│ - Virtual Try-On Studio (Session-based) & Ruler Fit    │ - Real-Time Order Tracking & Returns    │
└────────────────────────────────────────────────────────┴─────────────────────────────────────────┘
```

### 2.1 Purchase Boundary Interface Copy
- **Header:** *"Sign in to continue to checkout"* / *"Create an account to complete your purchase"*
- **Exploratory Assurance:** *"You can browse freely. To secure items, activate real-time tracking, and manage returns, please sign in or create an account."*
- **State Preservation Message:** *"We’ll return you right here to checkout after sign-in with your bag and selections intact."*

---

## 3. Market-Specific Payment & Wallet Copy Standards

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 LOCALIZED PAYMENT COPY MATRIX                                    │
├───────────────────────┬───────────────────────────────┬──────────────────────────────────────────┤
│ OPERATING MARKET      │ METHOD LABELS                 │ SUPPORTING COPY & TRANSPARENCY           │
├───────────────────────┼───────────────────────────────┼──────────────────────────────────────────┤
│ **Egypt (EG / EGP)**  │ - Credit or Debit Card        │ - "Visa / Mastercard with 3D Secure"     │
│                       │ - Digital Mobile Wallets      │ - "Vodafone Cash, Orange Cash, Etisalat" │
│                       │ - Buy Now, Pay Later          │ - "Split in 4 interest-free payments"    │
│                       │ - Cash on Delivery (COD)      │ - "Pay in cash at your doorstep"         │
├───────────────────────┼───────────────────────────────┼──────────────────────────────────────────┤
│ **UAE & Gulf (GCC)**  │ - Credit / Debit Card         │ - "Visa, Mastercard, American Express"   │
│                       │ - Tabby / Tamara 0% BNPL      │ - "4 interest-free monthly installments" │
│                       │ - Apple Pay / Google Pay      │ - "Instant biometric 1-tap checkout"     │
│                       │ - Boutique Store Pickup       │ - "Pay online, collect free in 2 hours"  │
└───────────────────────┴───────────────────────────────┴──────────────────────────────────────────┘
```

### 3.1 InstaPay-Specific Honesty Rule
- **Standard:** Do not display direct "InstaPay" buttons unless backed by an active, operational bank-to-bank or PSP integration rail.
- **Copy:** In sandbox/demo environments, display compliant hosted PSP bridge descriptions without making unverified direct-clearing claims.

---

## 4. Feature-by-Feature Microcopy Inventory

### 4.1 Conversational AI Virtual Stylist
- **Prompt Placeholder:** *"Tell us the occasion, your budget, or the look you want (e.g. 'Smart casual dinner under $350')..."*
- **Speech Status:** *"Listening to your style vision..."* ──► *"Composing curated ensemble..."*
- **Recommendation Header:** *"Curated Look for [Occasion]"*
- **Buttons:** *"Add Complete Look to Bag"* · *"Open in Canvas"* · *"Swap Item"*

### 4.2 Virtual Try-On Studio (VTON)
- **Primary CTA:** *"Launch Virtual Try-On"*
- **Processing Status:** *"Segmenting fabric drape and matching proportions..."*
- **Side-by-Side Labels:** Left: *"Flat Garment"* · Right: *"Rendered on Silhouette"*
- **AI Disclosure Watermark:** *"AI Synthesized Garment Fit — Certified CONFIT VTON Engine v2.4 (Privacy Protected)"*
- **Privacy Notice:** *"🔒 Privacy Protected: Photos are processed in-session and automatically purged after 24 hours unless permanent storage is explicitly approved."*

### 4.3 No-Photo Fit Finder (The Ruler Engine)
- **Header:** *"No-Photo Size Guide"*
- **Support Copy:** *"Prefer not to upload a photo? Get a size recommendation and zone breakdown based purely on measurements."*
- **Fit Breakdown Output:** *"Optimal shoulder seam alignment · Relaxed drape at waist · Hits precisely at mid-hip"*
- **Return Risk Indicator:** *"Low Return Risk — Estimated <3.2% size return probability"*

### 4.4 Smart Wardrobe & Smart Reuse
- **Section Title:** *"Your Smart Wardrobe"*
- **Core Philosophy CTA:** *"Shop your wardrobe first"*
- **Duplicate Alert Modal:** *"You already own a similar piece in your closet. Would you like to style what you own first or proceed with this purchase?"*
- **Action Buttons:** *"Style What I Own First"* vs. *"Proceed to Bag Anyway"*
- **Gap Analysis Header:** *"Wardrobe Gap Analysis"*
- **Gap Insight Copy:** *"You have structured blazers and shirts, but lack tailored neutral trousers to complete formal and smart casual silhouettes. Adding this piece unlocks +4 new outfits."*

### 4.5 B2B Brand Partner Portal
- **Dashboard Title:** *"Brand Partner Command Center"*
- **Telemetry Labels:** *"Catalog Impressions"* · *"Virtual Try-Ons Run"* · *"Try-On Conversion Rate"* · *"Return Rate (Pre-VTON vs Post-VTON)"*
- **Return Impact Card:** *"71.4% Return Reduction — Saving an estimated $42,800 in quarterly restocking logistics"*
- **Placements Bidding:** *"Sponsored CPC Slot Bidding — Daily Budget & CPC Allocation"*

---

## 5. Bilingual Localization & Tone Harmony (English & Arabic)

| English UI Copy | Arabic UI Copy (طبيعية وراقية وغير حرفية) |
| :--- | :--- |
| **Where Style Meets Your Character in Every Moment** | **حيث تلتقي الأناقة مع شخصيتك في كل لحظة** |
| **Build an Outfit** | **صمم إطلالة متكاملة** |
| **Virtual Try-On** | **القياس الافتراضي** |
| **No-Photo Fit Finder** | **محدد المقاس بدون صور** |
| **Shop your wardrobe first** | **استثمر ما تملكه في خزانتك أولاً** |
| **Smart Duplicate Alert** | **تنبيه القطعة المشابهة في خزانك** |
| **Sign in to continue to checkout** | **سجّل الدخول للمتابعة لإتمام الطلب** |
| **Boutique Pickup (BOPIS) — Ready in 2h** | **استلام فوري من المتجر — جاهز خلال ساعتين** |
| **Split in 4 interest-free payments** | **قسّم على 4 دفعات بدون أي فوائد** |

---

## 6. Deliverable Assets

The complete UX Content & Microcopy Guidelines document has been compiled and saved to:  
📁 `/home/user/docs/CONFIT_UX_Content_and_Microcopy_Guidelines.md` (and presented in the interactive viewer).
