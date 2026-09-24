import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { profileService, authService } from '../../services/apiServices';
import { UserStyleProfile } from '../../models';
import { useAuthStore } from '../../stores/authStore';
import { CircularGalleryShowcase } from '../../components/showcase/DesignShowcases';
import { useUIStore } from '../../stores/uiStore';
import { SparkleIcon, UserIcon, RulerIcon, ShieldIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';
import { formatAmount, formatMoney, formatNumber } from '../../i18n/format';

/**
 * Canonical JSON — byte-identical to the backend's integrity form:
 * keys sorted recursively, compact separators, raw UTF-8 (no \u escapes).
 * Used to recompute the GDPR export sha256 client-side before download.
 */
export const canonicalJson = (value: unknown): string => {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalJson).join(',') + ']';
  }
  const keys = Object.keys(value as Record<string, unknown>).sort();
  const parts = keys.map(
    (k) => JSON.stringify(k) + ':' + canonicalJson((value as Record<string, unknown>)[k]),
  );
  return '{' + parts.join(',') + '}';
};

const formatBytes = (n: number): string => {
  if (!Number.isFinite(n)) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
};

/**
 * Option tables for the style quiz and the stored-profile chips.
 *
 * WHY `value` AND `labelKey` ARE SEPARATE
 * ---------------------------------------
 * Every `value` here is written into the shopper's style profile through the API
 * (`style_archetypes`, `preferred_colors`, `avoided_colors`, `fashion_aesthetics`,
 * `blacklisted_brands`, `occasion_weights`, `size_*`, `fit_preference`,
 * `body_attributes.body_shape`) and is what the recommender matches on.
 * `labelKey` is the only thing rendered. Translating a value would write Arabic
 * into a field the backend matches against — silently, with no type error and no
 * failing i18n gate — and would then reject the profile of an Arabic shopper.
 *
 * Brand names are proper nouns, so their label would equal their token anyway;
 * they are kept as plain strings deliberately rather than inventing a key that
 * would translate a brand name.
 */
export const PROFILE_OPTIONS = {
  archetypes: [
    { value: 'Smart Casual', labelKey: 'profile.arch_smart_casual' },
    { value: 'Quiet Luxury', labelKey: 'profile.arch_quiet_luxury' },
    { value: 'Modern Minimalist', labelKey: 'profile.arch_modern_minimalist' },
    { value: 'Streetwear Tailored', labelKey: 'profile.arch_streetwear_tailored' },
    { value: 'Old Money', labelKey: 'profile.arch_old_money' },
    { value: 'Bohemian Refined', labelKey: 'profile.arch_bohemian_refined' },
  ],
  colors: [
    { value: 'Navy', labelKey: 'profile.color_navy' },
    { value: 'Beige', labelKey: 'profile.color_beige' },
    { value: 'Black', labelKey: 'profile.color_black' },
    { value: 'White', labelKey: 'profile.color_white' },
    { value: 'Forest Green', labelKey: 'profile.color_forest_green' },
    { value: 'Ivory', labelKey: 'profile.color_ivory' },
    { value: 'Burgundy', labelKey: 'profile.color_burgundy' },
    { value: 'Camel', labelKey: 'profile.color_camel' },
    { value: 'Charcoal', labelKey: 'profile.color_charcoal' },
  ],
  avoidColors: [
    { value: 'Neon Orange', labelKey: 'profile.avoid_neon_orange' },
    { value: 'Magenta', labelKey: 'profile.avoid_magenta' },
    { value: 'Neon Yellow', labelKey: 'profile.avoid_neon_yellow' },
    { value: 'Fluoro Pink', labelKey: 'profile.avoid_fluoro_pink' },
    { value: 'Lime', labelKey: 'profile.avoid_lime' },
    { value: 'Turquoise', labelKey: 'profile.avoid_turquoise' },
  ],
  aesthetics: [
    { value: 'Old Money', labelKey: 'profile.aesthetic_old_money' },
    { value: 'Quiet Luxury', labelKey: 'profile.aesthetic_quiet_luxury' },
    { value: 'Modern Tailored', labelKey: 'profile.aesthetic_modern_tailored' },
    { value: 'Streetwear', labelKey: 'profile.aesthetic_streetwear' },
    { value: 'Minimalist', labelKey: 'profile.aesthetic_minimalist' },
    { value: 'Preppy', labelKey: 'profile.aesthetic_preppy' },
    { value: 'Athleisure', labelKey: 'profile.aesthetic_athleisure' },
    { value: 'Y2K', labelKey: 'profile.aesthetic_y2k' },
    { value: 'Dark Academia', labelKey: 'profile.aesthetic_dark_academia' },
    { value: 'Cottagecore', labelKey: 'profile.aesthetic_cottagecore' },
  ],
  shapes: [
    { value: 'Athletic', labelKey: 'profile.shape_athletic' },
    { value: 'Hourglass', labelKey: 'profile.shape_hourglass' },
    { value: 'Rectangle', labelKey: 'profile.shape_rectangle' },
    { value: 'Pear', labelKey: 'profile.shape_pear' },
    { value: 'Inverted Triangle', labelKey: 'profile.shape_inverted_triangle' },
    { value: 'Apple', labelKey: 'profile.shape_apple' },
  ],
  fits: [
    { value: 'slim', labelKey: 'profile.fit_slim' },
    { value: 'regular', labelKey: 'profile.fit_regular' },
    { value: 'oversized', labelKey: 'profile.fit_oversized' },
    { value: 'relaxed', labelKey: 'profile.fit_relaxed' },
  ],
  occasions: [
    { value: 'work', labelKey: 'profile.occ_work' },
    { value: 'casual', labelKey: 'profile.occ_casual' },
    { value: 'party', labelKey: 'profile.occ_party' },
    { value: 'formal', labelKey: 'profile.occ_formal' },
    { value: 'sports', labelKey: 'profile.occ_sports' },
    { value: 'travel', labelKey: 'profile.occ_travel' },
  ],
  blacklist: [
    { value: 'Shein', labelKey: 'profile.black_shein' },
    { value: 'Fast Fashion', labelKey: 'profile.black_fast_fashion' },
    { value: 'Fur', labelKey: 'profile.black_fur' },
    { value: 'Leather', labelKey: 'profile.black_leather' },
  ],
  /** Proper nouns: the brand is the label, so no key is invented for it. */
  preferredBrands: ['Massimo Dutti', 'COS', 'Reiss', 'Arket', 'Zara', 'H&M', 'Uniqlo'],
} as const;

