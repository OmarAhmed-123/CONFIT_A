import React, { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SparkleIcon } from '../icons/ConfitIcons';
import { useUIStore } from '../../stores/uiStore';
import { useConsentStore } from '../../privacy/consentStore';
import {
  measurementService,
  PhotoEstimateResult,
} from '../../services/measurementService';

/**
 * Feature 05 — "Estimate from a photo" panel for the Fit Finder.
 *
 * Design rules (mirroring the backend honesty contract):
 *
 * * Consent is an explicit checkbox tied to the durable `body_scan` grant.
 *   Without it the estimate button never enables — consent is never assumed
 *   from a click on "Estimate".
 * * The estimate runs against a server_side measurement session created at
 *   submit time (the session is the audit unit; consent is recorded there).
 * * A 422 is an honest refusal from the worker (bad pose, no person,
 *   implausible geometry). Its guidance is displayed verbatim so the user
 *   can retake the photo — it is never replaced with a generic error.
 * * The result shows what was estimated AND what was excluded with reasons,
 *   plus the mandatory ±2-3 cm note. Shoulder/waist are rendered as
 *   "not estimated" when absent — never silently omitted, never invented.
 * * Applying the values to the parent form is a separate user action: the
 *   numbers arrive with their provenance shown first.
 */

export interface PhotoEstimateApplyValues {
  heightCm: number | null;
  chestCm: number | null;
  hipCm: number | null;
  /** Honest absence: the model set has no waist/shoulder. */
  waistCm: number | null;
}

interface Props {
  /** Called with metric centimetres when the user applies the estimate. */
  onApply: (values: PhotoEstimateApplyValues) => void;
  /** Pre-fill for the height anchor (metric cm) — improves calibration. */
  defaultHeightCm?: number | null;
  /** Pre-selected sex from the form's sizing demographic, when known. */
  defaultSex?: 'male' | 'female' | null;
}

type EstimationState =
  | { phase: 'idle' }
  | { phase: 'estimating' }
  | { phase: 'done'; result: PhotoEstimateResult }
  | { phase: 'refused'; code: string; message: string }
  | { phase: 'error'; message: string };

const MAX_PHOTO_BYTES = 15 * 1024 * 1024; // matches the backend upload limit
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

const REASON_LABELS: Record<string, string> = {
  outside_anatomical_range: 'implausible for the estimated body',
  inconsistent_with_observed_geometry: 'contradicts the pose geometry in your photo',
  outside_body_proportion_band: 'outside plausible body proportions',
};

