import React, { useMemo, useRef, useState } from 'react';
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
 * The no-photo measurement engine the route always promised: real
 * anthropometric inputs, a server-side size recommendation, and — since the
 * 2026-09-21 remediation — an interface that tells the truth about the answer.
 *
 * What changed in this view, and why
 * ----------------------------------
 * * Units are no longer converted here. The client used to convert in/lb to
 *   cm/kg and send "metric"; the server now owns conversion and the request
 *   states its own unit system. Converting on both sides is how an inch value
 *   could be scored as centimetres.
 * * A refusal (`recommended === false`) is rendered as a first-class outcome
 *   with its reason and what would fix it. Previously the engine could not
 *   refuse, so the UI had no concept of "we cannot tell you" and would have
 *   shown a blank card.
 * * The recommendation card now shows the evidence: which chart was used, who
 *   published it and when, which of your measurements were used, which were
 *   ESTIMATED, and how the confidence number was built.
 * * "Between sizes" is surfaced explicitly instead of silently picking one.
 * * Saving to the profile asks for consent explicitly and only then creates a
 *   consent-granted measurement session.
 *
 * The Try-On Studio stays at /tryon-studio; nothing here opens a camera.
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
const DEMOGRAPHICS = [
  { value: 'unisex', label: 'Prefer not to say' },
  { value: 'men', label: "Men's sizing" },
  { value: 'women', label: "Women's sizing" },
] as const;

interface FormState {
  height: number;
  weight: number;
  chest: number | null;
  waist: number | null;
  hip: number | null;
  bodyShape: string;
  preferredFit: string;
  demographic: 'men' | 'women' | 'unisex';
}

/** Metric defaults. Switching units re-expresses them, never re-labels them. */
const DEFAULTS: FormState = {
  height: 178,
  weight: 72,
  chest: null,
  waist: null,
  hip: null,
  bodyShape: 'Athletic',
  preferredFit: 'regular',
  demographic: 'unisex',
};

/**
 * Client-side bounds mirror backend `services/fit/units.BOUNDS_CM`. They exist
 * to give instant feedback — the server re-checks every value and is the
 * authority, so a client bypass cannot produce a recommendation from nonsense.
 */
const LIMITS_CM = {
  height: { min: 100, max: 250 },
  chest: { min: 50, max: 200 },
  waist: { min: 40, max: 200 },
  hip: { min: 50, max: 200 },
};
const LIMITS_WEIGHT_KG = { min: 30, max: 300 };

const toDisplay = (cm: number, units: Units) =>
  units === 'metric' ? cm : Math.round((cm / CM_PER_IN) * 10) / 10;