type OptionGroup = 'archetypes' | 'colors' | 'avoidColors' | 'aesthetics' | 'shapes' | 'fits' | 'occasions' | 'blacklist';

/**
 * Display key for a token stored in a profile.
 *
 * Matching is case-insensitive and whitespace-tolerant on purpose: the value
 * saved by an older client (or by the backend's own normalisation) may be
 * `athletic` while the table holds `Athletic`. An unknown or free-form value
 * returns `undefined`, and the caller then renders the raw token rather than
 * inventing a label for it.
 */
export const labelKeyFor = (group: OptionGroup, value: string): string | undefined => {
  const needle = value.trim().toLowerCase();
  const table = PROFILE_OPTIONS[group] as readonly { value: string; labelKey: string }[];
  return table.find((o) => o.value.toLowerCase() === needle)?.labelKey;
};

export const UserProfileView: React.FC = () => {
  const { t, i18n } = useTranslation();
  // Active UI language drives number/currency rendering; stored profile
  // tokens stay English regardless (see PROFILE_OPTIONS).
  const lang = i18n.resolvedLanguage ?? 'en';
  const [searchParams] = useSearchParams();
  const { user, isAuthenticated, logout } = useAuthStore();
  const { showToast, openAuthModal } = useUIStore();
  const forceOnboarding = searchParams.get('onboarding') === '1';

  const [usp, setUsp] = useState<UserStyleProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [quizStep, setQuizStep] = useState(1);
  const [isQuizOpen, setIsQuizOpen] = useState(false);

  // Quiz Form State (5-Step Onboarding Wizard) — every step starts EMPTY.
  // G1 §25: the body step must not preload real-looking numbers, else a
  // user who skips step 3 still ends up with fabricated 178/72 written
  // to their encrypted profile.
  const [archetypes, setArchetypes] = useState<string[]>([]);
  const [colors, setColors] = useState<string[]>([]);
  const [avoidedColors, setAvoidedColors] = useState<string[]>([]);
  const [aesthetics, setAesthetics] = useState<string[]>([]);
  const [budgetMonthlyMin, setBudgetMonthlyMin] = useState<number | null>(null);
  const [budgetMonthlyMax, setBudgetMonthlyMax] = useState<number | null>(null);
  const [budgetOutfitMax, setBudgetOutfitMax] = useState<number | null>(null);
  const [preferredBrands, setPreferredBrands] = useState<string[]>([]);
  const [blacklistedBrands, setBlacklistedBrands] = useState<string[]>([]);
  const [occasionWeights, setOccasionWeights] = useState<Record<string, number>>({});
  const [bodyTouched, setBodyTouched] = useState(false);
  const [height, setHeight] = useState<number | null>(null);
  const [weight, setWeight] = useState<number | null>(null);
  const [shape, setShape] = useState<string>('');
  const [sizeTop, setSizeTop] = useState<string>('');
  const [sizeBottom, setSizeBottom] = useState<string>('');
  const [sizeShoes, setSizeShoes] = useState<string>('');
  const [fitPref, setFitPref] = useState<string>('');
  const [consentTryon, setConsentTryon] = useState(false);

  // ---- MFA settings state (G1 §9) --------------------------------------
  // `mfaEnabled` mirrors the server value (user.mfa_enabled) — server is
  // authoritative; local state is only a transient UI cache during the
  // enrollment/disable flows.
  const [mfaEnabled, setMfaEnabled] = useState<boolean>(!!user?.mfa_enabled);
  const [mfaPanel, setMfaPanel] = useState<'idle' | 'enroll' | 'verify' | 'codes' | 'disable' | 'regenerate'>('idle');
  const [mfaQrUri, setMfaQrUri] = useState<string>('');
  const [mfaCode, setMfaCode] = useState('');
  const [mfaPassword, setMfaPassword] = useState('');
  // Disabling MFA requires a current authenticator/recovery code in
  // addition to the password (server contract — MFA_CODE_REQUIRED).
  const [mfaDisableCode, setMfaDisableCode] = useState('');

  // ---- Account deletion step-up state -----------------------------------
  // Server contract: confirm="DELETE" + current password (+ MFA code when
  // enrolled). The panel is revealed on demand; nothing is destructive
  // until the server has re-authenticated the user.
  const [deletePanelOpen, setDeletePanelOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteMfaCode, setDeleteMfaCode] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [mfaBackupCodes, setMfaBackupCodes] = useState<string[]>([]);
  const [mfaBusy, setMfaBusy] = useState(false);

  // ---- Change password state (cycle 9) ---------------------------------
  // In-product rotation: the email reset path 501s while no provider is
  // provisioned, so this form is the ONLY password-change path (it is also
  // how the owner completes the admin handover: sign in with the temporary
  // password once, then change it here).
  const [pwPanel, setPwPanel] = useState(false);
  const [pwCurrent, setPwCurrent] = useState('');
  const [pwNew, setPwNew] = useState('');
  const [pwConfirm, setPwConfirm] = useState('');
  const [pwMfa, setPwMfa] = useState('');
  const [pwBusy, setPwBusy] = useState(false);

  useEffect(() => {
    setMfaEnabled(!!user?.mfa_enabled);
  }, [user?.mfa_enabled]);

  const startMfaEnrollment = async () => {
    setMfaBusy(true);
    try {
      const res = await authService.setupMFA();
      setMfaQrUri(res.qr_uri);
      setMfaCode('');
      setMfaPanel('enroll');
    } catch (err: any) {
      showToast(t('profile.mfa_setup_failed', { detail: err.message }), 'error');
    } finally {
      setMfaBusy(false);
    }
  };

  const verifyMfaEnrollment = async () => {
    setMfaBusy(true);
    try {
      const res = await authService.verifyMFA(mfaCode.trim());
      // Backend returns plaintext recovery codes exactly once — surface them
      // now; they are never retrievable again after this screen.
      setMfaBackupCodes(res.backup_codes || []);
      setMfaEnabled(true);
      setMfaPanel('codes');
    } catch (err: any) {
      showToast(t('profile.mfa_verify_failed', { detail: err.message }), 'error');
    } finally {
      setMfaBusy(false);
    }
  };

  const disableMfa = async () => {
    setMfaBusy(true);
    try {
      await authService.disableMFA(mfaPassword, mfaDisableCode.trim());
      setMfaEnabled(false);
      setMfaPassword('');
      setMfaDisableCode('');
      setMfaPanel('idle');
      showToast(t('profile.mfa_disabled'), 'info');
    } catch (err: any) {
      showToast(t('profile.mfa_disable_failed', { detail: err.message }), 'error');
    } finally {
      setMfaBusy(false);
    }
  };

  const regenerateMfaCodes = async () => {
    // Step-up (server-enforced): password + current TOTP/recovery code.
    setMfaBusy(true);
    try {
      const res = await authService.regenerateMFACodes(mfaPassword, mfaDisableCode.trim());
      setMfaBackupCodes(res.backup_codes || []);
      setMfaPassword('');
      setMfaDisableCode('');
      setMfaPanel('codes');
    } catch (err: any) {
      showToast(t('profile.mfa_regen_failed', { detail: err.message }), 'error');
    } finally {
      setMfaBusy(false);
    }
  };

  const changePassword = async () => {
    if (pwNew !== pwConfirm) {
      showToast(t('profile.password_mismatch'), 'error');
      return;
    }
    setPwBusy(true);
    try {
      await authService.changePassword({
        current_password: pwCurrent,
        new_password: pwNew,
        ...(mfaEnabled ? { mfa_code: pwMfa.trim() } : {}),
      });
      setPwPanel(false);
      setPwCurrent(''); setPwNew(''); setPwConfirm(''); setPwMfa('');
      showToast(t('profile.password_changed'), 'success');
      // The server revoked EVERY session (including this one) — sign out
      // locally so the UI reflects the real state instead of a ghost session.
      await logout();
    } catch (err: any) {
      showToast(t('profile.password_change_failed', { detail: err.message }), 'error');
    } finally {
      setPwBusy(false);
    }
  };

  useEffect(() => {
    if (!isAuthenticated) {
      // No server call for a guest — /profile/me now requires auth.
      setIsLoading(false);
      setUsp(null);
      return;
    }
    setIsLoading(true);
    profileService
      .getUSP()
      .then((data: any) => {
        setIsLoading(false);
        if (!data || data.state === 'not_completed' || !data.onboarding_completed) {
          setUsp(null);
          return;
        }
        setUsp(data);
        // Prefill the wizard with the user's ACTUAL saved values (or leave
        // empty). Never invent defaults for fields the user has not set.
        setArchetypes(data.style_archetypes || []);
        setColors(data.preferred_colors || []);
        setAvoidedColors(data.avoided_colors || []);
        setAesthetics(data.fashion_aesthetics || []);
        setBudgetMonthlyMin(data.budget_monthly_min ?? null);
        setBudgetMonthlyMax(data.budget_monthly_max ?? null);
        setBudgetOutfitMax(data.budget_per_outfit_max ?? null);
        setPreferredBrands(data.preferred_brands || []);
        setBlacklistedBrands(data.blacklisted_brands || []);
        setOccasionWeights(data.occasion_weights || {});
        setSizeTop(data.size_tops || '');
        setSizeBottom(data.size_bottoms || '');
        setSizeShoes(data.size_shoes || '');
        setFitPref(data.fit_preference || '');
        setConsentTryon(!!data.privacy_consent_tryon_storage);
        if (data.body_attributes) {
          setHeight(data.body_attributes.height_cm ?? null);
          setWeight(data.body_attributes.weight_kg ?? null);
          setShape(data.body_attributes.body_shape ?? '');
          setBodyTouched(true);
        }
      })
      .catch((err) => {
        setIsLoading(false);
        showToast(t('profile.profile_sync', { detail: err.message }), 'info');
      });
  }, [isAuthenticated, showToast]);

  // First-run onboarding auto-open (G1 §23): if the URL says onboarding=1
  // or the profile hasn't been completed yet, pop the wizard automatically.
  useEffect(() => {
    if (isAuthenticated && !isLoading && (forceOnboarding || (user && !user.has_profile))) {
      setIsQuizOpen(true);
      setQuizStep(1);
    }
  }, [isAuthenticated, isLoading, forceOnboarding, user]);

  const handleSaveQuiz = async () => {
    // Build a payload that ONLY contains fields the user actually
    // interacted with. exclude_unset on the backend then leaves
    // untouched columns alone (G1 §25/§31).
    const payload: Record<string, any> = {};
    if (archetypes.length) payload.style_archetypes = archetypes;
    if (colors.length) payload.preferred_colors = colors;
    if (avoidedColors.length) payload.avoided_colors = avoidedColors;
    if (aesthetics.length) payload.fashion_aesthetics = aesthetics;
    if (budgetMonthlyMin !== null) payload.budget_monthly_min = budgetMonthlyMin;
    if (budgetMonthlyMax !== null) payload.budget_monthly_max = budgetMonthlyMax;
    if (budgetOutfitMax !== null) payload.budget_per_outfit_max = budgetOutfitMax;
    if (preferredBrands.length) payload.preferred_brands = preferredBrands;
    if (blacklistedBrands.length) payload.blacklisted_brands = blacklistedBrands;
    if (Object.keys(occasionWeights).length) payload.occasion_weights = occasionWeights;
    if (sizeTop) payload.size_tops = sizeTop;
    if (sizeBottom) payload.size_bottoms = sizeBottom;
    if (sizeShoes) payload.size_shoes = sizeShoes;
    if (fitPref) payload.fit_preference = fitPref;
    payload.privacy_consent_tryon_storage = consentTryon;

    // Body attributes ONLY when the user actually opened step 3 AND
    // entered at least one value — never fabricate 178/72.
    if (bodyTouched) {
      const body: Record<string, any> = {};
      if (height !== null) body.height_cm = height;
      if (weight !== null) body.weight_kg = weight;
      if (shape) body.body_shape = shape;
      if (Object.keys(body).length) payload.body_attributes = body;
    }

    try {
      const updated = await profileService.submitOnboardingQuiz(payload);
      setUsp(updated as any);
      setIsQuizOpen(false);
      showToast(t('profile.usp_saved'), 'success');
    } catch (err: any) {
      showToast(t('profile.save_failed', { detail: err.message }), 'error');
    }
  };

  const handleDeleteBodyAttributes = async () => {
    if (!window.confirm(t('profile.confirm_delete_body'))) return;
    try {
      await profileService.deleteBodyAttributes();
      setHeight(null);
      setWeight(null);
      setShape('');
      setBodyTouched(false);
      if (usp) setUsp({ ...usp, body_attributes: undefined, body_shape_tag: undefined } as any);
      showToast(t('profile.body_deleted'), 'success');
    } catch (err: any) {
      showToast(t('profile.delete_failed', { detail: err.message }), 'error');
    }
  };

  const handleGdprExport = async () => {
    if (!isAuthenticated) {
      openAuthModal('login');
      return;
    }
    try {
      const res = await authService.exportGDPR();
      // Verify the server-declared integrity BEFORE offering the download:
      // recompute sha256 over the canonical JSON of `data` (sorted keys,
      // compact separators — mirrors the server's algorithm) and compare.
      // "Download started" is not proof; a checksum match is.
      let integrityNote = '';
      const integrity = res?.export_integrity;
      if (integrity?.checksum_sha256 && res?.data && window.crypto?.subtle) {
        const canonical = canonicalJson(res.data);
        const digest = await window.crypto.subtle.digest(
          'SHA-256',
          new TextEncoder().encode(canonical),
        );
        const hex = Array.from(new Uint8Array(digest))
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');
        if (hex === integrity.checksum_sha256) {
integrityNote = t('profile.exported_integrity', {
            hash: hex.slice(0, 12),
            size: formatBytes(integrity.canonical_bytes),
          });
        } else {
          showToast(t('profile.export_integrity_failed'), 'error');
          return;
        }
      }
      const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const downloadAnchor = document.createElement('a');
      downloadAnchor.setAttribute('href', url);
      downloadAnchor.setAttribute('download', `CONFIT_GDPR_Data_${user?.email}.json`);
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      URL.revokeObjectURL(url);
      showToast(t('profile.exported_ok') + integrityNote, 'success');
    } catch (err: any) {
      showToast(t('profile.export_failed', { detail: err.message }), 'error');
    }
  };

  const handleDeleteAccount = async () => {
    // Step-up contract (server-enforced): explicit confirm + current
    // password + MFA code when enrolled. The panel below collects these;
    // this handler fires the real request.
    if (!isAuthenticated) return;
    if (!window.confirm(t('profile.confirm_delete_account'))) return;
    setDeleteBusy(true);
    try {
      await authService.deleteAccount(deletePassword, mfaEnabled ? deleteMfaCode.trim() : undefined);
      logout();
      showToast(t('profile.account_erased'), 'info');
    } catch (err: any) {
      showToast(t('profile.deletion_error', { detail: err.message }), 'error');
    } finally {
      setDeleteBusy(false);
    }
  };

  if (isLoading) {
    return <LoadingSpinner text="Decrypting User Style Profile (USP)..." />;
  }

  return (
    <div className="space-y-8 pb-24 max-w-4xl mx-auto">
      <CircularGalleryShowcase
        tone="consumer"
        compact
        eyebrow={t('profile.gallery_eyebrow')}
        title={t('profile.gallery_title')}
        description={t('profile.gallery_body')}
      />
      {/* Guest Mode Callout Banner */}
      {!isAuthenticated && (
        <div className="bg-[#FAF9F6] border border-[#C5A059]/40 rounded-3xl p-6 shadow-2xs flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-2xl bg-[#0C0E1E] text-[#C5A059] flex items-center justify-center font-bold text-lg shadow-2xs shrink-0">
              <UserIcon size={22} color="#C5A059" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-serif text-lg font-bold text-[#1B1F3B]">
                  {t('profile.guest_title')}
                </h2>
                <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#FDF8EE] text-[#A37E44] font-bold border border-[#C5A059]/30">
                  {t('profile.guest_badge')}
                </span>
              </div>
              <p className="text-xs text-slate-500 font-light mt-0.5">
                {t('profile.guest_body')}
              </p>
            </div>
          </div>

          <div className="flex gap-2.5 shrink-0 w-full sm:w-auto">
            <button
              onClick={() => openAuthModal('login')}
              className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold shadow-2xs transition-all"
            >
              {t('common.sign_in')}
            </button>
            <button
              onClick={() => openAuthModal('register')}
              className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-[#FDF8EE] hover:bg-[#C5A059] text-[#C5A059] hover:text-white border border-[#C5A059]/40 text-xs font-semibold shadow-2xs transition-all"
            >
              {t('common.create_account')}
            </button>
          </div>
        </div>
      )}

      {/* Header Profile Card */}
      <div className="bg-white rounded-3xl border border-slate-200/80 p-6 sm:p-8 shadow-2xs flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-[#1B1F3B] text-white flex items-center justify-center font-bold text-xl shadow-md">
            {user?.full_name?.charAt(0) || 'G'}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-serif text-2xl font-bold text-[#1B1F3B]">
                {user?.full_name || t('profile.guest_explorer')}
              </h1>
              {isAuthenticated && (
                <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#FDF8EE] text-[#A37E44] font-bold border border-[#C5A059]/30">
                  {t('profile.verified_badge')}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 font-light mt-0.5">{user?.email || t('profile.anonymous_session')}</p>
          </div>
        </div>

        <button
          onClick={() => {
            setIsQuizOpen(true);
            setQuizStep(1);
          }}
          className="px-5 py-2.5 rounded-2xl bg-[#C5A059] hover:bg-[#A37E44] text-slate-950 font-bold text-xs shadow-2xs transition-all flex items-center gap-1.5"
        >
          <SparkleIcon size={14} color="#0C0E1E" />
          <span>{t('profile.retake_quiz')}</span>
        </button>
      </div>

      {/* USP Details Card */}
      {usp && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Style Preferences */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
              <SparkleIcon size={18} color="#C5A059" />
              <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('profile.archetypes_title')}</h3>
            </div>

            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                {t('profile.primary_aesthetics')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {usp.style_archetypes.map((a) => (
                  <span key={a} className="px-3 py-1 rounded-xl bg-slate-100 text-xs font-semibold text-slate-800">
                    {labelKeyFor('archetypes', a) ? t(labelKeyFor('archetypes', a)!) : a}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                {t('profile.preferred_colors')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {usp.preferred_colors.map((c) => (
                  <span key={c} className="px-3 py-1 rounded-xl bg-[#FDF8EE] text-[#A37E44] border border-[#C5A059]/30 text-xs font-semibold">
                    {labelKeyFor('colors', c) ? t(labelKeyFor('colors', c)!) : c}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                {t('profile.budget_constraints')}
              </span>
              <div className="text-xs text-slate-700 font-light">
                {usp.budget_per_outfit_max != null
                  ? t('profile.target_per_outfit', { amount: formatMoney(Math.round(usp.budget_per_outfit_max * 100), 'USD', lang) })
                  : ''}
                {usp.budget_monthly_max != null
                  ? t('profile.monthly_allocation', { amount: formatMoney(Math.round(usp.budget_monthly_max * 100), 'USD', lang) })
                  : ''}
              </div>
            </div>
          </div>

          {/* Encrypted Body Attributes */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <RulerIcon size={18} color="#1B1F3B" />
                <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('profile.body_attrs_title')}</h3>
              </div>
              <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                {t('profile.encrypted_badge')}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="text-slate-400 block text-[10px]">{t('profile.height_weight')}</span>
                <span className="font-bold text-slate-900">
                  {usp.body_attributes?.height_cm
                    ? `${formatNumber(usp.body_attributes.height_cm, lang)} ${t('profile.unit_cm')}`
                    : t('profile.not_set')}
                  {' · '}
                  {usp.body_attributes?.weight_kg
                    ? `${formatNumber(usp.body_attributes.weight_kg, lang)} ${t('profile.unit_kg')}`
                    : t('profile.not_set')}
                </span>
              </div>
              <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="text-slate-400 block text-[10px]">{t('profile.silhouette')}</span>
                  {usp.body_shape_tag
                    ? labelKeyFor('shapes', usp.body_shape_tag)
                      ? t(labelKeyFor('shapes', usp.body_shape_tag)!)
                      : usp.body_shape_tag
                    : t('profile.not_set')}
              </div>
              <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="text-slate-400 block text-[10px]">{t('profile.tops_bottoms')}</span>
                <span className="font-bold text-slate-900">{usp.size_tops} / {usp.size_bottoms}</span>
              </div>
              <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="text-slate-400 block text-[10px]">{t('profile.fit_preference')}</span>
                  {usp.fit_preference
                    ? labelKeyFor('fits', usp.fit_preference)
                      ? t(labelKeyFor('fits', usp.fit_preference)!)
                      : usp.fit_preference
                    : t('profile.not_set')}
              </div>
            </div>

            <p className="text-[10px] text-slate-400 font-light leading-relaxed">
              {t('profile.privacy_note')}
            </p>

            {usp.body_attributes && (
              <button
                onClick={handleDeleteBodyAttributes}
                className="text-[11px] font-semibold text-rose-600 hover:text-rose-700 hover:underline"
              >
                {t('profile.delete_my_measurements')}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Security — Two-Factor Authentication (G1 §9) */}
      {isAuthenticated && (
        <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
            <ShieldIcon size={18} color="#C5A059" />
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">{t('profile.mfa_title')}</h3>
          </div>

          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-bold text-slate-900">
                MFA is {mfaEnabled ? t('profile.mfa_is_enabled') : t('profile.mfa_is_disabled')}
              </div>
              <div className="text-[11px] text-slate-500 font-light">
                {mfaEnabled
                  ? t('profile.mfa_enrolled_body')
                  : t('profile.mfa_intro_body')}
              </div>
            </div>
            <span className={`text-[10px] px-2.5 py-1 rounded-full font-bold border shrink-0 ${
              mfaEnabled
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-slate-100 text-slate-600 border-slate-200'
            }`}>
              {mfaEnabled ? t('profile.mfa_on') : t('profile.mfa_off')}
            </span>
          </div>

          {/* Enrollment step 1: show provisioning URI for the authenticator app */}
          {mfaPanel === 'enroll' && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <p className="text-[11px] text-slate-600">
                {t('profile.mfa_enroll_body')}
              </p>
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 break-all font-mono text-[11px] text-slate-800 select-all">
                {mfaQrUri}
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder={t('profile.mfa_code_placeholder')}
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                />
                <button
                  onClick={verifyMfaEnrollment}
                  disabled={mfaBusy || mfaCode.trim().length < 6}
                  className="px-4 py-2 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] text-slate-950 text-xs font-bold disabled:opacity-50"
                >
                  {t('profile.mfa_verify_enable')}
                </button>
              </div>
            </div>
          )}

          {/* One-time recovery codes reveal */}
          {mfaPanel === 'codes' && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <p className="text-[11px] text-slate-600">
                {t('profile.mfa_codes_warning')}{' '}
                <span className="font-bold text-slate-800">{t('profile.mfa_codes_never_shown')}</span>
              </p>
              <div className="grid grid-cols-2 gap-1.5">
                {mfaBackupCodes.map((c) => (
                  <code key={c} className="px-3 py-1.5 rounded-lg bg-slate-900 text-emerald-300 text-[11px] font-mono text-center select-all">
                    {c}
                  </code>
                ))}
              </div>
              <button
                onClick={() => { setMfaPanel('idle'); setMfaBackupCodes([]); }}
                className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-800"
              >
                {t('profile.mfa_codes_saved')}
              </button>
            </div>
          )}

          {/* Regenerate recovery codes: step-up (password + current code) */}
          {mfaPanel === 'regenerate' && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <p className="text-[11px] text-slate-600">
                {t('profile.mfa_regen_warning')}
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="password"
                  placeholder={t('profile.current_password')}
                  value={mfaPassword}
                  onChange={(e) => setMfaPassword(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-slate-400"
                />
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder={t('profile.auth_or_recovery')}
                  value={mfaDisableCode}
                  onChange={(e) => setMfaDisableCode(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-slate-400"
                />
                <button
                  onClick={regenerateMfaCodes}
                  disabled={mfaBusy || !mfaPassword || !mfaDisableCode.trim()}
                  className="px-4 py-2 rounded-xl bg-[#1B1F3B] hover:bg-[#2A2F52] text-white text-xs font-semibold disabled:opacity-50"
                >
                  {t('profile.mfa_regen_short')}
                </button>
              </div>
            </div>
          )}

          {/* Disable flow: requires password re-authentication */}
          {mfaPanel === 'disable' && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <p className="text-[11px] text-slate-600">
                {t('profile.mfa_disable_body')}
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="password"
                  placeholder={t('profile.current_password')}
                  value={mfaPassword}
                  onChange={(e) => setMfaPassword(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-rose-400"
                />
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder={t('profile.auth_or_recovery')}
                  value={mfaDisableCode}
                  onChange={(e) => setMfaDisableCode(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-rose-400"
                />
                <button
                  onClick={disableMfa}
                  disabled={mfaBusy || !mfaPassword || !mfaDisableCode.trim()}
                  className="px-4 py-2 rounded-xl border border-rose-200 hover:bg-rose-50 text-xs font-semibold text-rose-600 disabled:opacity-50"
                >
                  {t('profile.disable_mfa')}
                </button>
              </div>
            </div>
          )}

          {/* Idle actions */}
          {mfaPanel === 'idle' && (
            <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100">
              {!mfaEnabled ? (
                <button
                  onClick={startMfaEnrollment}
                  disabled={mfaBusy}
                  className="px-4 py-2 rounded-xl bg-[#1B1F3B] hover:bg-[#2A2F52] text-white text-xs font-semibold disabled:opacity-50"
                >
                  {t('profile.enable_mfa')}
                </button>
              ) : (
                <>
                  <button
                    onClick={() => { setMfaPassword(''); setMfaDisableCode(''); setMfaPanel('regenerate'); }}
                    disabled={mfaBusy}
                    className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-800 disabled:opacity-50"
                  >
                    {t('profile.mfa_regenerate')}
                  </button>
                  <button
                    onClick={() => { setMfaPassword(''); setMfaPanel('disable'); }}
                    disabled={mfaBusy}
                    className="px-4 py-2 rounded-xl border border-rose-200 hover:bg-rose-50 text-xs font-semibold text-rose-600 disabled:opacity-50"
                  >
                    {t('profile.disable_mfa')}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Security — Change Password (cycle 9): the only in-product password
          rotation path while email delivery is unprovisioned; also the
          completion step of the admin handover (temp → owner password). */}
      {isAuthenticated && (
        <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-bold text-slate-900">{t('profile.password_label')}</div>
              <div className="text-[11px] text-slate-500 font-light">
                {t('profile.password_intro')}
              </div>
            </div>
            <button
              onClick={() => {
                setPwPanel(!pwPanel);
                setPwCurrent(''); setPwNew(''); setPwConfirm(''); setPwMfa('');
              }}
              disabled={pwBusy}
              className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-800 disabled:opacity-50 shrink-0"
            >
              {pwPanel ? t('common.cancel') : t('profile.change_password')}
            </button>
          </div>

          {pwPanel && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              {mfaEnabled && (
                <p className="text-[11px] text-slate-600">
                  {t('profile.password_mfa_body')}
                </p>
              )}
              <input
                type="password"
                placeholder={t('profile.current_password')}
                value={pwCurrent}
                onChange={(e) => setPwCurrent(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
              />
              <input
                type="password"
                placeholder={t('profile.new_password_placeholder')}
                value={pwNew}
                onChange={(e) => setPwNew(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
              />
              <input
                type="password"
                placeholder={t('profile.confirm_new_password')}
                value={pwConfirm}
                onChange={(e) => setPwConfirm(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
              />
              {mfaEnabled && (
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder={t('profile.mfa_code_mfa')}
                  value={pwMfa}
                  onChange={(e) => setPwMfa(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                />
              )}
              <button
                onClick={changePassword}
                disabled={
                  pwBusy ||
                  !pwCurrent ||
                  pwNew.length < 8 ||
                  !pwConfirm ||
                  (mfaEnabled && pwMfa.trim().length < 6)
                }
                className="px-4 py-2 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] text-slate-950 text-xs font-bold disabled:opacity-50"
              >
                {t('profile.update_password')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* GDPR & Privacy Controls */}
      <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
        <h3 className="font-serif text-base font-bold text-[#1B1F3B] pb-2 border-b border-slate-100">
          {t('profile.privacy_title')}
        </h3>

        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 pt-1">
          <div>
            <div className="text-xs font-bold text-slate-900">{t('profile.export_title')}</div>
            <div className="text-[11px] text-slate-500 font-light">{t('profile.export_body')}</div>
          </div>
          <button
            onClick={handleGdprExport}
            className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-800 transition-all shrink-0"
          >
            {t('profile.export_button')}
          </button>
        </div>

        {isAuthenticated && (
          <div className="flex flex-col gap-3 pt-3 border-t border-slate-100">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
              <div>
                <div className="text-xs font-bold text-rose-600">{t('profile.delete_section_title')}</div>
                <div className="text-[11px] text-slate-500 font-light">{t('profile.delete_body')}</div>
              </div>
              <button
                onClick={() => setDeletePanelOpen((v) => !v)}
                className="px-4 py-2 rounded-xl border border-rose-200 hover:bg-rose-50 text-xs font-semibold text-rose-600 transition-all shrink-0"
              >
                {deletePanelOpen ? t('common.cancel') : t('profile.erase_button')}
              </button>
            </div>
            {deletePanelOpen && (
              <div className="space-y-2 p-3 rounded-xl bg-rose-50/50 border border-rose-100">
                <p className="text-[11px] text-slate-600">
                  {t('profile.delete_stepup_a')}{mfaEnabled ? t('profile.delete_stepup_b') : ''}.
                </p>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="password"
                    placeholder={t('profile.current_password')}
                    value={deletePassword}
                    onChange={(e) => setDeletePassword(e.target.value)}
                    className="flex-1 px-3 py-2 rounded-xl border border-rose-200 text-xs focus:outline-none focus:border-rose-400"
                  />
                  {mfaEnabled && (
                    <input
                      type="text"
                      inputMode="numeric"
                      placeholder={t('profile.auth_or_recovery')}
                      value={deleteMfaCode}
                      onChange={(e) => setDeleteMfaCode(e.target.value)}
                      className="flex-1 px-3 py-2 rounded-xl border border-rose-200 text-xs focus:outline-none focus:border-rose-400"
                    />
                  )}
                  <button
                    onClick={handleDeleteAccount}
                    disabled={deleteBusy || !deletePassword || (mfaEnabled && !deleteMfaCode.trim())}
                    className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold disabled:opacity-50 shrink-0"
                  >
                    {deleteBusy ? t('profile.deleting') : t('profile.delete_forever')}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 5-Step Style Quiz Wizard Modal */}
      {isQuizOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md animate-in fade-in duration-150">
          <div className="w-full max-w-xl bg-white rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] border border-slate-100">
            <div className="p-5 bg-[#0C0E1E] text-white flex justify-between items-center border-b border-slate-800">
              <div>
                <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider">
                  {t('profile.step_of', { step: quizStep })}
                </span>
                <h3 className="font-serif text-base font-bold text-white">
                  {t('profile.wizard_title')}
                </h3>
              </div>
              <button onClick={() => setIsQuizOpen(false)} className="text-slate-300 hover:text-white">
                ✕
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {quizStep === 1 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-bold text-slate-900">{t('profile.q_aesthetics')}</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {PROFILE_OPTIONS.archetypes.map((arch) => (
                      <button
                        key={arch.value}
                        onClick={() => {
                          if (archetypes.includes(arch.value)) setArchetypes(archetypes.filter((a) => a !== arch.value));
                          else setArchetypes([...archetypes, arch.value]);
                        }}
                        className={`p-3 rounded-2xl border text-xs font-semibold transition-all text-left ${
                          archetypes.includes(arch.value)
                            ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]'
                            : 'border-slate-200 text-slate-700'
                        }`}
                      >
                        {t(arch.labelKey)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {quizStep === 2 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-bold text-slate-900">{t('profile.q_colors')}</h4>
                  <div className="grid grid-cols-3 gap-2">
                    {PROFILE_OPTIONS.colors.map((col) => (
                      <button
                        key={col.value}
                        onClick={() => {
                          if (colors.includes(col.value)) setColors(colors.filter((c) => c !== col.value));
                          else setColors([...colors, col.value]);
                        }}
                        className={`p-2.5 rounded-xl border text-xs font-semibold text-center transition-all ${
                          colors.includes(col.value)
                            ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]'
                            : 'border-slate-200 text-slate-700'
                        }`}
                      >
                        {t(col.labelKey)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {quizStep === 3 && (
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-bold text-slate-900">{t('profile.q_body_title')}</h4>
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        {t('profile.q_body_body')}
                      </p>
                    </div>
                    {bodyTouched && (
                      <button
                        type="button"
                        onClick={() => { setHeight(null); setWeight(null); setShape(''); setBodyTouched(false); }}
                        className="text-[10px] font-semibold text-rose-500 hover:underline shrink-0"
                      >
                        {t('profile.clear')}
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-bold text-slate-700 block mb-1">{t('profile.height_cm_label')}</label>
                      <input
                        type="number"
                        min={100} max={250}
                        value={height ?? ''}
                        onChange={(e) => { setHeight(e.target.value ? Number(e.target.value) : null); setBodyTouched(true); }}
                        placeholder={t('profile.height_placeholder')}
                        className="w-full p-2.5 rounded-xl border border-slate-200 text-xs"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-bold text-slate-700 block mb-1">{t('profile.weight_kg_label')}</label>
                      <input
                        type="number"
                        min={30} max={250}
                        value={weight ?? ''}
                        onChange={(e) => { setWeight(e.target.value ? Number(e.target.value) : null); setBodyTouched(true); }}
                        placeholder={t('profile.weight_placeholder')}
                        className="w-full p-2.5 rounded-xl border border-slate-200 text-xs"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 block mb-1">{t('profile.silhouette_shape')}</label>
                    <select
                      value={shape}
                      onChange={(e) => { setShape(e.target.value); setBodyTouched(true); }}
                      className="w-full p-2.5 rounded-xl border border-slate-200 text-xs bg-white"
                    >
                      <option value="">{t('profile.select_optional')}</option>
                      {PROFILE_OPTIONS.shapes.map((s) => (
                        <option key={s.value} value={s.value}>{t(s.labelKey)}</option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-3 gap-3 pt-2 border-t border-slate-100">
                    <div>
                      <label className="text-[10px] font-bold text-slate-700 block mb-1">{t('profile.tops_size')}</label>
                      <select value={sizeTop} onChange={(e) => setSizeTop(e.target.value)} className="w-full p-2 rounded-xl border border-slate-200 text-xs bg-white">
                        <option value="">—</option>
                        {['XS','S','M','L','XL','XXL'].map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] font-bold text-slate-700 block mb-1">{t('profile.bottoms_size')}</label>
                      <select value={sizeBottom} onChange={(e) => setSizeBottom(e.target.value)} className="w-full p-2 rounded-xl border border-slate-200 text-xs bg-white">
                        <option value="">—</option>
                        {['28','30','32','34','36','38','40','42'].map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] font-bold text-slate-700 block mb-1">{t('profile.shoes_eu')}</label>
                      <select value={sizeShoes} onChange={(e) => setSizeShoes(e.target.value)} className="w-full p-2 rounded-xl border border-slate-200 text-xs bg-white">
                        <option value="">—</option>
                        {['36','37','38','39','40','41','42','43','44','45','46'].map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-700 block mb-1">{t('profile.preferred_fit')}</label>
                    <div className="grid grid-cols-4 gap-2">
                      {PROFILE_OPTIONS.fits.map(f => (
                        <button
                          key={f.value}
                          type="button"
                          onClick={() => setFitPref(f.value)}
                          className={`p-2 rounded-xl border text-[11px] font-semibold capitalize transition-all ${
                            fitPref === f.value ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]' : 'border-slate-200 text-slate-700'
                          }`}
                        >
                          {t(f.labelKey)}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {quizStep === 4 && (
                <div className="space-y-4">
                  <h4 className="text-sm font-bold text-slate-900">{t('profile.budget_occasions')}</h4>

                  <div>
                    <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                      <span>{t('profile.monthly_budget_min')}</span>
                      <span className="text-[#A37E44]">{formatMoney(Math.round((budgetMonthlyMin ?? 0) * 100), 'USD', lang)}</span>
                    </div>
                    <input type="range" min={0} max={2000} step={50}
                      value={budgetMonthlyMin ?? 0}
                      onChange={(e) => setBudgetMonthlyMin(Number(e.target.value))}
                      className="w-full accent-[#C5A059]" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                      <span>{t('profile.monthly_budget_max')}</span>
                      <span className="text-[#A37E44]">{formatMoney(Math.round((budgetMonthlyMax ?? 0) * 100), 'USD', lang)}</span>
                    </div>
                    <input type="range" min={0} max={5000} step={50}
                      value={budgetMonthlyMax ?? 0}
                      onChange={(e) => setBudgetMonthlyMax(Number(e.target.value))}
                      className="w-full accent-[#C5A059]" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                      <span>{t('profile.max_per_outfit')}</span>
                      <span className="text-[#A37E44]">{formatMoney(Math.round((budgetOutfitMax ?? 0) * 100), 'USD', lang)}</span>
                    </div>
                    <input type="range" min={50} max={2000} step={25}
                      value={budgetOutfitMax ?? 0}
                      onChange={(e) => setBudgetOutfitMax(Number(e.target.value))}
                      className="w-full accent-[#C5A059]" />
                  </div>

                  <div className="pt-2 border-t border-slate-100">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2">
                      {t('profile.week_split')}
                    </span>
                    <div className="grid grid-cols-2 gap-2">
                      {PROFILE_OPTIONS.occasions.map(occ => (
                        <label key={occ.value} className="flex items-center gap-2 text-xs">
                          <span className="w-16 capitalize text-slate-700">{t(occ.labelKey)}</span>
                          <input
                            type="number"
                            step="0.05"
                            min="0"
                            max="1"
                            value={occasionWeights[occ.value] ?? 0}
                            onChange={(e) => setOccasionWeights({ ...occasionWeights, [occ.value]: Number(e.target.value) })}
                            className="flex-1 p-1.5 rounded-lg border border-slate-200 text-xs"
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {quizStep === 2 && (
                <div className="pt-4 border-t border-slate-100 space-y-2">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                    {t('profile.avoid_colors')}
                  </span>
                  <div className="grid grid-cols-3 gap-2">
                    {PROFILE_OPTIONS.avoidColors.map(col => (
                      <button key={col.value} type="button"
                        onClick={() => setAvoidedColors(avoidedColors.includes(col.value) ? avoidedColors.filter(c=>c!==col.value) : [...avoidedColors, col.value])}
                        className={`p-2 rounded-xl border text-xs font-semibold ${avoidedColors.includes(col.value) ? 'border-rose-400 bg-rose-50 text-rose-700' : 'border-slate-200 text-slate-700'}`}>
                        {t(col.labelKey)}
                      </button>
                    ))}
                  </div>
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block pt-2">
                    {t('profile.fashion_aesthetics')}
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {PROFILE_OPTIONS.aesthetics.map(a => (
                      <button key={a.value} type="button"
                        onClick={() => setAesthetics(aesthetics.includes(a.value) ? aesthetics.filter(x=>x!==a.value) : [...aesthetics, a.value])}
                        className={`px-3 py-1.5 rounded-xl border text-[11px] font-semibold ${aesthetics.includes(a.value) ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]' : 'border-slate-200 text-slate-700'}`}>
                        {t(a.labelKey)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {quizStep === 5 && (
                <div className="space-y-4">
                  <h4 className="text-sm font-bold text-slate-900">{t('profile.brands_privacy')}</h4>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2">{t('profile.preferred_brands')}</span>
                    <div className="flex flex-wrap gap-2">
                      {PROFILE_OPTIONS.preferredBrands.map(b => (
                        <button key={b} type="button"
                          onClick={() => setPreferredBrands(preferredBrands.includes(b) ? preferredBrands.filter(x=>x!==b) : [...preferredBrands, b])}
                          className={`px-3 py-1.5 rounded-xl border text-[11px] font-semibold ${preferredBrands.includes(b) ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]' : 'border-slate-200 text-slate-700'}`}>
                          {b}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2">{t('profile.blacklist')}</span>
                    <div className="flex flex-wrap gap-2">
                      {PROFILE_OPTIONS.blacklist.map(b => (
                        <button key={b.value} type="button"
                          onClick={() => setBlacklistedBrands(blacklistedBrands.includes(b.value) ? blacklistedBrands.filter(x=>x!==b.value) : [...blacklistedBrands, b.value])}
                          className={`px-3 py-1.5 rounded-xl border text-[11px] font-semibold ${blacklistedBrands.includes(b.value) ? 'border-rose-400 bg-rose-50 text-rose-700' : 'border-slate-200 text-slate-700'}`}>
                        {t(b.labelKey)}
                      </button>
                      ))}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                    <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-slate-800">
                      <input
                        type="checkbox"
                        checked={consentTryon}
                        onChange={(e) => setConsentTryon(e.target.checked)}
                        className="accent-[#C5A059]"
                      />
                      <span>{t('profile.vton_consent')}</span>
                    </label>
                  </div>
                </div>
              )}
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-between items-center">
              {quizStep > 1 ? (
                <button
                  onClick={() => setQuizStep(quizStep - 1)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700"
                >
                  {t('profile.back')}
                </button>
              ) : <div />}

              {quizStep < 5 ? (
                <button
                  onClick={() => setQuizStep(quizStep + 1)}
                  className="px-5 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold"
                >
                  {t('profile.next_step')}
                </button>
              ) : (
                <button
                  onClick={handleSaveQuiz}
                  className="px-5 py-2 rounded-xl bg-[#C5A059] text-slate-950 font-bold text-xs"
                >
                  {t('profile.finish_save')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
