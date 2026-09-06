import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { useCatalogViewModel } from '../../viewmodels/useCatalogViewModel';
import { useUIStore } from '../../stores/uiStore';
import { useAuthStore } from '../../stores/authStore';
import { tryOnService } from '../../services/apiServices';
import { measurementService } from '../../services/measurementService';
import { NoPhotoFitResult, Product } from '../../models';
import { RulerIcon, SparkleIcon, TryOnIcon } from '../../components/icons/ConfitIcons';
import { FitScoreBadge } from '../../components/common/CommonComponents';

/**
 * FIT-01 — dedicated Fit Finder page at /fit.
 *
 * Audit 2026-09-05: "/fit renders the Virtual Try-On Studio instead of a
 * measurement engine; the product's name and promise do not match what the
 * user sees." This view is the no-photo measurement engine the route always
 * promised: real anthropometric inputs (height / weight / chest / waist /
 * hip / body shape / preferred fit), server-side size recommendation via
 * POST /tryon/no-photo-fit (brand ease curves + fit breakdown + confidence
 * + return risk), an optional privacy-preserving save of the measurement
 * result to the caller's profile, and honest loading / error states.
 *
 * The Try-On Studio stays at /tryon-studio; nothing on this page opens a
 * camera or renders garment overlays.
 */

type Units = 'metric' | 'imperial';

const CM_PER_IN = 2.54;
const KG_PER_LB = 0.453592;

const BODY_SHAPES = ['Hourglass', 'Athletic', 'Rectangle', 'Pear', 'Inverted Triangle'];
const FIT_PREFS = [
  { value: 'slim', label: 'Slim / Tailored' },
  { value: 'regular', label: 'Regular' },
  { value: 'relaxed', label: 'Relaxed' },
];

interface FormState {
  heightCm: number;
  weightKg: number;
  chestCm: number | null;
  waistCm: number | null;
  hipCm: number | null;
  bodyShape: string;
  preferredFit: string;
}

const DEFAULTS: FormState = {
  heightCm: 178,
  weightKg: 72,
  chestCm: 98,
  waistCm: 82,
  hipCm: 96,
  bodyShape: 'Athletic',
  preferredFit: 'regular',
};

/** Input bounds mirror the backend contract (schemas/tryon.py). */
const LIMITS = {
  height: { min: 100, max: 250 },
  weight: { min: 30, max: 250 },
  girth: { min: 40, max: 200 },
};

