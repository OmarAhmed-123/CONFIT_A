/**
 * Consent store — the record of what the user agreed to, when, and under which
 * version of the notice.
 *
 * WHY THIS EXISTS (audit 2026-09-21: "اطلب consent واضحًا للصور والبيانات
 * الحيوية", and the finding that the legacy body-scan flow passed
 * `consentGranted: true` on the user's behalf).
 *
 * Before this module the codebase had consent in NAME ONLY:
 *   · `CameraScanModal` called `measurementService.createSession('client_side',
 *     { consentGranted: true })` with the comment "the user explicitly started
 *     this scan and is looking at the disclosure above the button. That action
 *     is the consent" — the application asserted consent on the user's behalf,
 *     which is the exact pattern GDPR Article 7 forbids (a pre-ticked box, by
 *     another name).
 *   · `VirtualTryOnModal`, `VisualSearchModal` and `WardrobeView` sent photos to
 *     the API with no consent step at all.
 *
 * WHAT GDPR ACTUALLY REQUIRES, and how each requirement maps to a field here:
 *   · **Explicit** — a positive action per purpose, never a default. → only
 *     `grant()` writes a record, and it is only called from a button press.
 *   · **Specific** — consent for a try-on is not consent for wardrobe tagging.
 *     → consent is keyed by PURPOSE, one record per purpose.
 *   · **Informed** — the notice must state what, why, where and for how long.
 *     → `NOTICE_VERSION` pins the exact text shown; the record stores it.
 *   · **Withdrawable at any time** — as easy to withdraw as to give.
 *     → `withdraw()` / `withdrawAll()`, surfaced in the UI.
 *   · **Demonstrable** — the controller must be able to prove what was agreed.
 *     → each record carries `grantedAt` ISO timestamp + `noticeVersion`.
 *
 * SCOPE — read this before treating this file as compliance:
 *   This is a **client-side** record. It makes the in-product flow honest and
 *   auditable on the user's own device. It is NOT a server-side consent ledger
 *   and is NOT, by itself, GDPR compliance — that also needs the server to
 *   record the grant against the account, a DPIA, and legal review. Those are
 *   stated as remaining work rather than implied here.
 */
import { create } from 'zustand';

/**
 * Bump when the wording of the notice changes materially. Every record stores
 * the version it was granted under, and `hasConsent` treats a record from an
 * older version as ABSENT — so a materially different notice forces re-consent
 * instead of silently inheriting agreement to text the user never saw.
 */
export const NOTICE_VERSION = '2.0';

export type ConsentPurpose = 'try_on' | 'visual_search' | 'wardrobe' | 'body_scan';

export const CONSENT_PURPOSES: readonly ConsentPurpose[] = [
  'try_on',
  'visual_search',
  'wardrobe',
  'body_scan',
] as const;

export interface ConsentRecord {
  purpose: ConsentPurpose;
  noticeVersion: string;
  /** ISO-8601. Evidence of WHEN, which is half of what makes consent provable. */
  grantedAt: string;
  /**
   * True when the user asked to be remembered for this browsing session rather
   * than re-prompted each time. Never set by default — the checkbox is
   * unchecked and the option only applies AFTER an explicit grant.
   */
  rememberForSession: boolean;
}

export interface ConsentState {
  records: Partial<Record<ConsentPurpose, ConsentRecord>>;
  hasConsent: (purpose: ConsentPurpose) => boolean;
  getRecord: (purpose: ConsentPurpose) => ConsentRecord | undefined;
  grant: (purpose: ConsentPurpose, options?: { rememberForSession?: boolean }) => ConsentRecord;
  withdraw: (purpose: ConsentPurpose) => void;
  withdrawAll: () => void;
  /** Every record, for the GDPR export and for the Privacy view. */
  exportRecords: () => ConsentRecord[];
}

const STORAGE_KEY = 'confit_consent_v2';
const SESSION_KEY = 'confit_consent_session';

/** Session-scoped grants live in sessionStorage: closing the tab revokes them. */
type SessionGrants = Partial<Record<ConsentPurpose, ConsentRecord>>;

function readStorage<T>(storage: Storage | undefined, key: string): T | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    // Corrupt or unavailable storage must never crash the app: treat an
    // unreadable record as NO consent, which is the fail-closed direction.
    return null;
  }
}

