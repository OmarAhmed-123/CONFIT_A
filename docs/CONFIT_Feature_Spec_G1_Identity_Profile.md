# CONFIT — Feature Specification G1: User Identity & Profile Management

**Feature Group:** G1 — Foundation Layer  
**Document Version:** 1.0.0 (Production Delivery)  
**Primary Output Artifact:** **User Style Profile (USP)** (Canonical JSON Schema & Encrypted Biometric Model)  
**Security Standard:** OAuth 2.0 / JWT / TOTP MFA / Fernet-256 AES Encryption / GDPR & CCPA Compliant  
**Architecture:** Frontend MVVM & Backend MVC with Service-Oriented Isolation  

---

## 1. Executive Purpose & Business Outcome

Feature Group G1 is the foundational personalization and security layer of the CONFIT platform. Its primary mission is: **"Understand the user once, personalize consistently across every touchpoint forever."**

The output of this group is the **User Style Profile (USP)** — a canonical, persistent, and dynamically updated data object that powers all downstream intelligence across:
- **G2 Discovery & Styling:** Personalizes conversational AI stylist responses, filters catalog items by aesthetics, and seeds the Outfit Builder.
- **G3 Virtual Try-On:** Scales 3D silhouette proportion models based on anthropometric body attributes without revealing raw measurements.
- **G4 Smart Wardrobe:** Calibrates wardrobe gap analysis and tunes duplicate purchase alert thresholds.
- **G5 Commerce:** Drives real-time AI Fit Score calculations and size recommendations on Product Detail Pages (PDP).

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                G1 DATA PROPAGATION TOPOLOGY                                      │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   ┌───────────────────────────┐         ┌────────────────────────────────────────────────────┐   │
│   │ 5-Step Style Quiz Wizard  │ ──────► │ User Style Profile (USP)                           │   │
│   │ + Anthropometric Inputs   │         │ - Style Archetypes (Quiet Luxury, Minimalist)      │   │
│   └───────────────────────────┘         │ - Preferred & Avoided Color Palettes               │   │
│                                         │ - Target Budget Allocations ($400/outfit)          │   │
│   ┌───────────────────────────┐         │ - Fernet-256 Encrypted Measurements                │   │
│   │ Explicit Privacy Consents │ ──────► │ - Brand Affinity Matrix (Whitelist/Blacklist)      │   │
│   └───────────────────────────┘         └─────────────┬──────────────────────────────────────┘   │
│                                                       │                                          │
│                    ┌──────────────────────────────────┼──────────────────────────────────┐       │
│                    ▼                                  ▼                                  ▼       │
│     ┌────────────────────────────┐     ┌────────────────────────────┐     ┌────────────────────┐ │
│     │ G2: AI Stylist & Engine    │     │ G3: VTON Proportion Scale  │     │ G5: AI Fit Scores  │ │
│     └────────────────────────────┘     └────────────────────────────┘     └────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Functional Scope & Feature Breakdown

### 2.1 Authentication & Registration
- **Email & Password:** Registration with strict password entropy checks (minimum 8 characters, alphanumeric + symbols) and bcrypt hashing ($2^{12}$ work factor).
- **OAuth 2.0 Social Sign-In:** One-click registration and linking for Google, Apple ID, and Facebook.
- **Session Lifecycle:** Dual-token issuance:
  - **Access Token:** Short-lived JWT (60 minutes expiry) containing user ID, role scope (`consumer`, `brand_user`, `admin`), and tenant context.
  - **Refresh Token:** Long-lived cryptographically random token (30 days expiry) stored in database with automatic rotation and revocation on reuse.
- **Time-Based One-Time Password (TOTP) MFA:** RFC 6238 compliant two-factor authentication with Base32 secret generation, QR code provisioning URIs, and single-use emergency backup recovery codes.