export const FitFinderView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { products, isLoading: catalogLoading } = useCatalogViewModel();
  const { showToast } = useUIStore();
  const { isAuthenticated } = useAuthStore();

  const [units, setUnits] = useState<Units>('metric');
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [result, setResult] = useState<NoPhotoFitResult | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  /** Convert display units -> the cm/kg contract the API expects. */
  const payload = useMemo(() => {
    const toCm = (v: number | null) =>
      v === null ? null : Math.round((units === 'metric' ? v : v * CM_PER_IN) * 10) / 10;
    const heightCm = units === 'metric' ? form.heightCm : form.heightCm * CM_PER_IN;
    const weightKg = units === 'metric' ? form.weightKg : form.weightKg * KG_PER_LB;
    return {
      height_cm: Math.round(heightCm * 10) / 10,
      weight_kg: Math.round(weightKg * 10) / 10,
      chest_cm: toCm(form.chestCm),
      waist_cm: toCm(form.waistCm),
      hip_cm: toCm(form.hipCm),
      body_shape: form.bodyShape,
      preferred_fit: form.preferredFit,
    };
  }, [form, units]);

  const validationErrors = useMemo(() => {
    const errs: Record<string, string> = {};
    if (payload.height_cm < LIMITS.height.min || payload.height_cm > LIMITS.height.max)
      errs.height = `Height must be ${LIMITS.height.min}–${LIMITS.height.max} cm`;
    if (payload.weight_kg < LIMITS.weight.min || payload.weight_kg > LIMITS.weight.max)
      errs.weight = `Weight must be ${LIMITS.weight.min}–${LIMITS.weight.max} kg`;
    for (const key of ['chest_cm', 'waist_cm', 'hip_cm'] as const) {
      const v = payload[key];
      if (v !== null && (v < LIMITS.girth.min || v > LIMITS.girth.max))
        errs[key] = 'Value out of plausible range (40–200 cm)';
    }
    return errs;
  }, [payload]);

  const handleCalculate = async () => {
    if (!selectedProduct) {
      showToast('Select a garment to size first.', 'error');
      return;
    }
    if (Object.keys(validationErrors).length > 0) {
      showToast('Fix the highlighted measurement fields first.', 'error');
      return;
    }
    setCalcLoading(true);
    setCalcError(null);
    setResult(null);
    setSaveState('idle');
    try {
      const res = await tryOnService.calculateNoPhotoFit({
        product_id: selectedProduct.id,
        ...payload,
      });
      setResult(res);
    } catch (err: any) {
      setCalcError(err?.message || 'The sizing engine could not process these measurements.');
    } finally {
      setCalcLoading(false);
    }
  };

  /** Optional save — only with an authenticated account, manual capture mode,
   * explicit user action (consent is the click itself, sent as true). */
  const handleSave = async () => {
    if (!isAuthenticated) return;
    setSaveState('saving');
    try {
      const session = await measurementService.createSession('manual', true);
      await measurementService.submitResults(session.id, {
        height_cm: payload.height_cm,
        chest_cm: payload.chest_cm ?? undefined,
        waist_cm: payload.waist_cm ?? undefined,
        hip_cm: payload.hip_cm ?? undefined,
        body_shape: payload.body_shape,
        confidence_score: 100,
        calibration_method: 'manual_entry',
        source: 'fit_finder_manual',
      });
      setSaveState('saved');
      showToast('Measurements saved to your profile.', 'success');
    } catch (err: any) {
      setSaveState('error');
      showToast(err?.message || 'Could not save measurements.', 'error');
    }
  };

  const displayCm = (v: number | null) =>
    v === null ? '—' : units === 'metric' ? `${v} cm` : `${Math.round((v / CM_PER_IN) * 10) / 10} in`;
  const displayHeight = units === 'metric' ? `${form.heightCm} cm` : `${form.heightCm} in`;
  const displayWeight = units === 'metric' ? `${form.weightKg} kg` : `${form.weightKg} lbs`;

  const numberField = (
    key: 'chestCm' | 'waistCm' | 'hipCm',
    label: string
  ) => {
    const errKey = `${key.slice(0, -2)}_cm` as 'chest_cm' | 'waist_cm' | 'hip_cm';
    return (
      <div>
        <label htmlFor={`fit-${key}`} className="text-xs font-bold text-slate-800 block mb-1">
          {label} <span className="text-slate-400 font-light">(optional)</span>
        </label>
        <div className="flex items-center gap-2">
          <input
            id={`fit-${key}`}
            type="number"
            inputMode="decimal"
            min={units === 'metric' ? LIMITS.girth.min : Math.round(LIMITS.girth.min / CM_PER_IN)}
            max={units === 'metric' ? LIMITS.girth.max : Math.round(LIMITS.girth.max / CM_PER_IN)}
            value={form[key] ?? ''}
            onChange={(e) =>
              set(key, e.target.value === '' ? null : Number(e.target.value))
            }
            className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
          />
          <span className="text-[10px] text-slate-400 font-semibold w-6">
            {units === 'metric' ? 'cm' : 'in'}
          </span>
        </div>
        {validationErrors[errKey] && (
          <p className="text-[10px] text-rose-600 mt-1">{validationErrors[errKey]}</p>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-8 pb-20">
      {/* Header — clearly the measurement engine, not the try-on studio */}
      <div className="bg-gradient-to-r from-[#1B1F3B] to-[#0C0E1E] rounded-3xl text-white p-8 sm:p-10 shadow-xl border border-slate-800">
        <div className="max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#C5A059]/20 border border-[#C5A059]/40 text-[#E2BF70] text-xs font-semibold uppercase tracking-wider">
            <RulerIcon size={14} color="#E2BF70" />
            <span>Fit Finder — No Photo Required</span>
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold leading-tight">
            Size Recommendation Engine
          </h1>
          <p className="text-xs sm:text-sm text-slate-300 font-light leading-relaxed">
            Enter your measurements and CONFIT computes your size for a specific garment using
            brand-specific ease curves — with a confidence score, a per-region fit breakdown and
            a return-risk estimate. No photo, no camera, no upload: numbers in, size out.
          </p>
          <p className="text-[11px] text-slate-400">
            Looking for the photo-based studio instead?{' '}
            <button
              onClick={() => navigate('/tryon-studio')}
              className="text-[#C5A059] font-semibold hover:underline inline-flex items-center gap-1"
            >
              Open Virtual Try-On <TryOnIcon size={12} color="#C5A059" />
            </button>
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        {/* Inputs (3 cols) */}
        <div className="lg:col-span-3 space-y-6">
          {/* Garment selector */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-5 shadow-2xs space-y-3">
            <h3 className="font-serif text-base font-bold text-[#1B1F3B] flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-[#1B1F3B] text-white text-[11px] flex items-center justify-center font-sans font-bold">1</span>
              Choose the garment to size
            </h3>
            {catalogLoading ? (
              <div className="h-10 rounded-xl bg-slate-100 animate-pulse" aria-label="Loading catalog" />
            ) : (
              <select
                aria-label="Garment to size"
                value={selectedProduct?.id ?? ''}
                onChange={(e) => {
                  const p = products.find((x) => String(x.id) === e.target.value) || null;
                  setSelectedProduct(p);
                  setResult(null);
                  setCalcError(null);
                }}
                className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-xs font-semibold focus:outline-none focus:border-[#C5A059]"
              >
                <option value="">— Select a product —</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.brand_name} · {p.title} (${p.base_price})
                  </option>
                ))}
              </select>
            )}
            {selectedProduct && (
              <p className="text-[11px] text-slate-500 font-light">
                Brand sizing tendency will be applied from{' '}
                <span className="font-semibold text-slate-700">{selectedProduct.brand_name}</span>'s
                catalogue profile.
              </p>
            )}
          </div>

          {/* Measurements form */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-5 shadow-2xs space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-serif text-base font-bold text-[#1B1F3B] flex items-center gap-2">
                <span className="w-6 h-6 rounded-lg bg-[#1B1F3B] text-white text-[11px] flex items-center justify-center font-sans font-bold">2</span>
                Your measurements
              </h3>
              {/* Units toggle */}
              <div className="flex items-center bg-slate-100 rounded-xl p-1 text-[11px] font-bold">
                <button
                  type="button"
                  onClick={() => setUnits('metric')}
                  aria-pressed={units === 'metric'}
                  className={`px-3 py-1 rounded-lg transition-all ${units === 'metric' ? 'bg-white shadow-2xs text-[#1B1F3B]' : 'text-slate-500'}`}
                >
                  cm / kg
                </button>
                <button
                  type="button"
                  onClick={() => setUnits('imperial')}
                  aria-pressed={units === 'imperial'}
                  className={`px-3 py-1 rounded-lg transition-all ${units === 'imperial' ? 'bg-white shadow-2xs text-[#1B1F3B]' : 'text-slate-500'}`}
                >
                  in / lbs
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="fit-height" className="text-xs font-bold text-slate-800 block mb-1">
                  Height
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id="fit-height"
                    type="number"
                    inputMode="decimal"
                    min={units === 'metric' ? LIMITS.height.min : Math.round(LIMITS.height.min / CM_PER_IN)}
                    max={units === 'metric' ? LIMITS.height.max : Math.round(LIMITS.height.max / CM_PER_IN)}
                    value={form.heightCm}
                    onChange={(e) => set('heightCm', Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                  />
                  <span className="text-[10px] text-slate-400 font-semibold w-6">
                    {units === 'metric' ? 'cm' : 'in'}
                  </span>
                </div>
                {units === 'metric' && (
                  <p className="text-[10px] text-slate-400 mt-1">
                    ≈ {Math.floor(form.heightCm / 30.48)}'{Math.round((form.heightCm % 30.48) / 2.54)}"
                  </p>
                )}
                {validationErrors.height && (
                  <p className="text-[10px] text-rose-600 mt-1">{validationErrors.height}</p>
                )}
              </div>

              <div>
                <label htmlFor="fit-weight" className="text-xs font-bold text-slate-800 block mb-1">
                  Weight
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id="fit-weight"
                    type="number"
                    inputMode="decimal"
                    min={units === 'metric' ? LIMITS.weight.min : Math.round(LIMITS.weight.min / KG_PER_LB)}
                    max={units === 'metric' ? LIMITS.weight.max : Math.round(LIMITS.weight.max / KG_PER_LB)}
                    value={form.weightKg}
                    onChange={(e) => set('weightKg', Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                  />
                  <span className="text-[10px] text-slate-400 font-semibold w-6">
                    {units === 'metric' ? 'kg' : 'lbs'}
                  </span>
                </div>
                {validationErrors.weight && (
                  <p className="text-[10px] text-rose-600 mt-1">{validationErrors.weight}</p>
                )}
              </div>

              {numberField('chestCm', 'Chest / Bust')}
              {numberField('waistCm', 'Waist')}
              {numberField('hipCm', 'Hip')}

              <div>
                <label htmlFor="fit-shape" className="text-xs font-bold text-slate-800 block mb-1">
                  Body shape
                </label>
                <select
                  id="fit-shape"
                  value={form.bodyShape}
                  onChange={(e) => set('bodyShape', e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                >
                  {BODY_SHAPES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <span className="text-xs font-bold text-slate-800 block mb-1">Preferred fit</span>
              <div className="grid grid-cols-3 gap-2">
                {FIT_PREFS.map((f) => (
                  <button
                    key={f.value}
                    type="button"
                    onClick={() => set('preferredFit', f.value)}
                    aria-pressed={form.preferredFit === f.value}
                    className={`py-2 rounded-xl border text-[11px] font-bold transition-all ${
                      form.preferredFit === f.value
                        ? 'border-[#C5A059] bg-[#FDF8EE] text-[#A37E44]'
                        : 'border-slate-200 text-slate-600 hover:border-slate-300'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={handleCalculate}
              disabled={calcLoading || !selectedProduct}
              className="w-full py-3.5 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
            >
              <RulerIcon size={16} color="#C5A059" />
              <span>{calcLoading ? 'Computing your size…' : 'Calculate My Size'}</span>
            </button>
            <p className="text-[10px] text-slate-400 text-center font-light">
              Sent as anonymous numbers over HTTPS. Nothing is stored unless you choose “Save”.
            </p>
          </div>
        </div>

        {/* Results (2 cols) */}
        <div className="lg:col-span-2 space-y-6">
          {calcLoading && (
            <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-3" role="status" aria-live="polite">
              <div className="h-8 w-32 rounded-lg bg-slate-100 animate-pulse" />
              <div className="h-4 w-full rounded bg-slate-100 animate-pulse" />
              <div className="h-4 w-5/6 rounded bg-slate-100 animate-pulse" />
              <p className="text-[11px] text-slate-400">Applying brand ease curves…</p>
            </div>
          )}

          {calcError && !calcLoading && (
            <div className="bg-rose-50 border border-rose-200 rounded-3xl p-6 space-y-2" role="alert">
              <h3 className="font-serif text-base font-bold text-rose-800">Size engine error</h3>
              <p className="text-xs text-rose-700 leading-relaxed">{calcError}</p>
              <button
                onClick={handleCalculate}
                className="mt-1 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-[11px] font-bold"
              >
                Try again
              </button>
            </div>
          )}

          {!result && !calcLoading && !calcError && (
            <div className="bg-[#FAF9F6] rounded-3xl border border-dashed border-slate-300 p-6 text-center space-y-2">
              <RulerIcon size={26} color="#94A3B8" />
              <h3 className="font-serif text-base font-bold text-slate-700">Your recommendation lands here</h3>
              <p className="text-[11px] text-slate-500 font-light leading-relaxed">
                Pick a garment, enter your measurements, and the engine returns a size with its
                reasoning — chest/waist/hip fit per size, brand tendency and return risk.
              </p>
            </div>
          )}

          {result && !calcLoading && (
            <div className="bg-white rounded-3xl border-2 border-[#C5A059]/50 p-6 shadow-md space-y-4" aria-live="polite">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                    Recommended size
                  </p>
                  <p className="font-serif text-5xl font-black text-[#1B1F3B] leading-tight">
                    {result.recommended_size}
                  </p>
                  <p className="text-[11px] text-slate-500 font-light">
                    for {selectedProduct?.brand_name} · {selectedProduct?.title}
                  </p>
                </div>
                <FitScoreBadge
                  score={result.confidence_score}
                  verdict={`${result.confidence_score}% confidence`}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-[#FAF9F6] rounded-2xl p-3 border border-slate-100">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Brand tendency</p>
                  <p className="text-xs text-slate-700 font-semibold mt-1">{result.brand_sizing_tendency}</p>
                </div>
                <div className="bg-[#FAF9F6] rounded-2xl p-3 border border-slate-100">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Return risk</p>
                  <p className="text-xs text-slate-700 font-semibold mt-1">{result.return_risk_score}</p>
                </div>
              </div>

              {/* Fit breakdown — the WHY */}
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                  Why this size
                </p>
                <ul className="space-y-1.5">
                  {Object.entries(result.fit_breakdown).map(([region, verdict]) => (
                    <li key={region} className="flex gap-2 text-xs text-slate-600 bg-[#FAF9F6] rounded-xl px-3 py-2 border border-slate-100">
                      <SparkleIcon size={13} color="#C5A059" />
                      <span>
                        <span className="font-bold capitalize text-slate-800">{region.replace(/_/g, ' ')}:</span>{' '}
                        {verdict}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Size comparison table */}
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="text-slate-400 uppercase tracking-wider text-[9px]">
                      <th className="text-left py-1">Size</th>
                      <th className="text-left py-1">Chest</th>
                      <th className="text-left py-1">Waist</th>
                      <th className="text-left py-1">Fit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.size_comparison_table.map((row) => {
                      const isRec = row.size === result.recommended_size;
                      return (
                        <tr
                          key={row.size}
                          className={`border-t border-slate-100 ${isRec ? 'bg-[#FDF8EE] font-bold text-[#1B1F3B]' : 'text-slate-600'}`}
                        >
                          <td className="py-1.5">{row.size}{isRec ? ' ←' : ''}</td>
                          <td className="py-1.5">{row.chest}</td>
                          <td className="py-1.5">{row.waist}</td>
                          <td className="py-1.5">{row.fit_rating}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Optional save + add to bag */}
              <div className="pt-3 border-t border-slate-100 space-y-2">
                {isAuthenticated ? (
                  <button
                    onClick={handleSave}
                    disabled={saveState === 'saving' || saveState === 'saved'}
                    className="w-full py-2.5 rounded-xl border border-[#C5A059]/50 text-[#A37E44] hover:bg-[#FDF8EE] disabled:opacity-50 text-[11px] font-bold transition-all"
                  >
                    {saveState === 'saving'
                      ? 'Saving…'
                      : saveState === 'saved'
                        ? '✓ Saved to your profile'
                        : 'Save these measurements to my profile'}
                  </button>
                ) : (
                  <p className="text-[10px] text-slate-400 text-center">
                    <Link to="/" onClick={() => useUIStore.getState().openAuthModal('login')} className="text-[#C5A059] font-bold hover:underline">
                      Sign in
                    </Link>{' '}
                    to keep your measurements for next time (optional — the size works without an account).
                  </p>
                )}
                <button
                  onClick={() => navigate(`/product/${selectedProduct?.slug}`)}
                  className="w-full py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-[11px] font-bold transition-all"
                >
                  Open {selectedProduct?.brand_name} product page
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