function writeStorage(storage: Storage | undefined, key: string, value: unknown): void {
  if (!storage) return;
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or disabled — the in-memory state still governs this tab */
  }
}

function loadRecords(): Partial<Record<ConsentPurpose, ConsentRecord>> {
  const persistent = readStorage<Partial<Record<ConsentPurpose, ConsentRecord>>>(
    typeof localStorage === 'undefined' ? undefined : localStorage,
    STORAGE_KEY,
  );
  const session = readStorage<SessionGrants>(
    typeof sessionStorage === 'undefined' ? undefined : sessionStorage,
    SESSION_KEY,
  );
  return { ...(persistent ?? {}), ...(session ?? {}) };
}

export const useConsentStore = create<ConsentState>((set, get) => ({
  records: loadRecords(),

  getRecord: (purpose) => get().records[purpose],

  /**
   * A record only counts when it was granted under the CURRENT notice version.
   * This is what makes "material changes are announced" in the Terms true in
   * code rather than in prose: bump `NOTICE_VERSION`, and every prior grant
   * stops satisfying `hasConsent` until the user agrees again.
   */
  hasConsent: (purpose) => get().records[purpose]?.noticeVersion === NOTICE_VERSION,

  grant: (purpose, options = {}) => {
    const record: ConsentRecord = {
      purpose,
      noticeVersion: NOTICE_VERSION,
      grantedAt: new Date().toISOString(),
      rememberForSession: options.rememberForSession === true,
    };
    set((state) => ({ records: { ...state.records, [purpose]: record } }));

    // "Remember" is a convenience within the session, never a long-lived grant:
    // the user said yes to processing this photo, not to a permanent licence.
    if (record.rememberForSession) {
      writeStorage(typeof sessionStorage === 'undefined' ? undefined : sessionStorage, SESSION_KEY, {
        ...readStorage<SessionGrants>(
          typeof sessionStorage === 'undefined' ? undefined : sessionStorage,
          SESSION_KEY,
        ),
        [purpose]: record,
      });
    } else {
      writeStorage(
        typeof localStorage === 'undefined' ? undefined : localStorage,
        STORAGE_KEY,
        { ...loadRecords(), [purpose]: record },
      );
    }
    return record;
  },

  withdraw: (purpose) => {
    set((state) => {
      const next = { ...state.records };
      delete next[purpose];
      return { records: next };
    });
    const persistent = readStorage<Partial<Record<ConsentPurpose, ConsentRecord>>>(
      typeof localStorage === 'undefined' ? undefined : localStorage,
      STORAGE_KEY,
    );
    if (persistent) {
      delete persistent[purpose];
      writeStorage(typeof localStorage === 'undefined' ? undefined : localStorage, STORAGE_KEY, persistent);
    }
    const session = readStorage<SessionGrants>(
      typeof sessionStorage === 'undefined' ? undefined : sessionStorage,
      SESSION_KEY,
    );
    if (session) {
      delete session[purpose];
      writeStorage(typeof sessionStorage === 'undefined' ? undefined : sessionStorage, SESSION_KEY, session);
    }
  },

  withdrawAll: () => {
    set({ records: {} });
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
    }
    if (typeof sessionStorage !== 'undefined') {
      try {
        sessionStorage.removeItem(SESSION_KEY);
      } catch {
        /* ignore */
      }
    }
  },

  exportRecords: () => {
    const { records } = get();
    return CONSENT_PURPOSES.map((p) => records[p]).filter((r): r is ConsentRecord => Boolean(r));
  },
}));

/**
 * Purposes whose notice differs in substance — the copy for each is a separate
 * key so the user reads the actual destination and retention for THAT flow,
 * not a generic "we process photos".
 */
export const CONSENT_PURPOSE_COPY: Record<ConsentPurpose, { purposeKey: string; retentionKey: string }> = {
  try_on: { purposeKey: 'consent.purpose_try_on', retentionKey: 'consent.retention_try_on' },
  visual_search: { purposeKey: 'consent.purpose_visual_search', retentionKey: 'consent.retention_visual_search' },
  wardrobe: { purposeKey: 'consent.purpose_wardrobe', retentionKey: 'consent.retention_wardrobe' },
  body_scan: { purposeKey: 'consent.purpose_body_scan', retentionKey: 'consent.retention_body_scan' },
};
