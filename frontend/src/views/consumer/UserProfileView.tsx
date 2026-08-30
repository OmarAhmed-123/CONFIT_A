import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { profileService, authService } from '../../services/apiServices';
import { UserStyleProfile } from '../../models';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { SparkleIcon, UserIcon, RulerIcon, ShieldIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const UserProfileView: React.FC = () => {
  const { t } = useTranslation();
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
  const [mfaPanel, setMfaPanel] = useState<'idle' | 'enroll' | 'verify' | 'codes' | 'disable'>('idle');
  const [mfaQrUri, setMfaQrUri] = useState<string>('');
  const [mfaCode, setMfaCode] = useState('');
  const [mfaPassword, setMfaPassword] = useState('');
  const [mfaBackupCodes, setMfaBackupCodes] = useState<string[]>([]);
  const [mfaBusy, setMfaBusy] = useState(false);

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
      showToast('MFA setup failed: ' + err.message, 'error');
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
      showToast('Verification failed: ' + err.message, 'error');
    } finally {
      setMfaBusy(false);
    }
  };

  const disableMfa = async () => {
    setMfaBusy(true);
    try {
      await authService.disableMFA(mfaPassword);
      setMfaEnabled(false);
      setMfaPassword('');
      setMfaPanel('idle');
      showToast('Two-factor authentication disabled.', 'info');
    } catch (err: any) {
      showToast('Disable failed: ' + err.message, 'error');
    } finally {
      setMfaBusy(false);
    }
  };

  const regenerateMfaCodes = async () => {
    setMfaBusy(true);
    try {
      const res = await authService.regenerateMFACodes();
      setMfaBackupCodes(res.backup_codes || []);
      setMfaPanel('codes');
    } catch (err: any) {
      showToast('Regeneration failed: ' + err.message, 'error');
    } finally {
      setMfaBusy(false);
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
        showToast('Profile sync: ' + err.message, 'info');
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
      showToast('User Style Profile (USP) saved.', 'success');
    } catch (err: any) {
      showToast('Save failed: ' + err.message, 'error');
    }
  };

  const handleDeleteBodyAttributes = async () => {
    if (!window.confirm('Delete your saved body measurements? This does not affect your account.')) return;
    try {
      await profileService.deleteBodyAttributes();
      setHeight(null);
      setWeight(null);
      setShape('');
      setBodyTouched(false);
      if (usp) setUsp({ ...usp, body_attributes: undefined, body_shape_tag: undefined } as any);
      showToast('Body measurements deleted.', 'success');
    } catch (err: any) {
      showToast('Delete failed: ' + err.message, 'error');
    }
  };

  const handleGdprExport = async () => {
    if (!isAuthenticated) {
      openAuthModal('login');
      return;
    }
    try {
      const res = await authService.exportGDPR();
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(res, null, 2));
      const downloadAnchor = document.createElement('a');
      downloadAnchor.setAttribute('href', dataStr);
      downloadAnchor.setAttribute('download', `CONFIT_GDPR_Data_${user?.email}.json`);
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      showToast('GDPR Data archive exported successfully.', 'success');
    } catch (err: any) {
      showToast('Export failed: ' + err.message, 'error');
    }
  };

  const handleDeleteAccount = async () => {
    if (!isAuthenticated) return;
    if (window.confirm('Are you sure you want to permanently delete your account and all associated encrypted biometric data?')) {
      try {
        await authService.deleteAccount();
        logout();
        showToast('Account permanently erased.', 'info');
      } catch (err: any) {
        showToast('Deletion error: ' + err.message, 'error');
      }
    }
  };

  if (isLoading) {
    return <LoadingSpinner text="Decrypting User Style Profile (USP)..." />;
  }

  return (
    <div className="space-y-8 pb-24 max-w-4xl mx-auto">
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
                  Guest Style Exploration
                </h2>
                <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#FDF8EE] text-[#A37E44] font-bold border border-[#C5A059]/30">
                  Temporary Session
                </span>
              </div>
              <p className="text-xs text-slate-500 font-light mt-0.5">
                Sign in to save your personal measurements, access permanent closet gap analysis, and unlock order tracking.
              </p>
            </div>
          </div>

          <div className="flex gap-2.5 shrink-0 w-full sm:w-auto">
            <button
              onClick={() => openAuthModal('login')}
              className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold shadow-2xs transition-all"
            >
              Sign In
            </button>
            <button
              onClick={() => openAuthModal('register')}
              className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-[#FDF8EE] hover:bg-[#C5A059] text-[#C5A059] hover:text-white border border-[#C5A059]/40 text-xs font-semibold shadow-2xs transition-all"
            >
              Create Account
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
                {user?.full_name || 'Guest Style Explorer'}
              </h1>
              {isAuthenticated && (
                <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#FDF8EE] text-[#A37E44] font-bold border border-[#C5A059]/30">
                  Verified Profile
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 font-light mt-0.5">{user?.email || 'Anonymous Discovery Session'}</p>
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
          <span>Retake 5-Step Style Quiz</span>
        </button>
      </div>

      {/* USP Details Card */}
      {usp && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Style Preferences */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
              <SparkleIcon size={18} color="#C5A059" />
              <h3 className="font-serif text-base font-bold text-[#1B1F3B]">Style Archetypes & Palette</h3>
            </div>

            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                Primary Aesthetics
              </span>
              <div className="flex flex-wrap gap-1.5">
                {usp.style_archetypes.map((a) => (
                  <span key={a} className="px-3 py-1 rounded-xl bg-slate-100 text-xs font-semibold text-slate-800">
                    {a}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                Preferred Colors
              </span>
              <div className="flex flex-wrap gap-1.5">
                {usp.preferred_colors.map((c) => (
                  <span key={c} className="px-3 py-1 rounded-xl bg-[#FDF8EE] text-[#A37E44] border border-[#C5A059]/30 text-xs font-semibold">
                    {c}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                Budget Constraints
              </span>
              <div className="text-xs text-slate-700 font-light">
                Target per Outfit: <strong className="font-semibold text-slate-900">${usp.budget_per_outfit_max}</strong> · Monthly Allocation: <strong className="font-semibold text-slate-900">${usp.budget_monthly_max}</strong>
              </div>
            </div>
          </div>

          {/* Encrypted Body Attributes */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <RulerIcon size={18} color="#1B1F3B" />
                <h3 className="font-serif text-base font-bold text-[#1B1F3B]">Body Attributes & Sizing</h3>
              </div>
              <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                🔒 Fernet-256 Encrypted
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="text-slate-400 block text-[10px]">Height / Weight</span>
                <span className="font-bold text-slate-900">
                  {usp.body_attributes?.height_cm || 178} cm · {usp.body_attributes?.weight_kg || 72} kg
                </span>
              </div>
              <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="text-slate-400 block text-[10px]">Silhouette</span>
                <span className="font-bold text-slate-900">{usp.body_shape_tag || 'Athletic'}</span>
              </div>
              <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="text-slate-400 block text-[10px]">Tops / Bottoms</span>
                <span className="font-bold text-slate-900">{usp.size_tops} / {usp.size_bottoms}</span>
              </div>
              <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-100">
                <span className="text-slate-400 block text-[10px]">Fit Preference</span>
                <span className="font-bold text-slate-900 capitalize">{usp.fit_preference}</span>
              </div>
            </div>

            <p className="text-[10px] text-slate-400 font-light leading-relaxed">
              Data is strictly encrypted at rest and used solely to compute AI garment drape scaling and fit risk scores. Never sold or shared with brand partners without explicit consent.
            </p>

            {usp.body_attributes && (
              <button
                onClick={handleDeleteBodyAttributes}
                className="text-[11px] font-semibold text-rose-600 hover:text-rose-700 hover:underline"
              >
                Delete my saved measurements
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
            <h3 className="font-serif text-base font-bold text-[#1B1F3B]">Security — Two-Factor Authentication</h3>
          </div>

          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-bold text-slate-900">
                MFA is {mfaEnabled ? 'enabled' : 'disabled'}
              </div>
              <div className="text-[11px] text-slate-500 font-light">
                {mfaEnabled
                  ? 'Your account requires a 6-digit authenticator code (or a single-use recovery code) at sign-in.'
                  : 'Add a second layer of protection: a time-based code from your authenticator app.'}
              </div>
            </div>
            <span className={`text-[10px] px-2.5 py-1 rounded-full font-bold border shrink-0 ${
              mfaEnabled
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-slate-100 text-slate-600 border-slate-200'
            }`}>
              {mfaEnabled ? 'ON' : 'OFF'}
            </span>
          </div>

          {/* Enrollment step 1: show provisioning URI for the authenticator app */}
          {mfaPanel === 'enroll' && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <p className="text-[11px] text-slate-600">
                Scan this provisioning URI with your authenticator app (Google Authenticator, Authy, 1Password…),
                then enter the 6-digit code it shows.
              </p>
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 break-all font-mono text-[11px] text-slate-800 select-all">
                {mfaQrUri}
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="6-digit code"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                />
                <button
                  onClick={verifyMfaEnrollment}
                  disabled={mfaBusy || mfaCode.trim().length < 6}
                  className="px-4 py-2 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] text-slate-950 text-xs font-bold disabled:opacity-50"
                >
                  Verify & Enable
                </button>
              </div>
            </div>
          )}

          {/* One-time recovery codes reveal */}
          {mfaPanel === 'codes' && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <p className="text-[11px] text-slate-600">
                Save these single-use recovery codes somewhere safe. Each works once if you lose your
                authenticator. <span className="font-bold text-slate-800">They will never be shown again.</span>
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
                I've saved my codes
              </button>
            </div>
          )}

          {/* Disable flow: requires password re-authentication */}
          {mfaPanel === 'disable' && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <p className="text-[11px] text-slate-600">
                Re-enter your password to disable two-factor authentication.
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="password"
                  placeholder="Current password"
                  value={mfaPassword}
                  onChange={(e) => setMfaPassword(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-rose-400"
                />
                <button
                  onClick={disableMfa}
                  disabled={mfaBusy || !mfaPassword}
                  className="px-4 py-2 rounded-xl border border-rose-200 hover:bg-rose-50 text-xs font-semibold text-rose-600 disabled:opacity-50"
                >
                  Disable MFA
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
                  Enable MFA
                </button>
              ) : (
                <>
                  <button
                    onClick={regenerateMfaCodes}
                    disabled={mfaBusy}
                    className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-800 disabled:opacity-50"
                  >
                    Regenerate recovery codes
                  </button>
                  <button
                    onClick={() => { setMfaPassword(''); setMfaPanel('disable'); }}
                    disabled={mfaBusy}
                    className="px-4 py-2 rounded-xl border border-rose-200 hover:bg-rose-50 text-xs font-semibold text-rose-600 disabled:opacity-50"
                  >
                    Disable MFA
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* GDPR & Privacy Controls */}
      <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
        <h3 className="font-serif text-base font-bold text-[#1B1F3B] pb-2 border-b border-slate-100">
          Privacy, Consents & GDPR Compliance
        </h3>

        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 pt-1">
          <div>
            <div className="text-xs font-bold text-slate-900">Export All Account & Biometric Data (GDPR)</div>
            <div className="text-[11px] text-slate-500 font-light">Download a complete structured JSON archive of your style profile, fit logs, and purchase history.</div>
          </div>
          <button
            onClick={handleGdprExport}
            className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-800 transition-all shrink-0"
          >
            Export JSON Archive
          </button>
        </div>

        {isAuthenticated && (
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 pt-3 border-t border-slate-100">
            <div>
              <div className="text-xs font-bold text-rose-600">Delete Account & Biometrics</div>
              <div className="text-[11px] text-slate-500 font-light">Irrevocably erase your style profile, uploaded photos, and fit models from CONFIT servers.</div>
            </div>
            <button
              onClick={handleDeleteAccount}
              className="px-4 py-2 rounded-xl border border-rose-200 hover:bg-rose-50 text-xs font-semibold text-rose-600 transition-all shrink-0"
            >
              Permanently Erase
            </button>
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
                  Step {quizStep} of 5
                </span>
                <h3 className="font-serif text-base font-bold text-white">
                  CONFIT Style Profile Wizard
                </h3>
              </div>
              <button onClick={() => setIsQuizOpen(false)} className="text-slate-300 hover:text-white">
                ✕
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {quizStep === 1 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-bold text-slate-900">What style aesthetics resonate with you?</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {['Smart Casual', 'Quiet Luxury', 'Modern Minimalist', 'Streetwear Tailored', 'Old Money', 'Bohemian Refined'].map((arch) => (
                      <button
                        key={arch}
                        onClick={() => {
                          if (archetypes.includes(arch)) setArchetypes(archetypes.filter((a) => a !== arch));
                          else setArchetypes([...archetypes, arch]);
                        }}
                        className={`p-3 rounded-2xl border text-xs font-semibold transition-all text-left ${
                          archetypes.includes(arch)
                            ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]'
                            : 'border-slate-200 text-slate-700'
                        }`}
                      >
                        {arch}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {quizStep === 2 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-bold text-slate-900">Select your core color palette:</h4>
                  <div className="grid grid-cols-3 gap-2">
                    {['Navy', 'Beige', 'Black', 'White', 'Forest Green', 'Ivory', 'Burgundy', 'Camel', 'Charcoal'].map((col) => (
                      <button
                        key={col}
                        onClick={() => {
                          if (colors.includes(col)) setColors(colors.filter((c) => c !== col));
                          else setColors([...colors, col]);
                        }}
                        className={`p-2.5 rounded-xl border text-xs font-semibold text-center transition-all ${
                          colors.includes(col)
                            ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]'
                            : 'border-slate-200 text-slate-700'
                        }`}
                      >
                        {col}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {quizStep === 3 && (
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-bold text-slate-900">Body measurements (optional)</h4>
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        Encrypted at rest with Fernet AES-256. Used only for AI sizing;
                        never shared with brands without your consent. You can skip this
                        step entirely.
                      </p>
                    </div>
                    {bodyTouched && (
                      <button
                        type="button"
                        onClick={() => { setHeight(null); setWeight(null); setShape(''); setBodyTouched(false); }}
                        className="text-[10px] font-semibold text-rose-500 hover:underline shrink-0"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-bold text-slate-700 block mb-1">Height (cm)</label>
                      <input
                        type="number"
                        min={100} max={250}
                        value={height ?? ''}
                        onChange={(e) => { setHeight(e.target.value ? Number(e.target.value) : null); setBodyTouched(true); }}
                        placeholder="e.g. 178"
                        className="w-full p-2.5 rounded-xl border border-slate-200 text-xs"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-bold text-slate-700 block mb-1">Weight (kg)</label>
                      <input
                        type="number"
                        min={30} max={250}
                        value={weight ?? ''}
                        onChange={(e) => { setWeight(e.target.value ? Number(e.target.value) : null); setBodyTouched(true); }}
                        placeholder="e.g. 72"
                        className="w-full p-2.5 rounded-xl border border-slate-200 text-xs"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 block mb-1">Silhouette shape</label>
                    <select
                      value={shape}
                      onChange={(e) => { setShape(e.target.value); setBodyTouched(true); }}
                      className="w-full p-2.5 rounded-xl border border-slate-200 text-xs bg-white"
                    >
                      <option value="">Select (optional)…</option>
                      <option value="Athletic">Athletic</option>
                      <option value="Hourglass">Hourglass</option>
                      <option value="Rectangle">Rectangle</option>
                      <option value="Pear">Pear</option>
                      <option value="Inverted Triangle">Inverted Triangle</option>
                      <option value="Apple">Apple</option>
                    </select>
                  </div>
                  <div className="grid grid-cols-3 gap-3 pt-2 border-t border-slate-100">
                    <div>
                      <label className="text-[10px] font-bold text-slate-700 block mb-1">Tops size</label>
                      <select value={sizeTop} onChange={(e) => setSizeTop(e.target.value)} className="w-full p-2 rounded-xl border border-slate-200 text-xs bg-white">
                        <option value="">—</option>
                        {['XS','S','M','L','XL','XXL'].map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] font-bold text-slate-700 block mb-1">Bottoms</label>
                      <select value={sizeBottom} onChange={(e) => setSizeBottom(e.target.value)} className="w-full p-2 rounded-xl border border-slate-200 text-xs bg-white">
                        <option value="">—</option>
                        {['28','30','32','34','36','38','40','42'].map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] font-bold text-slate-700 block mb-1">Shoes (EU)</label>
                      <select value={sizeShoes} onChange={(e) => setSizeShoes(e.target.value)} className="w-full p-2 rounded-xl border border-slate-200 text-xs bg-white">
                        <option value="">—</option>
                        {['36','37','38','39','40','41','42','43','44','45','46'].map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-700 block mb-1">Preferred fit</label>
                    <div className="grid grid-cols-4 gap-2">
                      {(['slim','regular','oversized','relaxed'] as const).map(f => (
                        <button
                          key={f}
                          type="button"
                          onClick={() => setFitPref(f)}
                          className={`p-2 rounded-xl border text-[11px] font-semibold capitalize transition-all ${
                            fitPref === f ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]' : 'border-slate-200 text-slate-700'
                          }`}
                        >
                          {f}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {quizStep === 4 && (
                <div className="space-y-4">
                  <h4 className="text-sm font-bold text-slate-900">Budget & occasions</h4>

                  <div>
                    <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                      <span>Monthly budget (min)</span>
                      <span className="text-[#A37E44]">${budgetMonthlyMin ?? '—'}</span>
                    </div>
                    <input type="range" min={0} max={2000} step={50}
                      value={budgetMonthlyMin ?? 0}
                      onChange={(e) => setBudgetMonthlyMin(Number(e.target.value))}
                      className="w-full accent-[#C5A059]" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                      <span>Monthly budget (max)</span>
                      <span className="text-[#A37E44]">${budgetMonthlyMax ?? '—'}</span>
                    </div>
                    <input type="range" min={0} max={5000} step={50}
                      value={budgetMonthlyMax ?? 0}
                      onChange={(e) => setBudgetMonthlyMax(Number(e.target.value))}
                      className="w-full accent-[#C5A059]" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                      <span>Max per outfit</span>
                      <span className="text-[#A37E44]">${budgetOutfitMax ?? '—'}</span>
                    </div>
                    <input type="range" min={50} max={2000} step={25}
                      value={budgetOutfitMax ?? 0}
                      onChange={(e) => setBudgetOutfitMax(Number(e.target.value))}
                      className="w-full accent-[#C5A059]" />
                  </div>

                  <div className="pt-2 border-t border-slate-100">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2">
                      How you spend your week (must sum to 1.0)
                    </span>
                    <div className="grid grid-cols-2 gap-2">
                      {['work','casual','party','formal','sports','travel'].map(occ => (
                        <label key={occ} className="flex items-center gap-2 text-xs">
                          <span className="w-16 capitalize text-slate-700">{occ}</span>
                          <input
                            type="number"
                            step="0.05"
                            min="0"
                            max="1"
                            value={occasionWeights[occ] ?? 0}
                            onChange={(e) => setOccasionWeights({ ...occasionWeights, [occ]: Number(e.target.value) })}
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
                    Also — colours to AVOID
                  </span>
                  <div className="grid grid-cols-3 gap-2">
                    {['Neon Orange','Magenta','Neon Yellow','Fluoro Pink','Lime','Turquoise'].map(col => (
                      <button key={col} type="button"
                        onClick={() => setAvoidedColors(avoidedColors.includes(col) ? avoidedColors.filter(c=>c!==col) : [...avoidedColors, col])}
                        className={`p-2 rounded-xl border text-xs font-semibold ${avoidedColors.includes(col) ? 'border-rose-400 bg-rose-50 text-rose-700' : 'border-slate-200 text-slate-700'}`}>
                        {col}
                      </button>
                    ))}
                  </div>
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block pt-2">
                    Fashion aesthetics
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {['Old Money','Quiet Luxury','Modern Tailored','Streetwear','Minimalist','Preppy','Athleisure','Y2K','Dark Academia','Cottagecore'].map(a => (
                      <button key={a} type="button"
                        onClick={() => setAesthetics(aesthetics.includes(a) ? aesthetics.filter(x=>x!==a) : [...aesthetics, a])}
                        className={`px-3 py-1.5 rounded-xl border text-[11px] font-semibold ${aesthetics.includes(a) ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]' : 'border-slate-200 text-slate-700'}`}>
                        {a}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {quizStep === 5 && (
                <div className="space-y-4">
                  <h4 className="text-sm font-bold text-slate-900">Brands, privacy & consent</h4>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2">Preferred brands</span>
                    <div className="flex flex-wrap gap-2">
                      {['Massimo Dutti','COS','Reiss','Arket','Zara','H&M','Uniqlo'].map(b => (
                        <button key={b} type="button"
                          onClick={() => setPreferredBrands(preferredBrands.includes(b) ? preferredBrands.filter(x=>x!==b) : [...preferredBrands, b])}
                          className={`px-3 py-1.5 rounded-xl border text-[11px] font-semibold ${preferredBrands.includes(b) ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]' : 'border-slate-200 text-slate-700'}`}>
                          {b}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2">Blacklist (never recommend)</span>
                    <div className="flex flex-wrap gap-2">
                      {['Shein','Fast Fashion','Fur','Leather'].map(b => (
                        <button key={b} type="button"
                          onClick={() => setBlacklistedBrands(blacklistedBrands.includes(b) ? blacklistedBrands.filter(x=>x!==b) : [...blacklistedBrands, b])}
                          className={`px-3 py-1.5 rounded-xl border text-[11px] font-semibold ${blacklistedBrands.includes(b) ? 'border-rose-400 bg-rose-50 text-rose-700' : 'border-slate-200 text-slate-700'}`}>
                          {b}
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
                      <span>Allow session retention of VTON models for instant 1-click try-on</span>
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
                  ← Back
                </button>
              ) : <div />}

              {quizStep < 5 ? (
                <button
                  onClick={() => setQuizStep(quizStep + 1)}
                  className="px-5 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-semibold"
                >
                  Next Step →
                </button>
              ) : (
                <button
                  onClick={handleSaveQuiz}
                  className="px-5 py-2 rounded-xl bg-[#C5A059] text-slate-950 font-bold text-xs"
                >
                  Finish & Save Profile
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