const toDisplayWeight = (kg: number, units: Units) =>
  units === 'metric' ? kg : Math.round((kg / KG_PER_LB) * 10) / 10;

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
  // P1-01 hardening: request-sequence guard. If the user edits ANY input while
  // a calculate request is in flight, the late response must NOT resurrect a
  // recommendation computed from the OLD measurements (stale-async overwrite).
  const calcSeq = useRef(0);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveConsent, setSaveConsent] = useState(false);

  /** ANY input change invalidates the displayed recommendation. */
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setResult(null);
    setCalcError(null);
    calcSeq.current += 1; // invalidate any in-flight calculate response
  };

  /** Switching units re-expresses the SAME body, it does not reinterpret it. */
  const switchUnits = (next: Units) => {
    if (next === units) return;
    const round1 = (v: number) => Math.round(v * 10) / 10;
    const convertLength = (v: number | null) =>
      v === null ? null : round1(next === 'metric' ? v * CM_PER_IN : v / CM_PER_IN);
    const convertMass = (v: number) =>
      round1(next === 'metric' ? v * KG_PER_LB : v / KG_PER_LB);
    setForm((f) => ({
      ...f,
      height: convertLength(f.height) as number,
      weight: convertMass(f.weight),
      chest: convertLength(f.chest),
      waist: convertLength(f.waist),
      hip: convertLength(f.hip),
    }));
    setUnits(next);
    setResult(null);
    setCalcError(null);
    calcSeq.current += 1;
  };

  /** Bounds in the CURRENTLY displayed unit, for the inputs and messages. */
  const displayLimits = useMemo(
    () => ({
      height: {
        min: toDisplay(LIMITS_CM.height.min, units),
        max: toDisplay(LIMITS_CM.height.max, units),
      },
      weight: {
        min: toDisplayWeight(LIMITS_WEIGHT_KG.min, units),
        max: toDisplayWeight(LIMITS_WEIGHT_KG.max, units),
      },
      chest: { min: toDisplay(LIMITS_CM.chest.min, units), max: toDisplay(LIMITS_CM.chest.max, units) },
      waist: { min: toDisplay(LIMITS_CM.waist.min, units), max: toDisplay(LIMITS_CM.waist.max, units) },
      hip: { min: toDisplay(LIMITS_CM.hip.min, units), max: toDisplay(LIMITS_CM.hip.max, units) },
    }),
    [units]
  );

  const unitLabel = units === 'metric' ? 'cm' : 'in';
  const weightLabel = units === 'metric' ? 'kg' : 'lbs';

  const validationErrors = useMemo(() => {
    const errs: Record<string, string> = {};
    const check = (key: 'height' | 'chest' | 'waist' | 'hip', value: number | null) => {
      if (value === null) return;
      const { min, max } = displayLimits[key];
      if (value < min || value > max) {
        errs[key] = `Must be ${min}–${max} ${unitLabel}`;
      }
    };
    check('height', form.height);
    check('chest', form.chest);
    check('waist', form.waist);
    check('hip', form.hip);
    const { min, max } = displayLimits.weight;
    if (form.weight < min || form.weight > max) {
      errs.weight = `Must be ${min}–${max} ${weightLabel}`;
    }
    return errs;
  }, [form, displayLimits, unitLabel, weightLabel]);

  const measuredCount = [form.chest, form.waist, form.hip].filter((v) => v !== null).length;

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
    const mySeq = ++calcSeq.current;
    try {
      // Values are sent in the unit system the user picked. NO conversion here.
      const res = await tryOnService.calculateNoPhotoFit({
        product_id: selectedProduct.id,
        units,
        height: form.height,
        weight: form.weight,
        chest: form.chest,
        waist: form.waist,
        hip: form.hip,
        body_shape: form.bodyShape,
        preferred_fit: form.preferredFit,
        demographic: form.demographic,
      });
      if (calcSeq.current !== mySeq) return; // form changed mid-flight — drop it
      setResult(res);
    } catch (err: any) {
      if (calcSeq.current !== mySeq) return;
      const fields = err?.details?.error?.fields;
      setCalcError(
        fields
          ? `The server rejected these measurements: ${Object.values(fields).join('; ')}`
          : err?.message || 'The sizing engine could not process these measurements.'
      );
    } finally {
      if (calcSeq.current === mySeq) setCalcLoading(false);
    }
  };

  /**
   * Optional save. Consent is an explicit checkbox, not an assumption: the
   * session is only created once the user has ticked it, and the server
   * refuses to store measurements against a session that lacks consent.
   */
  const handleSave = async () => {
    if (!isAuthenticated || !saveConsent) return;
    setSaveState('saving');
    try {
      const session = await measurementService.createSession('manual', {
        consentGranted: true,
        saveToProfile: true,
      });
      await measurementService.submitResults(session.id, {
        units,
        ...(units === 'metric' ? { height_cm: form.height } : { height: form.height }),
        chest_cm: form.chest ?? undefined,
        waist_cm: form.waist ?? undefined,
        hip_cm: form.hip ?? undefined,
        body_shape: form.bodyShape,
        // Self-reported, typed by hand: this is NOT a measured-grade input and
        // must not claim to be one.
        confidence_score: 60,
        calibration_method: 'manual_entry',
        source: 'fit_finder_manual',
      });
      await measurementService.saveToProfile(session.id);
      setSaveState('saved');
      showToast('Measurements saved to your profile.', 'success');
    } catch (err: any) {
      setSaveState('error');
      showToast(err?.message || 'Could not save measurements.', 'error');
    }
  };

  const numberField = (
    key: 'chest' | 'waist' | 'hip',
    label: string
  ) => (
    <div>
      <label htmlFor={`fit-${key}`} className="text-xs font-bold text-slate-800 block mb-1">
        {label} <span className="text-slate-500 font-light">(optional)</span>
      </label>
      <div className="flex items-center gap-2">
        <input
          id={`fit-${key}`}
          type="number"
          inputMode="decimal"
          min={displayLimits[key].min}
          max={displayLimits[key].max}
          value={form[key] ?? ''}
          aria-invalid={Boolean(validationErrors[key])}
          aria-describedby={validationErrors[key] ? `fit-${key}-error` : undefined}
          onChange={(e) => set(key, e.target.value === '' ? null : Number(e.target.value))}
          className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
        />
        <span className="text-[10px] text-slate-500 font-semibold w-6">{unitLabel}</span>
      </div>
      {validationErrors[key] && (
        <p id={`fit-${key}-error`} className="text-[10px] text-rose-600 mt-1" role="alert">
          {validationErrors[key]}
        </p>
      )}
    </div>
  );

  const chartSource = result?.size_chart_source;

  return (
    <div className="space-y-8 pb-20">
      {/* Header */}
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
            Your measurements are compared against this garment's own size chart, section by
            section, using the ease the style is cut for. You get the size, the reasoning, and an
            honest confidence — and when the data is not good enough, you get told that instead of
            a guess.
          </p>
          <p className="text-[11px] text-slate-500">
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
        {/* Inputs */}
        <div className="lg:col-span-3 space-y-6">
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
                  calcSeq.current += 1;
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
                Sizing is computed against{' '}
                <span className="font-semibold text-slate-700">{selectedProduct.brand_name}</span>'s
                own chart when they publish one — the result below states which chart was used.
              </p>
            )}
          </div>

          {/* Measurements */}
          <div className="bg-white rounded-3xl border border-slate-200/80 p-5 shadow-2xs space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-serif text-base font-bold text-[#1B1F3B] flex items-center gap-2">
                <span className="w-6 h-6 rounded-lg bg-[#1B1F3B] text-white text-[11px] flex items-center justify-center font-sans font-bold">2</span>
                Your measurements
              </h3>
              <div className="flex items-center bg-slate-100 rounded-xl p-1 text-[11px] font-bold" role="group" aria-label="Unit system">
                <button
                  type="button"
                  onClick={() => switchUnits('metric')}
                  aria-pressed={units === 'metric'}
                  className={`px-3 py-1 rounded-lg transition-all ${units === 'metric' ? 'bg-white shadow-2xs text-[#1B1F3B]' : 'text-slate-600'}`}
                >
                  cm / kg
                </button>
                <button
                  type="button"
                  onClick={() => switchUnits('imperial')}
                  aria-pressed={units === 'imperial'}
                  className={`px-3 py-1 rounded-lg transition-all ${units === 'imperial' ? 'bg-white shadow-2xs text-[#1B1F3B]' : 'text-slate-600'}`}
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
                    min={displayLimits.height.min}
                    max={displayLimits.height.max}
                    value={form.height}
                    aria-invalid={Boolean(validationErrors.height)}
                    aria-describedby={validationErrors.height ? 'fit-height-error' : undefined}
                    onChange={(e) => set('height', Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                  />
                  <span className="text-[10px] text-slate-500 font-semibold w-6">{unitLabel}</span>
                </div>
                {validationErrors.height && (
                  <p id="fit-height-error" className="text-[10px] text-rose-600 mt-1" role="alert">
                    {validationErrors.height}
                  </p>
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
                    min={displayLimits.weight.min}
                    max={displayLimits.weight.max}
                    value={form.weight}
                    aria-invalid={Boolean(validationErrors.weight)}
                    aria-describedby={validationErrors.weight ? 'fit-weight-error' : undefined}
                    onChange={(e) => set('weight', Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                  />
                  <span className="text-[10px] text-slate-500 font-semibold w-6">{weightLabel}</span>
                </div>
                {validationErrors.weight && (
                  <p id="fit-weight-error" className="text-[10px] text-rose-600 mt-1" role="alert">
                    {validationErrors.weight}
                  </p>
                )}
              </div>

              {numberField('chest', 'Chest / Bust')}
              {numberField('waist', 'Waist')}
              {numberField('hip', 'Hip')}

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

              <div>
                <label htmlFor="fit-demographic" className="text-xs font-bold text-slate-800 block mb-1">
                  Size chart to use
                </label>
                <select
                  id="fit-demographic"
                  value={form.demographic}
                  onChange={(e) => set('demographic', e.target.value as FormState['demographic'])}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
                >
                  {DEMOGRAPHICS.map((d) => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Honest nudge: the engine is measurably better with real girths. */}
            <div
              className={`rounded-2xl px-3 py-2 text-[11px] leading-relaxed border ${
                measuredCount === 0
                  ? 'bg-amber-50 border-amber-200 text-amber-800'
                  : 'bg-[#FAF9F6] border-slate-200 text-slate-600'
              }`}
            >
              {measuredCount === 0 ? (
                <>
                  <strong>Height and weight alone can only estimate your girths.</strong> Add a
                  real chest, waist or hip measurement for a recommendation the engine can stand
                  behind — without them the result is explicitly labelled an estimate, and for some
                  garments it will decline to name a size at all.
                </>
              ) : (
                <>Using {measuredCount} measured girth{measuredCount > 1 ? 's' : ''}. Adding the rest raises confidence further.</>
              )}
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
                        ? 'border-[#C5A059] bg-[#FDF8EE] text-[#7A5C28]'
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
            <p className="text-[10px] text-slate-500 text-center font-light">
              Sent as anonymous numbers over HTTPS. Nothing is stored unless you choose “Save”.
            </p>
          </div>
        </div>

        {/* Results */}
        <div className="lg:col-span-2 space-y-6">
          {calcLoading && (
            <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-3" role="status" aria-live="polite">
              <div className="h-8 w-32 rounded-lg bg-slate-100 animate-pulse" />
              <div className="h-4 w-full rounded bg-slate-100 animate-pulse" />
              <div className="h-4 w-5/6 rounded bg-slate-100 animate-pulse" />
              <p className="text-[11px] text-slate-500">Comparing your measurements with the size chart…</p>
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
                Pick a garment and enter your measurements. You will see the size, the chart it came
                from, how each section fits, and how confident the engine actually is.
              </p>
            </div>
          )}

          {/* ── Refusal: a first-class, honest outcome ── */}
          {result && !result.recommended && !calcLoading && (
            <div
              className="bg-amber-50 border-2 border-amber-300 rounded-3xl p-6 space-y-3"
              role="status"
              aria-live="polite"
            >
              <h3 className="font-serif text-base font-bold text-amber-900">
                No size recommendation for this item
              </h3>
              <p className="text-xs text-amber-900 leading-relaxed">{result.confidence_disclosure}</p>
              {result.missing && result.missing.length > 0 && (
                <div className="bg-white/70 rounded-2xl px-3 py-2">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-amber-800 mb-1">
                    What would fix it
                  </p>
                  <ul className="text-[11px] text-amber-900 list-disc list-inside space-y-0.5">
                    {result.missing.map((m) => (
                      <li key={m}>{m.replace(/_cm$/, '').replace(/_/g, ' ')}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-[10px] text-amber-800">
                We would rather say nothing than name a size we cannot justify — a wrong size is a
                return, and a confident wrong size is worse.
                {result.reason_code ? ` (reason: ${result.reason_code})` : ''}
              </p>
            </div>
          )}

          {/* ── Recommendation ── */}
          {result && result.recommended && !calcLoading && (
            <div className="bg-white rounded-3xl border-2 border-[#C5A059]/50 p-6 shadow-md space-y-4" aria-live="polite">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
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
                  label="Confidence"
                  verdict={result.fit_verdict}
                />
              </div>

              {result.is_between_sizes && result.alternative_size && (
                <div className="bg-[#FDF8EE] border border-[#C5A059]/40 rounded-2xl px-3 py-2">
                  <p className="text-[11px] text-[#7A5C28] leading-relaxed">
                    <strong>You are between sizes.</strong> {result.recommended_size} for a closer
                    fit, {result.alternative_size} for more room.
                  </p>
                </div>
              )}

              {result.is_estimated && (
                <div className="bg-amber-50 border border-amber-200 rounded-2xl px-3 py-2">
                  <p className="text-[11px] text-amber-900 leading-relaxed">
                    <strong>Partly estimated.</strong> Some girths were modelled from your height
                    and weight rather than measured, which is why the confidence is capped.
                  </p>
                </div>
              )}

              {/* Provenance — which chart, whose, how fresh */}
              {chartSource && (
                <div className="bg-[#FAF9F6] rounded-2xl p-3 border border-slate-100">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    Size chart used
                  </p>
                  <p className="text-xs text-slate-700 font-semibold mt-1">{chartSource.label}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">
                    {chartSource.is_brand_published
                      ? `Published by the brand${chartSource.updated_at ? ` · updated ${chartSource.updated_at}` : ' · no update date published'}`
                      : `Public standard${chartSource.standard ? ` (${chartSource.standard})` : ''} — not this brand's own measurements`}
                  </p>
                  {chartSource.notes?.map((note) => (
                    <p key={note} className="text-[10px] text-slate-500 mt-1">{note}</p>
                  ))}
                </div>
              )}

              {/* Why this size — per-section evidence */}
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-2">
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

              {/* Size comparison from the real chart */}
              {result.size_comparison_table.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-[11px]">
                    <caption className="sr-only">
                      Body measurement ranges and fit score for every size this product sells
                    </caption>
                    <thead>
                      <tr className="text-slate-500 uppercase tracking-wider text-[9px]">
                        <th scope="col" className="text-left py-1">Size</th>
                        <th scope="col" className="text-left py-1">Chest (cm)</th>
                        <th scope="col" className="text-left py-1">Waist (cm)</th>
                        <th scope="col" className="text-left py-1">Fit</th>
                        <th scope="col" className="text-left py-1">Stock</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.size_comparison_table.map((row) => {
                        const fmt = (r?: [number, number]) => (r ? `${r[0]}–${r[1]}` : '—');
                        return (
                          <tr
                            key={row.size}
                            className={`border-t border-slate-100 ${row.is_recommended ? 'bg-[#FDF8EE] font-bold text-[#1B1F3B]' : 'text-slate-600'}`}
                          >
                            <td className="py-1.5">
                              {row.size}
                              {row.is_recommended ? ' ←' : ''}
                            </td>
                            <td className="py-1.5">{fmt(row.ranges_cm?.chest)}</td>
                            <td className="py-1.5">{fmt(row.ranges_cm?.waist)}</td>
                            <td className="py-1.5">{row.fit_rating}</td>
                            <td className="py-1.5">{row.in_stock ? 'In stock' : 'Out of stock'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-[#FAF9F6] rounded-2xl p-3 border border-slate-100">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Brand tendency</p>
                  <p className="text-xs text-slate-700 font-semibold mt-1">
                    {result.brand_sizing_tendency?.summary}
                  </p>
                  {result.brand_sizing_tendency?.return_rate_signal && (
                    <p className="text-[10px] text-slate-500 mt-1">
                      {result.brand_sizing_tendency.return_rate_signal}
                    </p>
                  )}
                </div>
                <div className="bg-[#FAF9F6] rounded-2xl p-3 border border-slate-100">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Return risk</p>
                  <p className="text-xs text-slate-700 font-semibold mt-1">{result.return_risk?.label}</p>
                  <p className="text-[10px] text-slate-500 mt-1">{result.return_risk?.basis}</p>
                </div>
              </div>

              {/* How the confidence was built — auditable, not asserted */}
              {result.confidence_factors?.length > 0 && (
                <details className="bg-[#FAF9F6] rounded-2xl border border-slate-100 px-3 py-2">
                  <summary className="text-[11px] font-bold text-slate-700 cursor-pointer">
                    How this {result.confidence_score}% confidence was calculated
                  </summary>
                  <ul className="mt-2 space-y-1">
                    {result.confidence_factors.map((factor, i) => (
                      <li key={i} className="text-[10px] text-slate-600 font-mono">{factor}</li>
                    ))}
                  </ul>
                  <p className="text-[10px] text-slate-500 mt-2">
                    Engine {result.engine_version}. No remote method can guarantee fit, so the score
                    is deliberately capped below certainty.
                  </p>
                </details>
              )}

              {result.notes?.length > 0 && (
                <ul className="space-y-1">
                  {result.notes.map((note, i) => (
                    <li key={i} className="text-[10px] text-slate-500 leading-relaxed">• {note}</li>
                  ))}
                </ul>
              )}

              {/* Save + go to product */}
              <div className="pt-3 border-t border-slate-100 space-y-2">
                {isAuthenticated ? (
                  <>
                    <label className="flex items-start gap-2 text-[10px] text-slate-600 leading-relaxed cursor-pointer">
                      <input
                        type="checkbox"
                        checked={saveConsent}
                        onChange={(e) => setSaveConsent(e.target.checked)}
                        className="mt-0.5"
                      />
                      <span>
                        I agree to CONFIT storing these body measurements on my profile
                        (encrypted at rest). I can delete them at any time.
                      </span>
                    </label>
                    <button
                      onClick={handleSave}
                      disabled={!saveConsent || saveState === 'saving' || saveState === 'saved'}
                      className="w-full py-2.5 rounded-xl border border-[#C5A059]/50 text-[#A37E44] hover:bg-[#FDF8EE] disabled:opacity-50 text-[11px] font-bold transition-all"
                    >
                      {saveState === 'saving'
                        ? 'Saving…'
                        : saveState === 'saved'
                          ? '✓ Saved to your profile'
                          : 'Save these measurements to my profile'}
                    </button>
                  </>
                ) : (
                  <p className="text-[10px] text-slate-500 text-center">
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