export const PhotoEstimatePanel: React.FC<Props> = ({
  onApply,
  defaultHeightCm = null,
  defaultSex = null,
}) => {
  const { t } = useTranslation();
  const { showToast } = useUIStore();
  const grantConsent = useConsentStore((s) => s.grant);
  const withdrawConsent = useConsentStore((s) => s.withdraw);

  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [sex, setSex] = useState<'male' | 'female'>(defaultSex === 'female' ? 'female' : 'male');
  const [height, setHeight] = useState<string>(defaultHeightCm ? String(defaultHeightCm) : '');
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<EstimationState>({ phase: 'idle' });
  const [applied, setApplied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const pickFile = (f: File | null) => {
    setApplied(false);
    setState({ phase: 'idle' });
    if (!f) {
      setFile(null);
      setPreviewUrl(null);
      return;
    }
    if (!ACCEPTED_TYPES.includes(f.type)) {
      showToast(t('fit_finder.photo_estimate.bad_type'), 'error');
      return;
    }
    if (f.size > MAX_PHOTO_BYTES) {
      showToast(t('fit_finder.photo_estimate.too_large'), 'error');
      return;
    }
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
  };

  const estimate = async () => {
    if (!file || !consent) return;
    setState({ phase: 'estimating' });
    setApplied(false);
    try {
      // The session is created at submit time with the consent the user just
      // ticked — never before, never without it.
      const session = await measurementService.createSession('server_side', {
        consentGranted: true,
      });
      const heightCm = height.trim() === '' ? null : Number(height);
      const result = await measurementService.estimateFromPhoto(
        session.id,
        file,
        sex,
        Number.isFinite(heightCm) ? heightCm : null
      );
      setState({ phase: 'done', result });
    } catch (err: any) {
      // 422 = the worker's honest refusal with actionable guidance.
      const e = err?.details?.error ?? err?.error;
      if (e?.code && e?.message) {
        setState({ phase: 'refused', code: String(e.code), message: String(e.message) });
      } else {
        setState({
          phase: 'error',
          message: err?.message || t('fit_finder.photo_estimate.error_generic'),
        });
      }
    }
  };

  const apply = (result: PhotoEstimateResult) => {
    const s = result.stored_measurements;
    onApply({
      heightCm: s.height_cm,
      chestCm: s.chest_cm,
      hipCm: s.hip_cm,
      waistCm: s.waist_cm,
    });
    setApplied(true);
    showToast(t('fit_finder.photo_estimate.applied'), 'success');
  };

  const busy = state.phase === 'estimating';
  const canEstimate = Boolean(file) && consent && !busy;

  return (
    <div className="rounded-2xl border border-slate-200 bg-[#FAF9F6] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-xs font-bold text-[#1B1F3B]">
          <SparkleIcon size={16} color="#C5A059" />
          {t('fit_finder.photo_estimate.title')}
        </span>
        <span className="text-[10px] text-slate-500 font-semibold">
          {open ? t('fit_finder.photo_estimate.hide') : t('fit_finder.photo_estimate.show')}
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          <p className="text-[11px] text-slate-600 leading-relaxed">
            {t('fit_finder.photo_estimate.intro')}{' '}
            <span className="font-semibold">±2–3 cm</span>{' '}
            {t('fit_finder.photo_estimate.intro_accuracy')}
          </p>

          {/* Photo */}
          <div className="flex items-start gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_TYPES.join(',')}
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex-1 py-2.5 rounded-xl border border-dashed border-slate-300 text-[11px] font-bold text-slate-600 hover:border-[#C5A059] transition-all"
            >
              {file ? file.name : t('fit_finder.photo_estimate.choose_file')}
            </button>
            {previewUrl && (
              <img
                src={previewUrl}
                alt=""
                className="w-12 h-16 object-cover rounded-lg border border-slate-200"
              />
            )}
          </div>

          {/* Sex + height anchor */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="pe-sex" className="text-[10px] font-bold text-slate-700 block mb-1">
                {t('fit_finder.photo_estimate.sex')}
              </label>
              <select
                id="pe-sex"
                value={sex}
                onChange={(e) => setSex(e.target.value as 'male' | 'female')}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs"
              >
                <option value="male">{t('fit_finder.photo_estimate.sex_male')}</option>
                <option value="female">{t('fit_finder.photo_estimate.sex_female')}</option>
              </select>
            </div>
            <div>
              <label htmlFor="pe-height" className="text-[10px] font-bold text-slate-700 block mb-1">
                {t('fit_finder.photo_estimate.height')} ({t('fit_finder.photo_estimate.height_unit')})
              </label>
              <input
                id="pe-height"
                type="number"
                inputMode="decimal"
                min={50}
                max={260}
                value={height}
                placeholder="176"
                onChange={(e) => setHeight(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs"
              />
            </div>
          </div>
          <p className="text-[10px] text-slate-500 leading-relaxed">
            {t('fit_finder.photo_estimate.height_hint')}
          </p>

          {/* Consent — explicit, durable, revocable */}
          <label className="flex items-start gap-2 text-[10px] text-slate-600 leading-relaxed cursor-pointer">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => {
                setConsent(e.target.checked);
                if (e.target.checked) grantConsent('body_scan');
                else withdrawConsent('body_scan');
              }}
              className="mt-0.5"
            />
            <span>{t('fit_finder.photo_estimate.consent')}</span>
          </label>

          <button
            type="button"
            onClick={estimate}
            disabled={!canEstimate}
            className="w-full py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 text-white text-[11px] font-bold transition-all"
          >
            {busy ? t('fit_finder.photo_estimate.working') : t('fit_finder.photo_estimate.estimate')}
          </button>

          {/* Honest refusal — the worker's guidance, verbatim */}
          {state.phase === 'refused' && (
            <div className="rounded-xl bg-amber-50 border border-amber-200 px-3 py-2 space-y-1" role="alert">
              <p className="text-[11px] font-bold text-amber-900">
                {t('fit_finder.photo_estimate.refused')}
              </p>
              <p className="text-[11px] text-amber-900 leading-relaxed">{state.message}</p>
              <p className="text-[10px] text-amber-700 font-mono">{state.code}</p>
            </div>
          )}

          {state.phase === 'error' && (
            <div className="rounded-xl bg-rose-50 border border-rose-200 px-3 py-2" role="alert">
              <p className="text-[11px] text-rose-800 leading-relaxed">{state.message}</p>
              <p className="text-[10px] text-rose-600 mt-1">
                {t('fit_finder.photo_estimate.retry_hint')}
              </p>
            </div>
          )}

          {/* Result — full provenance, exclusions included */}
          {state.phase === 'done' && (
            <div className="rounded-xl bg-white border border-slate-200 px-3 py-3 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-[11px] font-bold text-[#1B1F3B]">
                  {t('fit_finder.photo_estimate.result_title')}
                </p>
                <span className="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                  {state.result.quality}
                </span>
              </div>

              <ul className="space-y-0.5">
                {(['height_cm', 'chest_cm', 'hip_cm'] as const).map((k) => {
                  const v = state.result.stored_measurements[k];
                  return (
                    <li key={k} className="flex justify-between text-[11px] text-slate-700">
                      <span>{t(`fit_finder.photo_estimate.field_${k.replace('_cm', '')}`)}</span>
                      <span className="font-mono font-semibold">
                        {v == null ? '—' : `${Math.round(v)} cm`}
                      </span>
                    </li>
                  );
                })}
                <li className="flex justify-between text-[11px] text-slate-400">
                  <span>{t('fit_finder.photo_estimate.field_waist')}</span>
                  <span className="font-mono">
                    {t('fit_finder.photo_estimate.not_estimated')}
                  </span>
                </li>
              </ul>

              {state.result.excluded.length > 0 && (
                <details className="text-[10px] text-slate-600">
                  <summary className="cursor-pointer font-bold">
                    {t('fit_finder.photo_estimate.excluded_summary', {
                      count: state.result.excluded.length,
                    })}
                  </summary>
                  <ul className="mt-1 space-y-0.5">
                    {state.result.excluded.map((x) => (
                      <li key={x.name} className="leading-relaxed">
                        • {x.name} — {REASON_LABELS[x.reason] ?? x.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              <p className="text-[10px] text-slate-500 leading-relaxed">
                {t('fit_finder.photo_estimate.accuracy_line', {
                  note: state.result.accuracy_note,
                })}
              </p>

              <button
                type="button"
                onClick={() => apply(state.result)}
                disabled={applied}
                className="w-full py-2 rounded-xl border border-[#C5A059]/50 text-[#A37E44] hover:bg-[#FDF8EE] disabled:opacity-50 text-[11px] font-bold transition-all"
              >
                {applied
                  ? t('fit_finder.photo_estimate.applied_short')
                  : t('fit_finder.photo_estimate.apply')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
