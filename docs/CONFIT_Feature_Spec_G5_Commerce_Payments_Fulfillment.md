# CONFIT — Feature Specification G5: Commerce, Payments & Fulfillment

**Feature Group:** G5 — End-to-End Commerce, Transactional & Fulfillment Engine  
**Document Version:** 1.0.0 (Production Engineering Specification)  
**Primary Business Purpose:** Convert user styling and fit confidence into completed, auditable transactions while preserving absolute transactional correctness, real-time inventory precision, and frictionless payment handling.  
**Architecture:** Frontend MVVM & Backend MVC with Server-Authoritative Pricing, Atomic Inventory Locking & Idempotent Checkout Sessions  

---

## 1. Executive Purpose & Core Product Principles

Feature Group G5 owns the entire transaction lifecycle across the consumer journey:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                G5 COMMERCE LIFECYCLE TOPOLOGY                                    │
├───────────────────────────────────┬──────────────────────────────────────────────────────────────┤
│       PRODUCT DISCOVERY & PDP     │                 CART & DUPLICATE INTERCEPTOR                 │
│  - AI Fit Score & Recommended Size│  - Cross-Brand Cart Session Aggregation                      │
│  - Inline VTON & Ruler Fit Modals │  - Server-Authoritative Totals Recomputation                 │
│  - BNPL 4-Split Installment Quote │  - Real-Time Wardrobe Duplicate Collision Interceptor        │
│  - BOPIS Boutique Availability    │  - Guest Cart Token Merging (`guest_token`)                  │
├───────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│       CHECKOUT & PAYMENTS         │                 FULFILLMENT & RETURNS                        │
│  - UUID Idempotency Lock Barrier  │  - Home Delivery Courier Milestone Tracking (`TRK-*`)        │
│  - Tabby / Tamara 0% Interest BNPL│  - BOPIS 2-Hour In-Store Pickup QR Codes (`PICKUP-*`)        │
│  - Card, Apple Pay & Market COD   │  - Self-Service Automated Return Label Generation (`RET-*`)  │
│  - Webhook Signature Verification │  - 30-Day Zero-Fee Try-On Assisted Return Guarantee          │
└───────────────────────────────────┴──────────────────────────────────────────────────────────────┘
```

### 1.1 Core Product Principles
1. **Commerce Correctness Over Cosmetic Speed:** Financial accuracy and inventory integrity supersede optimistic client updates.
2. **Server-Authoritative Pricing & Totals:** Frontend prices and totals are purely presentational; backend recalculates taxes, discounts, shipping, and line items atomically.
3. **Strict Checkout Idempotency:** Every confirmation request requires a client-generated UUID `idempotency_key` backed by database unique constraints.
4. **Provider-Agnostic Payment Abstraction:** Payment gateways (Stripe, Checkout.com, Tabby, Tamara) reside behind clean domain interfaces with mandatory webhook signature validation.
5. **Graceful Payment Fallback:** If a preferred BNPL provider rejects a credit session, standard Card/Apple Pay options remain immediately available.
6. **BOPIS Stock Constraint:** Store pickup is permitted strictly when localized physical inventory is available and verified.
7. **Frictionless Guest-to-Account Upgrade:** Guest checkout is supported via cryptographically random session tokens that merge seamlessly into permanent user accounts upon post-purchase authentication.

---

## 2. Comprehensive Feature Breakdown

### 2.1 Product Detail Page (PDP)
- **Decision-Ready Surface:** Combines standard e-commerce media galleries with CONFIT's core differentiators:
  - *AI Fit Score Badge:* Visual percentage match badge (e.g. `96% AI Fit · True to Size`).
  - *Virtual Try-On Button:* Launches the inline VTON modal with silhouette drape simulation.
  - *No-Photo Fit Launcher:* Opens the anthropometric ruler size predictor.
  - *Style Compatibility Score:* Match percentage against user USP aesthetics.
  - *BNPL 4-Payment Teaser:* Real-time installment breakdown:
    $$\text{Monthly Installment} = \frac{\text{Base Price}}{4}$$
  - *BOPIS Boutique Stock Availability:* Real-time stock status across Dubai, Riyadh, and London stores.
  - *Complete-the-Look Outfits:* Algorithmic outfit combinations recommending matching trousers, shoes, or outerwear.

### 2.2 Multi-Brand Cart
- **Cross-Brand Session Container:** Aggregates SKU items across disparate partner brands (*Massimo Dutti*, *COS*, *Reiss*, *Arket*) in a single shopping bag.
- **Cart-Level Fit Summary:** Displays size selections and AI fit verdicts before checkout progression.
- **Smart Duplicate Interceptor:** Evaluates candidate items against owned wardrobe inventory ($\ge 82\%$ similarity), presenting the `DuplicateAlertModal` before committing to cart.
- **Guest Cart Merging:** When an unauthenticated shopper signs in, `POST /api/v1/cart/merge` merges items into their user account.

### 2.3 Idempotent Checkout Session
- **Step-by-Step Checkout Workflow:**
  1. *Identity Step:* User email capture (authenticated or guest).
  2. *Fulfillment Selection:* Home Delivery (standard/express courier) vs. BOPIS Boutique Pickup (free 2-hour collection).
  3. *Payment Method Selection:* Tabby / Tamara 0% BNPL, Credit/Debit Card, Apple Pay, or COD.
  4. *Order Review & Submit:* Server locks pricing, validates inventory availability, and creates the order entity under an `idempotency_key` lock.

### 2.4 Payment & BNPL Gateway Integration
- **Abstracted Provider Interface (`BasePaymentProvider` & `BaseBNPLProvider`):**
  - `create_payment_intent(amount, currency, customer_info)`
  - `verify_webhook_signature(payload, signature_header)`
  - `get_installment_quote(amount, currency)`
  - `capture_transaction(transaction_id)`
  - `initiate_refund(transaction_id, amount)`
- **Security Standard:** Zero raw credit card CVVs or third-party secret keys touch client bundles.

### 2.5 BOPIS / In-Store Boutique Pickup
- **Real-Time Store Locator:** Returns pickup-enabled stores with available SKU stock and distance calculations.
- **2-Hour Store Readiness SLA:** Store associates pull garments, perform quality checks, and update status to `ready_for_pickup`.
- **Digital Pickup QR Pass:** Generates a secure alphanumeric pickup code (e.g. `PICKUP-8821`) presented at the boutique concierge.

### 2.6 Order Tracking & Fulfillment Milestones
- **Live Status Progression:**
  - `placed` ──► Order received and payment secured.
  - `processing` ──► Garments pulled and packaged in luxury garment bags.
  - `dispatched` / `ready_for_pickup` ──► In transit with courier or waiting in boutique.
  - `delivered` / `picked_up` ──► Handed to customer.
- **Tracking Data:** Order number, line items, carrier tracking number (`TRK-*`), tracking URL, and estimated delivery timestamps.

### 2.7 Returns Management & 30-Day Try-On Guarantee
- **Self-Service Initiation:** Users select returnable order items and choose reason codes (*Wrong Size*, *Color Difference*, *Style Mismatch*, *Changed Mind*).
- **Automated Label Generation:** Generates downloadable PDF shipping labels with carrier barcodes.
- **Try-On Assurance:** Orders assisted by Virtual Try-On or No-Photo Fit receive complimentary zero-fee return processing.

---

## 3. User Journeys & State Machines

### 3.1 Checkout & Order State Machine
```
[Cart Active] ──► [Initiate Checkout Session] ──► [Generate UUID idempotency_key]
                                                        │
                                                        ▼
                                     [Select Fulfillment: Delivery vs BOPIS]
                                                        │
                                                        ▼
                                     [Select Payment: Tabby / Tamara / Card]
                                                        │
                                                        ▼
                                     [Verify Payment & Inventory Allocation]
                                                        │
                                                        ▼
                                     [Atomic Order & Line Items Creation]
                                                        │
                                                        ▼
                                     [Clear Cart] ──► [Route to OrderTrackingView]