### 2.2 5-Step Style Onboarding Quiz
1. **Step 1 — Style Archetypes:** Multi-selection of primary fashion identities (*Smart Casual*, *Quiet Luxury*, *Modern Minimalist*, *Streetwear Tailored*, *Old Money*, *Bohemian Refined*).
2. **Step 2 — Color Harmony & Palette Preferences:** Visual swatch selection of preferred core tones (*Navy Blue*, *Beige Sand*, *Optic White*, *Forest Green*, *Ivory*) and explicitly avoided shades (*Neon Orange*, *Magenta*).
3. **Step 3 — Anthropometric Sizing & Proportions (Optional):** Height ($140\text{--}210\text{ cm}$), weight ($40\text{--}140\text{ kg}$), silhouette type (*Athletic*, *Hourglass*, *Rectangle*, *Pear*, *Inverted Triangle*), and standard apparel sizes (Tops: XS–XXL, Bottoms: 28–42).
4. **Step 4 — Budget Allocations & Occasion Weights:** Monthly apparel budget slider, maximum target budget per outfit ($100–$1,500), and lifestyle occasion weighting (Work, Casual, Evening, Sports).
5. **Step 5 — Privacy Consents & Brand Preferences:** Preferred brand whitelisting (*Massimo Dutti*, *COS*, *Reiss*, *Arket*), brand exclusions, and explicit opt-in for session-based Virtual Try-On photo processing.

### 2.3 Biometric Data Protection (Fernet-256 Encryption at Rest)
- Anthropometric measurements (`height_cm`, `weight_kg`, `chest_cm`, `waist_cm`, `hip_cm`, `inseam_cm`) are encrypted with authenticated symmetric AES-256 (Fernet) cipher keys prior to database insertion.
- Raw measurements are never exposed to brand partners or unauthenticated APIs.
- Sizing recommendations compute dimensionless scaling ratios (`scaling_factor = height_cm / 175.0`) server-side to drive diffusion try-on garment warping.

### 2.4 Privacy, GDPR Article 17 & Consent Lifecycle
- **Explicit Consent Ledger:** Tracks granular consent states (`photo_storage`, `ai_personalization`, `marketing_analytics`) with policy versions, granting source, and revocation timestamps.
- **Automated 24h Purge Lifecycle:** Unconsented try-on imagery and ephemeral session assets are automatically assigned `expires_at = NOW() + INTERVAL '24 hours'` and wiped via an hourly maintenance worker.
- **GDPR Data Portability:** Endpoints generate a structured JSON data archive containing user profile metadata, style preferences, fit logs, and purchase history.
- **Account Erasure:** Irrevocably erases user credentials, personal identities, and encrypted biometrics with audit trail logging.

---

## 3. User Journeys & State Machine Diagrams

### 3.1 New User Registration & Onboarding Flow
```
[User Lands] ──► [AuthModal / Register] ──► [Bcrypt Hash / Token Issue]
                                                    │
                                                    ▼
                                       [OnboardingQuizView (Step 1/5)]
                                                    │ (Aesthetics & Archetypes)
                                                    ▼
                                       [OnboardingQuizView (Step 2/5)]
                                                    │ (Color Swatches)
                                                    ▼
                                       [OnboardingQuizView (Step 3/5)]
                                                    │ (Body Measurements - Encrypted)
                                                    ▼
                                       [OnboardingQuizView (Step 4/5)]
                                                    │ (Budget & Occasions)
                                                    ▼
                                       [OnboardingQuizView (Step 5/5)]
                                                    │ (Brand Whitelist & Consent)
                                                    ▼
                                       [Persist USP via API] ──► [Redirect to Home Dashboard]
```

### 3.2 Privacy & Data Management Lifecycle Flow
```
[User Profile Settings] ──► [Privacy & GDPR Tab]
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          ▼                                                   ▼
[Request GDPR Export]                               [Request Account Deletion]
          │                                                   │
          ▼                                                   ▼
[Generate Signed JSON Archive]                      [Verify MFA / Password]
          │                                                   │
          ▼                                                   ▼
[Browser Direct Download]                           [Wipe DB & S3 Assets via Purge Daemon]
```

---

## 4. Frontend MVVM Architecture Specification

### 4.1 Views & Components
- `src/views/consumer/UserProfileView.tsx`: Displays verified style profile overview, aesthetic chips, budget allocations, encrypted body attribute summary, and GDPR controls.
- `src/views/auth/AuthModal.tsx`: High-conversion authentication modal supporting email/password sign-in, registration, and 1-click persona test accounts (*Shopper*, *Brand Manager*).
- `src/components/navigation/ConsumerNavbar.tsx`: Top bar displaying authenticated user avatar initials and direct profile navigation.

### 4.2 ViewModel: `useProfileViewModel` & `useAuthViewModel`
- **State Properties:**
  - `user`: Active `User` object or `null`.
  - `usp`: Canonical `UserStyleProfile` entity.
  - `isLoading`: Boolean indicator for network synchronization.
  - `isQuizOpen`: Controls 5-step onboarding wizard modal visibility.
  - `quizStep`: Current step index ($1\text{--}5$).
