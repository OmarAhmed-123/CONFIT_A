import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { profileService, authService } from '../../services/apiServices';
import { UserStyleProfile } from '../../models';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { SparkleIcon, UserIcon, RulerIcon } from '../../components/icons/ConfitIcons';
import { LoadingSpinner } from '../../components/common/CommonComponents';

export const UserProfileView: React.FC = () => {
  const { t } = useTranslation();
  const { user, isAuthenticated, logout } = useAuthStore();
  const { showToast, openAuthModal } = useUIStore();

  const [usp, setUsp] = useState<UserStyleProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [quizStep, setQuizStep] = useState(1);
  const [isQuizOpen, setIsQuizOpen] = useState(false);

  // Quiz Form State (5-Step Onboarding Wizard)
  const [archetypes, setArchetypes] = useState<string[]>(['Smart Casual', 'Quiet Luxury']);
  const [colors, setColors] = useState<string[]>(['Navy', 'Beige', 'Black', 'White']);
  const [budgetMonthlyMax, setBudgetMonthlyMax] = useState(1200);
  const [budgetOutfitMax, setBudgetOutfitMax] = useState(400);
  const [height, setHeight] = useState(178);
  const [weight, setWeight] = useState(72);
  const [shape, setShape] = useState('Athletic');
  const [sizeTop, setSizeTop] = useState('M');
  const [sizeBottom, setSizeBottom] = useState('32');
  const [fitPref, setFitPref] = useState('regular');
  const [consentTryon, setConsentTryon] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    // Profile API is requested with optional guest fallback (Section 5.2)
    profileService
      .getUSP()
      .then((data) => {
        setUsp(data);
        if (data) {
          setArchetypes(data.style_archetypes || ['Smart Casual', 'Quiet Luxury']);
          setColors(data.preferred_colors || ['Navy', 'Beige']);
          setBudgetMonthlyMax(data.budget_monthly_max || 1200);
          setBudgetOutfitMax(data.budget_per_outfit_max || 400);
          setSizeTop(data.size_tops || 'M');
          setSizeBottom(data.size_bottoms || '32');
          setFitPref(data.fit_preference || 'regular');
          setConsentTryon(data.privacy_consent_tryon_storage || false);
        }
        setIsLoading(false);
      })
      .catch((err) => {
        setIsLoading(false);
        // Do not show noisy auth error toasts for guests
        if (isAuthenticated) {
          showToast('Profile sync: ' + err.message, 'info');
        }
      });
  }, [isAuthenticated, showToast]);

  const handleSaveQuiz = async () => {
    try {
      const updated = await profileService.submitQuiz({
        style_archetypes: archetypes,
        preferred_colors: colors,
        budget_monthly_min: 200,
        budget_monthly_max: budgetMonthlyMax,
        budget_per_outfit_max: budgetOutfitMax,
        size_tops: sizeTop,
        size_bottoms: sizeBottom,
        fit_preference: fitPref,
        body_attributes: {
          height_cm: height,
          weight_kg: weight,
          body_shape: shape,
        },
        privacy_consent_tryon_storage: consentTryon,
      });
      setUsp(updated);
      setIsQuizOpen(false);
      showToast('User Style Profile (USP) updated & encrypted!', 'success');
    } catch (err: any) {
      showToast('Save failed: ' + err.message, 'error');
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
          </div>
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
                  <h4 className="text-sm font-bold text-slate-900">Body measurements for AI sizing & scaling:</h4>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-bold text-slate-700 block mb-1">Height (cm)</label>
                      <input
                        type="number"
                        value={height}
                        onChange={(e) => setHeight(Number(e.target.value))}
                        className="w-full p-2.5 rounded-xl border border-slate-200 text-xs"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-bold text-slate-700 block mb-1">Weight (kg)</label>
                      <input
                        type="number"
                        value={weight}
                        onChange={(e) => setWeight(Number(e.target.value))}
                        className="w-full p-2.5 rounded-xl border border-slate-200 text-xs"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 block mb-1">Silhouette Shape</label>
                    <select
                      value={shape}
                      onChange={(e) => setShape(e.target.value)}
                      className="w-full p-2.5 rounded-xl border border-slate-200 text-xs bg-white"
                    >
                      <option value="Athletic">Athletic</option>
                      <option value="Hourglass">Hourglass</option>
                      <option value="Rectangle">Rectangle</option>
                      <option value="Pear">Pear</option>
                    </select>
                  </div>
                </div>
              )}

              {quizStep === 4 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-bold text-slate-900">Target Budget Constraints:</h4>
                  <div>
                    <div className="flex justify-between text-xs font-bold text-slate-800 mb-1">
                      <span>Max Budget per Outfit:</span>
                      <span className="text-[#A37E44]">${budgetOutfitMax}</span>
                    </div>
                    <input
                      type="range"
                      min="100"
                      max="1500"
                      step="50"
                      value={budgetOutfitMax}
                      onChange={(e) => setBudgetOutfitMax(Number(e.target.value))}
                      className="w-full accent-[#C5A059]"
                    />
                  </div>
                </div>
              )}

              {quizStep === 5 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-bold text-slate-900">Privacy & Try-On Preferences:</h4>
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