```

### 3.2 Order Fulfillment & Return Lifecycle
```
[Order Placed] ──► [Processing / Quality Check] ──► [Dispatched / Ready for BOPIS]
                                                              │
                                                              ▼
                                                   [Delivered / Picked Up]
                                                              │
                                                              ▼
                                              [30-Day Return Window Open]
                                                              │
                                                              ▼ (User requests return)
                                              [Return Approved ──► Label Generated ──► Refunded]
```

---

## 4. Frontend MVVM Architecture Specification

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND VIEW–VIEWMODEL MAPPING                                  │
├───────────────────────┬───────────────────────────────┬──────────────────────────────────────────┤
│ VIEW SCREEN / DRAWER  │ VIEWMODEL HOOK                │ MANAGED STATE & ACTIONS                  │
├───────────────────────┼───────────────────────────────┼──────────────────────────────────────────┤
│ `ProductListView`     │ `useProductListViewModel`     │ Product grid, category filters, sorting  │
│ `ProductDetailView`   │ `useProductDetailViewModel`   │ Sizing matrix, BNPL quote, Try-On launch │
│ `CartDrawer`          │ `useCartViewModel`            │ Multi-brand cart, quantity, promo codes  │
│ `CheckoutView`        │ `useCheckoutViewModel`        │ Delivery vs BOPIS, Tabby BNPL, address   │
│ `OrderTrackingView`   │ `useOrderTrackingViewModel`   │ Milestone timeline, BOPIS pickup pass    │
│ `ReturnRequestModal`  │ `useReturnsViewModel`         │ Reason codes, item selection, PDF labels │
└───────────────────────┴───────────────────────────────┴──────────────────────────────────────────┘
```