- **Commands & Methods:**
  - `login(email, password, mfaCode)`: Dispatches authentication and stores JWT tokens.
  - `submitQuiz(payload)`: Serializes quiz form inputs and commits USP updates.
  - `exportGDPR()`: Downloads signed account data archive.
  - `deleteAccount()`: Executes soft/hard deletion with confirmation prompt.

```typescript
// Sample ViewModel Implementation Snippet
export function useProfileViewModel() {
  const [usp, setUsp] = useState<UserStyleProfile | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { showToast } = useUIStore();

  const fetchProfile = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await profileService.getUSP();
      setUsp(data);
      setIsLoading(false);
    } catch (err: any) {
      setIsLoading(false);
      showToast('Error loading profile: ' + err.message, 'error');
    }
  }, [showToast]);

  const savePreferences = useCallback(async (formData: any) => {
    try {
      const updated = await profileService.submitQuiz(formData);
      setUsp(updated);
      showToast('Style Profile & Biometrics Encrypted & Saved!', 'success');
    } catch (err: any) {
      showToast('Failed to save profile: ' + err.message, 'error');
    }
  }, [showToast]);

  return { usp, isLoading, fetchProfile, savePreferences };
}
```

---

## 5. Backend MVC Architecture & API Contracts

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     BACKEND MVC MAPPING (G1)                                     │
├─────────────────┬────────────────────────────────────────────────────────────────────────────────┤
│ LAYER           │ IMPLEMENTATION COMPONENT                                                       │
├─────────────────┼────────────────────────────────────────────────────────────────────────────────┤
│ **Controller**  │ `backend/app/controllers/auth_controller.py` & `profile_controller.py`         │
│ **Service**     │ `backend/app/services/auth_service.py` & `profile_service.py`                    │
│ **Repository**  │ `backend/app/repositories/user_repository.py` & `profile_repository.py`        │
│ **Model**       │ `backend/app/models/user.py` & `profile.py`                                    │
│ **Schema**      │ `backend/app/schemas/auth.py` & `profile.py`                                   │
│ **Security**    │ `backend/app/core/security.py` (Bcrypt, JWT HS256, Fernet AES-256 Biometrics)  │
└─────────────────┴────────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 REST API Endpoint Contracts

