# CONFIT — Payment Integration Specification for Egypt and GCC

**Document Version:** 1.0.0 (Production Financial Integration Specification)  
**Target Markets:** Egypt (EG / EGP), United Arab Emirates (AE / AED), Saudi Arabia (SA / SAR), Qatar (QA), Kuwait (KW), Bahrain (BH), Oman (OM), Global (USD)  
**Regulatory & Compliance Scope:** CBE (Central Bank of Egypt) Regulations, SAMA (Saudi Central Bank) Standards, PCI-DSS Level 1 Scope Minimization, and Consumer Protection Laws  
**Architecture:** Abstracted Provider Layer (`PaymentOrchestrator`) with Dynamic Market Capability Registry  

---

## 1. Executive Purpose & Scope

This specification defines the production payment architecture, checkout presentation, and backend processing pipelines across **Egypt** and **Gulf Cooperation Council (GCC)** markets:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CONFIT PAYMENT ORCHESTRATION                                     │
├───────────────────────────────────┬──────────────────────────────────────────────────────────────┤
│       EGYPT (EG / EGP)            │                 GULF GCC (AE, SA, QA, KW, BH, OM)            │
├───────────────────────────────────┼──────────────────────────────────────────────────────────────┤
│ - Visa / Mastercard (EGP 3D Sec)  │ - Visa / Mastercard / American Express                       │
│ - Smart Mobile Wallets (Vodafone  │ - Mada Debit Cards (SAMA Tokenized)                          │
│   Cash, Orange, Etisalat via PSP) │ - Tabby (4 Interest-Free Monthly Installments, 0% Fee)       │
│ - InstaPay IPN (Compliant Bridge) │ - Tamara (4 Interest-Free Monthly Installments)              │
│ - Local Egyptian BNPL (Tabby/ValU)│ - Apple Pay & Google Pay (1-Tap Biometric Sheet)             │
│ - Cash on Delivery (COD + OTP)    │ - In-Store BOPIS Settlement & Boutique Pickup                │
└───────────────────────────────────┴──────────────────────────────────────────────────────────────┘
```

---

## 2. Non-Negotiable Implementation & Honesty Rules

1. **No Fake Payment Buttons:** The frontend checkout never renders static, non-functional payment buttons. Every visible payment method maps directly to a real backend adapter and capability record in `MarketPaymentCapabilityRegistry`.
2. **InstaPay-Specific Honesty Rule:**
   - The platform provides a compliant abstraction for bank-to-bank and IPN rails via authorized PSP bridges (`paymob_fawry_bridge`).
   - In sandbox/demo environments, InstaPay displays explainable reference-number reconciliation states without claiming unverified direct clearing ties.
3. **PCI Scope Minimization:** Zero raw cardholder data (PAN, CVV) touches CONFIT servers. All card submissions flow through tokenized PSP-hosted fields or secure SDKs.
4. **Idempotency Protection:** Every payment confirmation requires a UUID v4 `idempotency_key` stored with unique database constraints to prevent double charges during mobile network disconnects.

---

## 3. Supported Payment Methods Matrix by Country

| Method ID | Display Name (EN / AR) | Supported Countries | Provider Engine | Requirements & Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| `card` | Credit / Debit Card<br/>*بطاقة بنكية / ائتمانية* | EG, AE, SA, QA, KW, BH, OM, Global | Stripe / Paymob | Visa, Mastercard, Amex with 3D Secure 2.0 OTP verification. |
| `bnpl_tabby` | Tabby — Split in 4<br/>*تابي — قسّم على 4 دفعات* | AE, SA, KW, BH, QA, EG | Tabby REST API | 4 equal interest-free monthly payments. Sharia-compliant. |
| `bnpl_tamara`| Tamara — Split in 4<br/>*تمارا — قسّم على 4 دفعات* | SA, AE, KW | Tamara REST API | 4 payments with 0% interest and zero hidden fees. |
| `apple_pay` | Apple Pay<br/>*أبل باي* | AE, SA, QA, KW, BH, OM, Global | Apple Pay Web / PSP | Instant 1-tap biometric authorization via Face ID / Touch ID. |
| `vodafone_cash`| Smart Mobile Wallets<br/>*المحافظ الإلكترونية الذكية* | **EG (Egypt Only)** | Paymob Wallets | Direct debit from Vodafone Cash, Orange Cash, Etisalat Cash. |
| `instapay_bridge`| InstaPay Instant Transfer<br/>*التحويل البنكي الفوري إنستاباي*| **EG (Egypt Only)** | Paymob / Fawry IPN | Egyptian Instant Payment Network transfer via PSP bridge. |
| `cod` | Cash on Delivery (COD)<br/>*الدفع عند الاستلام* | EG, AE, SA, KW, BH, OM | CONFIT Logistics | Cash collection at doorstep with automated SMS OTP verification. |

---

## 4. Backend Architecture & Integration Hierarchy

```
backend/app/providers/payment/
├── base.py                 # Abstract BasePaymentAdapter (intents, signatures, status)
├── schemas.py              # PaymentMethodOption & MarketPaymentCapabilitiesResponse
├── capability_registry.py  # Market-aware capability matrix for EG, AE, SA, GCC, Global
├── orchestrator.py         # PaymentOrchestrator handling routing & HMAC webhook validation
├── tabby_adapter.py        # Tabby BNPL 4-split quote generator & authorization adapter
├── tamara_adapter.py       # Tamara BNPL 4-split payment adapter
├── paymob_adapter.py       # Egyptian Card, Mobile Wallets & Fawry/InstaPay adapter
├── stripe_adapter.py       # Global Credit/Debit Card & Apple Pay adapter
└── mock_adapter.py         # Deterministic development & test adapter
```

### 4.1 Market Capability Discovery API
- **Endpoint:** `GET /api/v1/payments/methods?country_code=EG` (or `AE`, `SA`, etc.)
- **Response Payload (200 OK):**
```json
{
  "market_code": "EG",
  "currency_code": "EGP",
  "available_methods": [
    {
      "id": "card",
      "title_en": "Credit / Debit Card",
      "title_ar": "بطاقة ائتمانية / بنكية",
      "description_en": "Visa, Mastercard, American Express with 3D Secure",
      "description_ar": "فيزا، ماستركارد، أمريكان إكسبريس مع حماية ثلاثية الأبعاد",
      "icon_name": "card",
      "provider_name": "stripe_or_paymob",
      "is_live": true
    },
    {
      "id": "bnpl_tabby",
      "title_en": "Tabby — Split in 4",
      "title_ar": "تابي — قسّم على 4 دفعات",
      "description_en": "Split in 4 interest-free monthly payments. Sharia compliant.",
      "description_ar": "قسّم على 4 دفعات شهرية بدون فوائد أو رسوم تأخير. متوافق مع الشريعة.",
      "icon_name": "tabby",
      "provider_name": "tabby",
      "is_live": true,
      "installment_available": true,
      "installments_count": 4
    },
    {
      "id": "vodafone_cash",
      "title_en": "Smart Mobile Wallets (Vodafone / Orange / Etisalat Cash)",
      "title_ar": "المحافظ الإلكترونية (فودافون كاش / أورنج / اتصالات / وي)",
      "description_en": "Pay directly with your local Egyptian mobile wallet via Paymob PSP",
      "description_ar": "ادفع مباشرة من محفظتك الإلكترونية المصرية عبر بوابة باي موب",
      "icon_name": "wallet",
      "provider_name": "paymob_wallets",
      "is_live": true
    },
    {
      "id": "instapay_bridge",
      "title_en": "InstaPay Instant Bank Transfer (PSP Bridge)",
      "title_ar": "التحويل البنكي الفوري عبر إنستاباي (بوابة الدفع)",
      "description_en": "Instant Egyptian IPN transfer via authorized PSP banking bridge with automated reconciliation",
      "description_ar": "تحويل بنكي فوري عبر شبكة المدفوعات اللحظية IPN المعتمدة مع مطابقة آلية",
      "icon_name": "instapay",
      "provider_name": "paymob_fawry_bridge",
      "is_live": true,
      "requires_redirect": true
    },
    {
      "id": "cod",
      "title_en": "Cash on Delivery (COD)",
      "title_ar": "الدفع نقدًا عند الاستلام",
      "description_en": "Pay in cash at your doorstep upon receiving your luxury package",
      "description_ar": "ادفع نقدًا عند استلام شحنتك الفاخرة على باب منزلك",
      "icon_name": "cod",
      "provider_name": "confit_logistics",
      "is_live": true
    }
  ],
  "cod_eligible": true,
  "bopis_eligible": true,
  "disclaimer_en": "All transactions in EG are processed in compliance with local central bank regulations and PCI-DSS tokenization standards.",
  "disclaimer_ar": "تتم جميع المعاملات في EG بما يتوافق مع تعليمات البنوك المركزية ومعايير التشفير الآمن PCI-DSS."
}
```

---

## 5. Webhook Signature Verification Protocol

```python
def verify_webhook_signature(provider_name: str, payload_bytes: bytes, signature_header: str) -> bool:
    """Verifies HMAC SHA-256 signatures on incoming PSP callbacks."""
    secret = settings.SECRET_KEY.encode("utf-8")
    expected_sig = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature_header)
```

- **Callback Endpoint:** `POST /api/v1/payments/webhooks/{provider}`
- Webhooks update `payment_transactions.status` and transition `orders.status` atomically without client dependency.

---

## 6. Deliverable Assets

The complete payment specification document has been saved to:  
📁 `/home/user/docs/CONFIT_Payment_Integration_Spec_Egypt_GCC.md` (and presented in the interactive viewer).