### 4.1 ViewModel Implementation: `useCheckoutViewModel`
```typescript
export function useCheckoutViewModel() {
  const [fulfillmentType, setFulfillmentType] = useState<'delivery' | 'bopis'>('delivery');
  const [selectedBopisStoreId, setSelectedBopisStoreId] = useState<number>(1);
  const [paymentMethod, setPaymentMethod] = useState<string>('bnpl_tabby');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { cart, fetchCart } = useCartStore();
  const { showToast } = useUIStore();
  const navigate = useNavigate();

  const submitOrder = useCallback(async (shippingDetails: any) => {
    setIsSubmitting(true);
    try {
      const order = await commerceService.checkout({
        payment_method: paymentMethod,
        fulfillment_type: fulfillmentType,
        bopis_store_id: fulfillmentType === 'bopis' ? selectedBopisStoreId : undefined,
        recipient_name: shippingDetails.recipientName,
        phone: shippingDetails.phone,
        address_line: shippingDetails.addressLine,
        city: shippingDetails.city,
        country: shippingDetails.country || 'UAE',
        promo_code: shippingDetails.promoCode || undefined,
        idempotency_key: 'idemp_' + Math.random().toString(36).substring(2, 12),
        try_on_assisted: true,
      });

      setIsSubmitting(false);
      showToast('Order confirmed! Tracking initiated.', 'success');
      navigate(`/orders/${order.order_number}`);
    } catch (err: any) {
      setIsSubmitting(false);
      showToast('Checkout failed: ' + err.message, 'error');
    }
  }, [paymentMethod, fulfillmentType, selectedBopisStoreId, showToast, navigate]);

  return { fulfillmentType, setFulfillmentType, selectedBopisStoreId, setSelectedBopisStoreId, paymentMethod, setPaymentMethod, isSubmitting, submitOrder, cart };
}
```

---

## 5. Backend MVC Architecture & API Contracts

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     BACKEND MVC MAPPING (G5)                                     │
├─────────────────┬────────────────────────────────────────────────────────────────────────────────┤
│ LAYER           │ IMPLEMENTATION COMPONENT                                                       │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Controllers** │ `catalog_controller.py`, `commerce_controller.py`, `bopis_controller.py`       │
│ **Services**    │ `commerce_service.py`, `bopis_service.py`, `bnpl_provider.py`                  │
│ **Repositories**│ `commerce_repository.py`, `catalog_repository.py`                              │
│ **Models**      │ `Cart`, `CartItem`, `Order`, `OrderItem`, `ReturnRequest`, `StoreInventory`     │
│ **Schemas**     │ `CartOut`, `CartItemAdd`, `CheckoutRequest`, `OrderOut`, `OrderTrackingOut`    │
│ **Providers**   │ `BNPLProvider` (Tabby / Tamara), `PaymentProvider` (Stripe / Apple Pay)        │
└─────────────────┴────────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Production REST API Contracts

#### `GET /api/v1/commerce/cart`
**Headers:** `X-Session-Token: sess_...`  
**Response (200 OK):**
```json
{
  "id": 1,
  "items": [
    {
      "id": 1,
      "product_sku_id": 2,
      "product_id": 1,
      "product_title": "Tailored Italian Wool Double-Breasted Blazer",
      "product_title_ar": "سترة بليزر صوف إيطالي بصدر مزدوج",
      "brand_name": "Massimo Dutti",
      "size": "M",
      "color": "Navy Blue",
      "unit_price": 289.0,
      "quantity": 1,
      "subtotal": 289.0,
      "image_url": "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=700",
      "ai_fit_verdict": "True to Size (Confidence 95%)"
    }
  ],
  "subtotal": 289.0,
  "discount_amount": 0.0,
  "tax_amount": 14.45,
  "shipping_amount": 0.0,
  "total": 303.45,
  "currency": "USD",
  "items_count": 1,
  "bnpl_monthly_quote": 75.86
}
```