#### `POST /api/v1/auth/register`
**Request Payload:**
```json
{
  "email": "layla@example.com",
  "password": "Password123!",
  "full_name": "Layla Al-Mansoor",
  "phone": "+971501234567",
  "role": "consumer",
  "preferred_language": "en"
}
```
**Response (201 Created):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "layla@example.com",
    "full_name": "Layla Al-Mansoor",
    "role": "consumer",
    "preferred_language": "en",
    "is_active": true,
    "is_verified": true,
    "mfa_enabled": false,
    "has_profile": false,
    "created_at": "2026-08-17T16:00:00.000Z"
  }
}
```

#### `POST /api/v1/auth/login`
**Request Payload:**
```json
{
  "email": "shopper@confit.io",
  "password": "Password123!",
  "mfa_code": null
}
```

#### `GET /api/v1/profile/me`
**Response (200 OK):**
```json
{
  "id": 1,
  "user_id": 1,
  "style_archetypes": ["Smart Casual", "Quiet Luxury", "Modern Minimalist"],
  "preferred_colors": ["Navy", "Beige", "Black", "Forest Green", "Ivory"],
  "avoided_colors": ["Neon Orange", "Magenta"],
  "fashion_aesthetics": ["Old Money", "Modern Tailored", "Relaxed Elegance"],
  "budget_monthly_min": 250.0,
  "budget_monthly_max": 1500.0,
  "budget_per_outfit_max": 450.0,
  "preferred_brands": ["Massimo Dutti", "COS", "Reiss", "Arket"],
  "blacklisted_brands": [],
  "occasion_weights": {
    "work": 0.40,
    "casual": 0.35,
    "party": 0.15,
    "sports": 0.10
  },
  "size_tops": "M",
  "size_bottoms": "32",
  "size_shoes": "42",
  "fit_preference": "regular",
  "body_shape_tag": "Athletic",
  "body_attributes": {
    "height_cm": 178.0,
    "weight_kg": 72.0,
    "body_shape": "Athletic",
    "chest_cm": 98.0,
    "waist_cm": 82.0,
    "hip_cm": 96.0,
    "inseam_cm": 81.0,
    "is_encrypted": true
  },
  "onboarding_completed": true,
  "privacy_consent_tryon_storage": true,
  "privacy_consent_share_with_brands": false,
  "updated_at": "2026-08-17T16:04:52.000Z"
}
```

#### `POST /api/v1/profile/onboarding-quiz`
**Request Payload:**
```json
{
  "style_archetypes": ["Smart Casual", "Quiet Luxury"],
  "preferred_colors": ["Navy", "Beige", "Black"],
  "avoided_colors": ["Neon Yellow"],
  "budget_monthly_min": 200.0,
  "budget_monthly_max": 1200.0,
  "budget_per_outfit_max": 400.0,
  "preferred_brands": ["Massimo Dutti", "COS"],
  "size_tops": "M",
  "size_bottoms": "32",
  "size_shoes": "42",
  "fit_preference": "regular",
  "body_attributes": {
    "height_cm": 178.0,
    "weight_kg": 72.0,
    "body_shape": "Athletic",
    "chest_cm": 98.0,
    "waist_cm": 82.0
  },
  "privacy_consent_tryon_storage": true,
  "privacy_consent_share_with_brands": false
}
```

---

## 6. Security, Encryption & Privacy Specifications

1. **Biometric Cipher:** Anthropometric measurements are encrypted with authenticated symmetric AES-256 (Fernet) cipher keys using a server-side secret key (`ENCRYPTION_KEY_FOR_BODY_DATA`).
2. **Password Hashing:** Passwords hashed with bcrypt ($2^{12}$ work factor).
3. **Session Revocation:** Long-lived refresh tokens are stored in the database with device signatures and IP tracking, enabling instant single-device or global session revocation.
4. **GDPR Article 17 Compliance:** Hourly purge daemons erase unconsented try-on imagery after 24 hours. Full structured JSON data export (`GET /api/v1/auth/gdpr-export`) and account erasure endpoints (`DELETE /api/v1/auth/account`) are fully operational.
5. **Role-Based Access Control (RBAC):** Controller-level permission guards enforce access boundaries between `consumer`, `brand_user`, and `admin` scopes.

---

## 7. Analytics Instrumentation

| Event Name | Trigger Moment | Payload Metadata |
| :--- | :--- | :--- |
| `auth_register_started` | User opens registration view | `{ "source": "modal", "locale": "en" }` |
| `auth_register_completed` | User successfully creates account | `{ "user_id": "...", "method": "email" }` |
| `auth_login_completed` | User logs in successfully | `{ "user_id": "...", "mfa_used": false }` |
| `onboarding_quiz_step_saved` | User advances through quiz | `{ "step": 3, "time_spent_seconds": 18 }` |
| `onboarding_quiz_completed` | User completes 5-step wizard | `{ "archetypes_count": 2, "body_provided": true }` |
| `privacy_consent_toggled` | User toggles photo retention consent | `{ "consent_type": "photo_storage", "granted": true }` |
| `gdpr_data_exported` | User requests JSON data archive | `{ "user_id": "...", "timestamp": "..." }` |
| `account_deletion_requested` | User confirms account erasure | `{ "user_id": "...", "retention_cleared": true }` |

---

## 8. Verification & Test Suite Results

The G1 feature group is covered by automated integration tests in `backend/tests/test_api.py`:

```bash
PYTHONPATH=. pytest backend/tests/test_api.py -k "test_auth_login_and_me or test_user_style_profile" -v
```

```
============================== test session starts ==============================
backend/tests/test_api.py::test_auth_login_and_me PASSED                 [ 50%]
backend/tests/test_api.py::test_user_style_profile PASSED                [100%]
============================== 2 passed in 1.12s ===============================
```

### Verified Test Assertions:
- ✅ Password authentication and JWT bearer token issuance.
- ✅ `/api/v1/auth/me` profile resolution.
- ✅ Fernet-256 encryption/decryption validation on body measurements.
- ✅ User Style Profile (USP) retrieval with style archetypes and budget limits.

---

## 9. Deliverable Assets

The complete G1 feature specification document has been saved to:  
📁 `/home/user/docs/CONFIT_Feature_Spec_G1_Identity_Profile.md` (and presented in the interactive viewer).