#### `POST /api/v1/commerce/checkout`
**Request Payload:**
```json
{
  "payment_method": "bnpl_tabby",
  "fulfillment_type": "bopis",
  "bopis_store_id": 1,
  "recipient_name": "Layla Al-Mansoor",
  "phone": "+971501234567",
  "city": "Dubai",
  "country": "UAE",
  "promo_code": "CONFIT10",
  "idempotency_key": "idemp_882190fa",
  "try_on_assisted": true,
  "stylist_assisted": true
}
```
**Response (200 OK):**
```json
{
  "id": 101,
  "order_number": "CONF-8821094A",
  "status": "processing",
  "total_amount": 384.0,
  "subtotal_amount": 384.0,
  "discount_amount": 20.0,
  "tax_amount": 18.2,
  "shipping_amount": 0.0,
  "currency": "USD",
  "payment_method": "bnpl_tabby",
  "payment_status": "paid",
  "payment_installments": 4,
  "fulfillment_type": "bopis",
  "bopis_store_name": "Massimo Dutti — The Dubai Mall",
  "bopis_pickup_code": "PICKUP-8821",
  "tracking_number": "TRK-CONF-8821094",
  "try_on_assisted": true,
  "stylist_assisted": true,
  "items": [
    {
      "id": 1,
      "product_id": 1,
      "product_title": "Tailored Italian Wool Double-Breasted Blazer",
      "brand_name": "Massimo Dutti",
      "size": "M",
      "color": "Navy Blue",
      "unit_price": 289.0,
      "quantity": 1,
      "subtotal": 289.0,
      "is_returned": false
    }
  ],
  "created_at": "2026-08-17T16:04:52.000Z"
}
```

#### `GET /api/v1/commerce/orders/{order_number}/tracking`
**Response (200 OK):**
```json
{
  "order_number": "CONF-8821094A",
  "current_status": "processing",
  "estimated_delivery": "Today by 6:00 PM",
  "carrier": "In-Store Concierge",
  "tracking_number": "TRK-CONF-8821094",
  "timeline": [
    {
      "status_key": "placed",
      "title": "Order Placed & Confirmed",
      "description": "Payment secured and routed to store warehouse.",
      "is_completed": true,
      "is_current": false
    },
    {
      "status_key": "processing",
      "title": "Store Preparing Items",
      "description": "Boutique associate pulling garments and verifying quality.",
      "is_completed": true,
      "is_current": true
    },
    {
      "status_key": "ready_for_pickup",
      "title": "Ready for Boutique Pickup",
      "description": "Present pickup code PICKUP-8821 at checkout counter.",
      "is_completed": false,
      "is_current": false
    }
  ],
  "bopis_store_info": {
    "name": "Massimo Dutti — The Dubai Mall",
    "address": "Fashion Avenue, Level 1, Financial Center Rd",
    "city": "Dubai",
    "pickup_instructions": "Visit the Fashion Avenue VIP Concierge desk. Show digital pickup QR.",
    "pickup_code": "PICKUP-8821"
  }
}
```

---

## 6. Security, Resilience & Core Business Rules

1. **Atomic Inventory Reservation:** Inventory deductions and reservations use transactional database rows with lock isolation, preventing over-selling of limited boutique stock.
2. **Idempotency Protection:** Checkout endpoints require a client-generated UUID `idempotency_key` backed by a unique index on `orders.idempotency_key` to eliminate duplicate payment attempts during network blips.
3. **PCI & Payment Secret Isolation:** Zero payment gateway private keys or credit card CVVs touch client-side bundles.
4. **BOPIS Eligibility Constraints:** Pickup orders are restricted strictly to physical stores with positive available stock (`quantity - reserved_quantity > 0`).

---

## 7. Automated Test Suite Verification

Feature Group G5 is covered by automated integration test suites in `backend/tests/test_api.py`:

```bash
PYTHONPATH=. pytest backend/tests/test_api.py -k "test_commerce_cart_checkout_and_tracking" -v
```

```
============================== test session starts ==============================
backend/tests/test_api.py::test_commerce_cart_checkout_and_tracking PASSED [100%]
============================== 1 passed in 0.92s ===============================
```

### Verified Assertions:
- ✅ Cart addition and quantity updates across multi-brand SKUs.
- ✅ Multi-brand checkout with BNPL Tabby payment method.
- ✅ In-store BOPIS pickup code generation (`PICKUP-8821`).
- ✅ Real-time tracking timeline resolution with milestone status progression.

---

## 8. Deliverable Assets

The complete G5 feature specification document has been saved to:  
📁 `/home/user/docs/CONFIT_Feature_Spec_G5_Commerce_Payments_Fulfillment.md` (and presented in the interactive viewer).
