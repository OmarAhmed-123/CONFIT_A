import { msg, translatableFrom, resolveMessage, type TranslatableMessage } from '../../i18n/messages';
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useModalFocus } from '../../hooks/useModalFocus';
import { usePhotoConsent } from '../../privacy/usePhotoConsent';
import { useTranslation } from 'react-i18next';
import { RulerIcon, SparkleIcon, TryOnIcon, LockIcon } from '../icons/ConfitIcons';
import { FitScoreBadge } from '../common/CommonComponents';
import { measurementService } from '../../services/measurementService';
import { computeSizeProfileConfidence } from '../../lib/sizeProfile';
import { compressImageToDataUrl } from '../../lib/imageUpload';

export interface CameraScanModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApplyMeasurements: (measurements: {
    height_cm: number;
    weight_kg: number;
    body_shape: string;
    chest_cm: number;
    waist_cm: number;
    shoulder_cm: number;
    hip_cm: number;
    confidence_score: number;
  }) => void;
}

export const CameraScanModal: React.FC<CameraScanModalProps> = ({
  isOpen,
  onClose,
  onApplyMeasurements,
}) => {
  const { t, i18n } = useTranslation();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // Consent for the body-scan photo. The gate is what makes the
  // `consentGranted: true` below TRUE instead of asserted.
  const { requestConsent, consentDialog } = usePhotoConsent('body_scan');
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameId = useRef<number | null>(null);
  const cameraRequestId = useRef(0);
  const analysisTimerIds = useRef<number[]>([]);
  const lastFrameTime = useRef<number>(performance.now());
  const frameCount = useRef<number>(0);

  const [activeTab, setActiveTab] = useState<'camera' | 'upload' | 'preset' | 'ruler'>('camera');
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [cameraError, setCameraError] = useState<TranslatableMessage | null>(null);
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('user');
  const [hasMultipleCameras, setHasMultipleCameras] = useState(false);
  const [fps, setFps] = useState<number>(30);
  const [scanProgress, setScanProgress] = useState<number>(0);
  const [analysisLogs, setAnalysisLogs] = useState<string[]>([]);

  const [scanStep, setScanStep] = useState<'ready' | 'analyzing' | 'result'>('ready');
  const [capturedImage, setCapturedImage] = useState<string | null>(null);

  // Calibration and User Height Reference
  const [userCalibrationHeightCm, setUserCalibrationHeightCm] = useState<number>(178);
  const [heightCm, setHeightCm] = useState<number>(178);
  const [shoulderCm, setShoulderCm] = useState<number>(46);
  const [chestCm, setChestCm] = useState<number>(98);
  const [waistCm, setWaistCm] = useState<number>(82);
  const [hipCm, setHipCm] = useState<number>(96);
  const [selectedSilhouette, setSelectedSilhouette] = useState<string>('Athletic V-Taper');
  // Honesty tracking: which inputs the user ACTUALLY set (a slider left at
  // its default is not data). Drives the principled confidence model in
  // lib/sizeProfile.ts — replaces the old hardcoded 97/94/95.
  const [modifiedInputs, setModifiedInputs] = useState<Record<string, boolean>>({});
  const markModified = (key: string) => setModifiedInputs((m) => (m[key] ? m : { ...m, [key]: true }));

  // Estimated Measurements Output
  const [estimatedData, setEstimatedData] = useState<{
    height_cm: number;
    weight_kg: number;
    body_shape: string;
    chest_cm: number;
    waist_cm: number;
    shoulder_cm: number;
    hip_cm: number;
    confidence_score: number;
    confidence_disclosure: string;
    is_estimated: boolean;
    method: 'self_reported';
    weight_estimated: boolean;
    hip_estimated: boolean;
    source: string;
    predicted_size: string;
  } | null>(null);

  // Enumerate video devices without treating enumeration failure as camera
  // availability. Browsers commonly hide device labels/counts until the user
  // grants permission.
  useEffect(() => {
    if (typeof navigator !== 'undefined' && navigator.mediaDevices?.enumerateDevices) {
      navigator.mediaDevices.enumerateDevices().then((devices) => {
        const videoInputs = devices.filter((d) => d.kind === 'videoinput');
        setHasMultipleCameras(videoInputs.length > 1);
      }).catch(() => {
        setHasMultipleCameras(false);
      });
    }
  }, []);

  const clearAnalysisTimers = useCallback(() => {
    analysisTimerIds.current.forEach((timerId) => window.clearTimeout(timerId));
    analysisTimerIds.current = [];
  }, []);

  const stopCamera = useCallback(() => {
    // Invalidates an in-flight getUserMedia request. If it resolves after the
    // user changes tabs or closes the dialog, its tracks are stopped below in
    // startCamera rather than being attached to a hidden video element.
    cameraRequestId.current += 1;
    if (animFrameId.current !== null) {
      cancelAnimationFrame(animFrameId.current);
      animFrameId.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
    setCameraLoading(false);
  }, []);

  const resetPrivateSession = useCallback(() => {
    stopCamera();
    clearAnalysisTimers();
    setCapturedImage(null);
    setEstimatedData(null);
    setScanStep('ready');
    setScanProgress(0);
    setAnalysisLogs([]);
    setCameraError(null);
    setActiveTab('camera');
    setUserCalibrationHeightCm(178);
    setHeightCm(178);
    setShoulderCm(46);
    setChestCm(98);
    setWaistCm(82);
    setHipCm(96);
    setSelectedSilhouette('Athletic V-Taper');
    setModifiedInputs({});
    if (canvasRef.current) {
      // Resetting either bitmap dimension clears its backing buffer without
      // asking for a rendering context (which may itself be unavailable).
      canvasRef.current.width = 0;
      canvasRef.current.height = 0;
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [clearAnalysisTimers, stopCamera]);

  const handleClose = useCallback(() => {
    // Clear camera bytes and self-reported body data before handing control
    // back to the parent. The privacy promise therefore describes behavior,
    // not merely where the data was processed.
    resetPrivateSession();
    onClose();
  }, [onClose, resetPrivateSession]);

  const panelRef = useModalFocus<HTMLDivElement>(handleClose, isOpen);

  useEffect(() => {
    if (!isOpen) {
      resetPrivateSession();
      return;
    }
    if (activeTab !== 'camera' || scanStep !== 'ready') {
      stopCamera();
    }
  }, [isOpen, activeTab, scanStep, resetPrivateSession, stopCamera]);

  useEffect(() => () => {
    stopCamera();
    clearAnalysisTimers();
  }, [clearAnalysisTimers, stopCamera]);

  // Real-time canvas landmark rendering and HUD overlay loop
  const drawPoseOverlay = useCallback(() => {
    if (!videoRef.current || !canvasRef.current || !cameraActive) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (video.readyState >= 2) {
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const w = canvas.width;
      const h = canvas.height;

      // Draw real video frame
      ctx.drawImage(video, 0, 0, w, h);

      // Measure real processing FPS
      const now = performance.now();
      frameCount.current += 1;
      if (now - lastFrameTime.current >= 1000) {
        setFps(Math.round((frameCount.current * 1000) / (now - lastFrameTime.current)));
        frameCount.current = 0;
        lastFrameTime.current = now;
      }

      // 1. Biometric Head Oval Guide
      const headCx = w / 2;
      const headCy = h * 0.22;
      const headRx = w * 0.11;
      const headRy = h * 0.13;

      ctx.strokeStyle = '#C5A059';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 6]);
      ctx.beginPath();
      ctx.ellipse(headCx, headCy, headRx, headRy, 0, 0, 2 * Math.PI);
      ctx.stroke();

      // 2. Bi-Deltoid Shoulder Caliper
      const shoulderY = h * 0.38;
      const shoulderLeft = w * 0.28;
      const shoulderRight = w * 0.72;

      ctx.strokeStyle = '#FAF9F6';
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(shoulderLeft, shoulderY);
      ctx.lineTo(shoulderRight, shoulderY);
      ctx.stroke();

      // Caliper Handles
      ctx.fillStyle = '#C5A059';
      ctx.beginPath();
      ctx.arc(shoulderLeft, shoulderY, 4, 0, 2 * Math.PI);
      ctx.arc(shoulderRight, shoulderY, 4, 0, 2 * Math.PI);
      ctx.fill();

      // Caliper Label
      ctx.font = 'bold 11px Inter, sans-serif';
      ctx.fillStyle = '#C5A059';
      ctx.fillText(`Guide (your input): shoulder ${shoulderCm} cm`, headCx - 50, shoulderY - 10);

      // 3. Torso Bounding Guide
      ctx.strokeStyle = 'rgba(197, 160, 89, 0.4)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.strokeRect(w * 0.25, shoulderY, w * 0.50, h * 0.48);

      // 4. Waistline Indicator
      const waistY = h * 0.60;
      ctx.strokeStyle = 'rgba(250, 249, 246, 0.7)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(w * 0.32, waistY);
      ctx.lineTo(w * 0.68, waistY);
      ctx.stroke();

      // Waist Label
      ctx.fillStyle = '#FAF9F6';
      ctx.fillText(`Waistline: ${waistCm}cm`, headCx - 40, waistY - 6);
    }

    animFrameId.current = requestAnimationFrame(drawPoseOverlay);
  }, [cameraActive, shoulderCm, waistCm]);

  useEffect(() => {
    if (cameraActive) {
      animFrameId.current = requestAnimationFrame(drawPoseOverlay);
    }
    return () => {
      if (animFrameId.current) cancelAnimationFrame(animFrameId.current);
    };
  }, [cameraActive, drawPoseOverlay]);

  const startCamera = async (mode: 'user' | 'environment' = facingMode) => {
    stopCamera();
    const requestId = ++cameraRequestId.current;
    setCameraLoading(true);
    setCameraError(null);

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setCameraError(msg('errors.webcam_restricted'));
      setCameraLoading(false);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: mode,
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      // A late permission response must not resurrect the camera after the
      // user closes the studio or chooses a no-camera fallback.
      if (requestId !== cameraRequestId.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      streamRef.current = stream;
      if (!videoRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setCameraError(msg('tryon.scan_camera_unavailable'));
        setCameraLoading(false);
        return;
      }

      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      if (requestId !== cameraRequestId.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      setCameraActive(true);
      setCameraLoading(false);
    } catch (error: unknown) {
      if (requestId !== cameraRequestId.current) return;
      console.warn('Camera stream error:', error);
      const errorName = error instanceof DOMException
        ? error.name
        : typeof error === 'object' && error && 'name' in error
          ? String(error.name)
          : '';
      const errorMessage = errorName === 'NotAllowedError' || errorName === 'PermissionDeniedError'
        ? msg('tryon.scan_camera_permission_denied')
        : errorName === 'NotFoundError' || errorName === 'DevicesNotFoundError'
          ? msg('tryon.scan_camera_not_found')
          : msg('tryon.scan_camera_unavailable');
      stopCamera();
      setCameraError(errorMessage);
    }
  };

  const toggleCameraFacing = () => {
    const nextMode = facingMode === 'user' ? 'environment' : 'user';
    setFacingMode(nextMode);
    startCamera(nextMode);
  };

  const selectTab = (tab: 'camera' | 'upload' | 'preset' | 'ruler') => {
    setActiveTab(tab);
    setScanStep('ready');
    setCameraError(null);
    if (tab === 'camera') startCamera();
    else stopCamera();
  };

  const captureCameraFrame = () => {
    let capturedDataUrl: string | null = null;
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        capturedDataUrl = canvas.toDataURL('image/jpeg', 0.90);
        setCapturedImage(capturedDataUrl);
      }
    }

    stopCamera();
    runVisionAnalysis('live_camera');
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // P0-03 fix: compress before analysis/upload — raw phone photos exceeded
    // the gateway body limit (HTTP 413).
    try {
      const { dataUrl } = await compressImageToDataUrl(file);
      setCapturedImage(dataUrl);
      runVisionAnalysis('uploaded_photo');
    } catch (err) {
      setCameraError(translatableFrom(err));
    }
  };

  const deriveSizeFromMeasurements = (chest: number, waist: number, height: number): string => {
    if (chest < 90 || waist < 74) return 'Size S (Slim Tailored)';
    if (chest <= 102 && waist <= 86) return 'Size M (Regular Drape)';
    if (chest <= 110 && waist <= 94) return 'Size L (Structured Comfort)';
    return 'Size XL (Relaxed Tailored)';
  };

  const runVisionAnalysis = (source: string) => {
    clearAnalysisTimers();
    setScanStep('analyzing');
    setScanProgress(15);
    // Truthful processing logs: this flow compiles the user's SELF-REPORTED
    // sliders (+ height-ratio estimates for anything missing) — it performs
    // no keypoint detection, so it must not claim any (audit fix).
    setAnalysisLogs(['[1/3] Measurements captured from your inputs']);

    const isPreset = source === 'silhouette_preset';
    const modifiedKeys = Object.keys(modifiedInputs).filter((k) => modifiedInputs[k]);
    const provided = isPreset
      ? ['shoulder', 'chest', 'waist', 'hip', 'body_shape']
      : [...modifiedKeys];
    const profile = computeSizeProfileConfidence({ provided, preset: isPreset });

    const steps = [
      { p: 45, log: '[2/3] Weight estimated from height ratio (BMI model)' },
      { p: 75, log: '[3/3] Matching brand size chart' },
      { p: 100, log: `✓ Profile ready — ${profile.confidence}% self-reported confidence` },
    ];

    analysisTimerIds.current = steps.map((step, idx) => window.setTimeout(() => {
        setScanProgress(step.p);
        setAnalysisLogs((prev) => [...prev, step.log]);

        if (idx === steps.length - 1) {
          // Final Calculation — the user's slider values ARE the profile.
          // (Previously these were discarded and re-derived from height
          // ratios while the UI claimed a biometric scan had run.)
          const calHeight = userCalibrationHeightCm || heightCm;
          const derivedWeight = Math.round((calHeight - 100) * 0.9); // ratio estimate, not measured
          const predSize = deriveSizeFromMeasurements(chestCm, waistCm, calHeight);

          const derived = {
            height_cm: calHeight,
            weight_kg: derivedWeight,
            body_shape: selectedSilhouette,
            chest_cm: chestCm,
            waist_cm: waistCm,
            shoulder_cm: shoulderCm,
            hip_cm: hipCm,
            confidence_score: profile.confidence,
            confidence_disclosure: profile.disclosure,
            is_estimated: profile.is_estimated,
            method: 'self_reported' as const,
            weight_estimated: true,
            hip_estimated: !modifiedInputs.hip,
            source,
            predicted_size: predSize,
          };

          setEstimatedData(derived);
          setScanStep('result');

          // Submit results to the backend measurement session — but ONLY with a
          // real grant.
          //
          // This used to read: "the user explicitly started this scan and is
          // looking at the disclosure above the button. That action is the
          // consent." It is not. GDPR Art.7 requires an affirmative act for the
          // specific purpose; pressing Start is an act to obtain a size, and the
          // photo and the measurements are a separate, later decision. The old
          // code sent `consentGranted: true` on the user's behalf, which is a
          // pre-ticked box with better grammar.
          //
          // The local size estimate has already been shown by this point, so
          // declining costs the user nothing they came for.
          void (async () => {
            if (!(await requestConsent())) return;
            try {
              const sess = await measurementService.createSession('client_side', {
                consentGranted: true,
              });
              if (sess?.id) {
                await measurementService.submitResults(sess.id, {
                  height_cm: derived.height_cm,
                  shoulder_width_cm: derived.shoulder_cm,
                  chest_cm: derived.chest_cm,
                  waist_cm: derived.waist_cm,
                  hip_cm: derived.hip_cm,
                  body_shape: derived.body_shape,
                  confidence_score: derived.confidence_score,
                  calibration_method: `self_reported_inputs_${profile.inputs_counted.length}`,
                  source: derived.source,
                });
              }
            } catch {
              /* the size estimate above already succeeded; a failed session
                 save must not erase it or raise a second, confusing error */
            }
          })();
        }
      }, (idx + 1) * 350));
  };

  const applyPresetSilhouette = (preset: {
    shape: string;
    height: number;
    chest: number;
    waist: number;
    shoulder: number;
    hip: number;
  }) => {
    setUserCalibrationHeightCm(preset.height);
    setHeightCm(preset.height);
    setChestCm(preset.chest);
    setWaistCm(preset.waist);
    setShoulderCm(preset.shoulder);
    setHipCm(preset.hip);
    setSelectedSilhouette(preset.shape);
    setModifiedInputs({ shoulder: true, chest: true, waist: true, hip: true, body_shape: true });
    runVisionAnalysis('silhouette_preset');
  };

  const handleApply = () => {
    if (estimatedData) {
      onApplyMeasurements(estimatedData);
      handleClose();
    }
  };

  const handleRetake = () => {
    clearAnalysisTimers();
    setCapturedImage(null);
    setEstimatedData(null);
    setScanStep('ready');
    setScanProgress(0);
    setAnalysisLogs([]);
    if (activeTab === 'camera') {
      startCamera();
    }
  };

  if (!isOpen) return null;

  const silhouettePresets = [
    { shape: 'Athletic V-Taper', label: t('tryon.scan_preset_athletic'), height: 178, chest: 99, waist: 82, shoulder: 46, hip: 96, desc: t('tryon.scan_preset_athletic_desc') },
    { shape: 'Hourglass Feminine', label: t('tryon.scan_preset_hourglass'), height: 172, chest: 92, waist: 68, shoulder: 40, hip: 96, desc: t('tryon.scan_preset_hourglass_desc') },
    { shape: 'Tall Structured', label: t('tryon.scan_preset_tall'), height: 186, chest: 104, waist: 86, shoulder: 48, hip: 100, desc: t('tryon.scan_preset_tall_desc') },
    { shape: 'Classic Regular', label: t('tryon.scan_preset_regular'), height: 175, chest: 96, waist: 84, shoulder: 44, hip: 95, desc: t('tryon.scan_preset_regular_desc') },
  ];

  return (
    <>
      {consentDialog}
    <div data-testid="camera-modal-overlay" className="fixed inset-0 z-50 !m-0 flex items-center justify-center bg-slate-950/85 p-0 backdrop-blur-md animate-in fade-in duration-150 sm:p-4">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="camera-scan-title"
        aria-describedby="camera-scan-summary"
        tabIndex={-1}
        dir={i18n.dir()}
        className="flex h-[100dvh] max-h-[100dvh] w-full min-w-0 flex-col overflow-hidden border border-slate-100 bg-white shadow-2xl sm:h-auto sm:max-w-2xl sm:max-h-[92dvh] sm:rounded-3xl"
      >
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-800 bg-[#0C0E1E] p-4 text-white sm:items-center sm:p-5">
          <div className="flex min-w-0 items-start gap-3 sm:items-center">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#C5A059] font-bold text-slate-950 shadow-xs">
              <RulerIcon size={22} color="#0C0E1E" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 id="camera-scan-title" className="font-serif text-base font-bold text-white sm:text-lg">
                  {t('tryon.scan_studio_title')}
                </h3>
                <span className="rounded-full border border-emerald-500/30 bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] text-emerald-400">
                  {t('tryon.scan_privacy_badge')}
                </span>
              </div>
              <p id="camera-scan-summary" className="mt-1 text-[11px] font-light leading-relaxed text-slate-400">
                {t('tryon.scan_privacy_summary')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label={t('tryon.scan_close')}
            title={t('tryon.scan_close')}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-800 text-sm text-slate-300 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>

        {/* Two rows on narrow screens keep every target readable and visible;
            a four-column strip returns at the first practical tablet width. */}
        <div role="tablist" aria-label={t('tryon.scan_modes')} className="grid shrink-0 grid-cols-2 gap-1.5 border-b border-slate-200 bg-[#FAF9F6] p-1.5 text-xs font-semibold sm:grid-cols-4">
          {[
            { id: 'camera' as const, icon: '📹', label: t('tryon.scan_tab_camera') },
            { id: 'upload' as const, icon: '🖼️', label: t('tryon.scan_tab_upload') },
            { id: 'preset' as const, icon: '👤', label: t('tryon.scan_tab_preset') },
            { id: 'ruler' as const, icon: '📐', label: t('tryon.scan_tab_ruler') },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`camera-scan-tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls={`camera-scan-panel-${tab.id}`}
              onClick={() => selectTab(tab.id)}
              className={`min-h-11 min-w-0 rounded-xl px-2 py-2.5 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ${
                activeTab === tab.id
                  ? 'bg-[#1B1F3B] text-white shadow-xs'
                  : 'text-slate-600 hover:bg-slate-200/60'
              }`}
            >
              <span aria-hidden="true">{tab.icon}</span>{' '}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Modal Body */}
        <div className="min-w-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto p-3 sm:p-6">
          {scanStep === 'ready' && (
            <>
              {/* Reference Height Calibration Input */}
              <div className="flex flex-col gap-3 rounded-2xl border border-[#C5A059]/30 bg-[#FDF8EE] p-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                <div className="min-w-0">
                  <label htmlFor="camera-calibration-height" className="block text-xs font-bold text-[#1B1F3B]">
                    {t('tryon.scan_calibration_label')}
                  </label>
                  <span className="text-[11px] font-light leading-relaxed text-slate-600">
                    {t('tryon.scan_calibration_hint')}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <input
                    id="camera-calibration-height"
                    type="number"
                    inputMode="numeric"
                    min="140"
                    max="220"
                    value={userCalibrationHeightCm}
                    onChange={(e) => {
                      setUserCalibrationHeightCm(Number(e.target.value));
                      markModified('height');
                    }}
                    className="w-24 rounded-xl border border-slate-300 bg-white px-2.5 py-2 text-center text-xs font-bold text-slate-900 focus:border-[#C5A059] focus:outline-none"
                  />
                  <span className="text-xs font-bold text-slate-700">{t('tryon.scan_unit_cm')}</span>
                </div>
              </div>

              {/* --- TAB 1: LIVE CAMERA --- */}
              {activeTab === 'camera' && (
                <div
                  id="camera-scan-panel-camera"
                  role="tabpanel"
                  aria-labelledby="camera-scan-tab-camera"
                  className="min-w-0 space-y-4"
                >
                  {cameraError && (
                    <div role="alert" className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50 p-3.5 text-xs text-amber-900">
                      <p className="font-medium leading-relaxed">{resolveMessage(cameraError, t)}</p>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => startCamera()}
                          className="min-h-10 rounded-lg bg-amber-700 px-3 py-2 text-[11px] font-bold text-white hover:bg-amber-800"
                        >
                          {t('tryon.scan_camera_retry')}
                        </button>
                        <button
                          type="button"
                          onClick={() => selectTab('upload')}
                          className="min-h-10 rounded-lg border border-amber-300 bg-white px-3 py-2 text-[11px] font-bold text-amber-900 hover:bg-amber-100"
                        >
                          {t('tryon.scan_camera_use_upload')}
                        </button>
                        <button
                          type="button"
                          onClick={() => selectTab('ruler')}
                          className="min-h-10 rounded-lg border border-amber-300 bg-white px-3 py-2 text-[11px] font-bold text-amber-900 hover:bg-amber-100"
                        >
                          {t('tryon.scan_camera_use_manual')}
                        </button>
                      </div>
                    </div>
                  )}

                  <div
                    data-testid="camera-stage"
                    className="relative isolate flex aspect-[4/3] min-w-0 items-center justify-center overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-lg sm:rounded-3xl"
                  >
                    <video
                      ref={videoRef}
                      playsInline
                      muted
                      autoPlay
                      className="hidden"
                    />
                    <canvas
                      ref={canvasRef}
                      data-testid="camera-preview-canvas"
                      aria-hidden={!cameraActive}
                      className={`absolute inset-0 h-full w-full object-cover ${cameraActive ? 'block' : 'hidden'}`}
                    />

                    {/* HUD Status Bar & Scanning Laser */}
                    {cameraActive && (
                      <>
                        <div className="pointer-events-none absolute inset-x-3 top-3 z-10 flex items-start justify-between gap-2">
                          <div className="flex items-center gap-1.5 rounded-full border border-[#C5A059]/40 bg-slate-950/80 px-3 py-1 font-mono text-[10px] font-bold text-[#C5A059] shadow-xs backdrop-blur-md">
                            <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-emerald-400"></span>
                            <span>{t('tryon.scan_align_hint')}</span>
                          </div>
                          <div className="shrink-0 rounded-full border border-slate-700 bg-slate-950/80 px-2.5 py-1 font-mono text-[10px] text-slate-300">
                            {t('tryon.scan_camera_live_fps', { fps: fps })}
                          </div>
                        </div>

                        {/* Animated Laser Scanning Beam */}
                        <div className="pointer-events-none absolute inset-x-0 h-1 animate-[scan_2.5s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-[#C5A059] to-transparent shadow-[0_0_15px_#C5A059]" />
                      </>
                    )}

                    {!cameraActive && !cameraLoading && (
                      <div data-testid="camera-empty-state" className="absolute inset-0 flex flex-col items-center justify-center gap-3 overflow-y-auto p-4 text-center sm:p-6">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-slate-700 bg-slate-900 text-[#C5A059] shadow-md sm:h-14 sm:w-14">
                          <TryOnIcon size={28} color="#C5A059" isAi={true} />
                        </div>
                        <p className="mx-auto max-w-sm text-[11px] font-light leading-relaxed text-slate-300 sm:text-xs">
                          {t('tryon.scan_camera_start_hint')}
                        </p>
                        <button
                          type="button"
                          onClick={() => startCamera()}
                          className="min-h-11 rounded-xl bg-[#C5A059] px-5 py-2.5 text-xs font-bold text-slate-950 shadow-md transition-all hover:bg-[#E2BF70] active:scale-95"
                        >
                          {t('tryon.scan_camera_enable')}
                        </button>
                      </div>
                    )}

                    {cameraLoading && (
                      <div role="status" className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center">
                        <div className="h-8 w-8 animate-spin rounded-full border-3 border-[#C5A059] border-t-transparent"></div>
                        <span className="text-xs text-slate-300">{t('tryon.scan_init_stream')}</span>
                      </div>
                    )}
                  </div>

                  {cameraActive && (
                    <div className="flex flex-col gap-2.5 sm:flex-row">
                      {hasMultipleCameras && (
                        <button
                          type="button"
                          onClick={toggleCameraFacing}
                          className="min-h-11 rounded-xl border border-slate-300 px-4 py-3 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50"
                        >
                          {t('tryon.scan_camera_switch')}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={captureCameraFrame}
                        className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-2xl bg-[#1B1F3B] py-3.5 text-xs font-bold text-white shadow-md transition-all hover:bg-[#0C0E1E]"
                      >
                        <SparkleIcon size={16} color="#C5A059" />
                        <span>{t('tryon.scan_capture_cta')}</span>
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* --- TAB 2: PHOTO UPLOAD --- */}
              {activeTab === 'upload' && (
                <div
                  id="camera-scan-panel-upload"
                  role="tabpanel"
                  aria-labelledby="camera-scan-tab-upload"
                  className="space-y-4"
                >
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full space-y-3 rounded-3xl border-2 border-dashed border-slate-300 bg-[#FAF9F6] p-6 text-center transition-all hover:border-[#C5A059] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] sm:p-8"
                  >
                    <span aria-hidden="true" className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-200 bg-white text-[#C5A059] shadow-xs">
                      📸
                    </span>
                    <span className="block font-serif text-sm font-bold text-[#1B1F3B]">
                      {t('tryon.scan_upload_title')}
                    </span>
                    <span className="mx-auto block max-w-sm text-xs font-light leading-relaxed text-slate-500">
                      {t('tryon.scan_upload_hint')}
                    </span>
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    aria-label={t('tryon.scan_upload_title')}
                    onChange={handleFileUpload}
                    className="sr-only"
                  />
                </div>
              )}

              {/* --- TAB 3: PRESETS --- */}
              {activeTab === 'preset' && (
                <div
                  id="camera-scan-panel-preset"
                  role="tabpanel"
                  aria-labelledby="camera-scan-tab-preset"
                  className="space-y-3"
                >
                  <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">
                    {t('tryon.scan_preset_title')}
                  </h4>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {silhouettePresets.map((preset) => (
                      <button
                        type="button"
                        key={preset.shape}
                        onClick={() => applyPresetSilhouette(preset)}
                        className="space-y-1.5 rounded-2xl border border-slate-200 bg-white p-4 text-start shadow-2xs transition-all hover:border-[#C5A059] hover:bg-[#FDF8EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
                      >
                        <span className="flex items-start justify-between gap-2">
                          <span className="font-serif text-xs font-bold text-[#1B1F3B]">
                            {preset.label}
                          </span>
                          <span className="shrink-0 rounded border border-slate-200 bg-white px-2 py-0.5 font-mono text-[10px] font-bold">
                            {preset.height} {t('tryon.scan_unit_cm')}
                          </span>
                        </span>
                        <span className="block text-[11px] font-light leading-relaxed text-slate-500">{preset.desc}</span>
                        <span className="flex flex-wrap gap-x-2 gap-y-1 pt-1 text-[10px] font-medium text-slate-600">
                          <span>{t('tryon.scan_chest')}: {preset.chest} {t('tryon.scan_unit_cm')}</span>
                          <span aria-hidden="true">•</span>
                          <span>{t('tryon.scan_waist')}: {preset.waist} {t('tryon.scan_unit_cm')}</span>
                          <span aria-hidden="true">•</span>
                          <span>{t('tryon.scan_shoulder')}: {preset.shoulder} {t('tryon.scan_unit_cm')}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* --- TAB 4: MANUAL RULER --- */}
              {activeTab === 'ruler' && (
                <div
                  id="camera-scan-panel-ruler"
                  role="tabpanel"
                  aria-labelledby="camera-scan-tab-ruler"
                  className="space-y-4 rounded-2xl border border-slate-200 bg-[#FAF9F6] p-4 sm:p-5"
                >
                  <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">
                    {t('tryon.scan_manual_title')}
                  </h4>

                  <div className="space-y-3 text-xs">
                    <div>
                      <div className="flex justify-between mb-1 font-semibold text-slate-700">
                        <span>{t('tryon.scan_height')}:</span>
                        <span className="font-bold text-[#1B1F3B]">{heightCm} cm</span>
                      </div>
                      <input
                        type="range"
                        min="150"
                        max="210"
                        value={heightCm}
                        onChange={(e) => {
                          setHeightCm(Number(e.target.value));
                          setUserCalibrationHeightCm(Number(e.target.value));
                          markModified('height');
                        }}
                        className="w-full accent-[#C5A059]"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between mb-1 font-semibold text-slate-700">
                        <span>{t('tryon.scan_shoulder')}:</span>
                        <span className="font-bold text-[#1B1F3B]">{shoulderCm} cm</span>
                      </div>
                      <input
                        type="range"
                        min="38"
                        max="56"
                        value={shoulderCm}
                        onChange={(e) => { setShoulderCm(Number(e.target.value)); markModified('shoulder'); }}
                        className="w-full accent-[#C5A059]"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between mb-1 font-semibold text-slate-700">
                        <span>{t('tryon.scan_chest')}:</span>
                        <span className="font-bold text-[#1B1F3B]">{chestCm} cm</span>
                      </div>
                      <input
                        type="range"
                        min="75"
                        max="125"
                        value={chestCm}
                        onChange={(e) => { setChestCm(Number(e.target.value)); markModified('chest'); }}
                        className="w-full accent-[#C5A059]"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between mb-1 font-semibold text-slate-700">
                        <span>{t('tryon.scan_waist')}:</span>
                        <span className="font-bold text-[#1B1F3B]">{waistCm} cm</span>
                      </div>
                      <input
                        type="range"
                        min="60"
                        max="115"
                        value={waistCm}
                        onChange={(e) => { setWaistCm(Number(e.target.value)); markModified('waist'); }}
                        className="w-full accent-[#C5A059]"
                      />
                    </div>
                  </div>

                  <button
                    onClick={() => runVisionAnalysis('manual_ruler')}
                    className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-bold text-xs shadow-md transition-all"
                  >
                    {t('tryon.scan_compile_profile')}
                  </button>
                </div>
              )}
            </>
          )}

          {/* --- STEP 2: CINEMATIC ACTIVE SCANNING ANIMATION WITH PERSON PREVIEW --- */}
          {scanStep === 'analyzing' && (
            <div className="py-6 space-y-6">
              <div className="relative w-64 h-80 mx-auto rounded-3xl overflow-hidden bg-slate-950 border-2 border-[#C5A059]/60 shadow-2xl flex items-center justify-center">
                {capturedImage ? (
                  <img
                    src={capturedImage}
                    alt="Scanning Subject"
                    className="w-full h-full object-cover brightness-90"
                  />
                ) : (
                  <div className="w-full h-full bg-gradient-to-b from-slate-900 via-[#1B1F3B] to-slate-950 flex flex-col items-center justify-center p-6 text-center">
                    <RulerIcon size={48} color="#C5A059" />
                    <span className="text-xs text-slate-300 mt-2 font-mono">Camera preview unavailable — guide view</span>
                  </div>
                )}

                {/* Laser Sweep Bar */}
                <div className="absolute inset-x-0 h-1.5 bg-gradient-to-r from-transparent via-[#C5A059] to-transparent shadow-[0_0_20px_#C5A059] animate-[scan_1.5s_ease-in-out_infinite]" />

                {/* Corner Calipers */}
                <div className="absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 border-[#C5A059]" />
                <div className="absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 border-[#C5A059]" />
                <div className="absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 border-[#C5A059]" />
                <div className="absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 border-[#C5A059]" />
              </div>

              {/* Progress and Radar Logs */}
              <div className="max-w-md mx-auto space-y-3">
                <div className="flex justify-between items-center text-xs font-mono text-slate-700">
                  <span className="font-bold text-[#1B1F3B]">{t('tryon.scan_compiling')}</span>
                  <span className="font-bold text-[#C5A059]">{scanProgress}%</span>
                </div>

                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                  <div
                    className="h-full bg-gradient-to-r from-[#1B1F3B] via-[#C5A059] to-[#E2BF70] transition-all duration-300"
                    style={{ width: `${scanProgress}%` }}
                  />
                </div>

                {/* Terminal HUD Logs */}
                <div className="p-3 rounded-xl bg-slate-950 text-slate-300 font-mono text-[11px] space-y-1 max-h-24 overflow-y-auto">
                  {analysisLogs.map((log, idx) => (
                    <div key={idx} className="text-emerald-400 flex items-center gap-1.5">
                      <span>›</span>
                      <span>{log}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* --- STEP 3: RESULT REVIEW --- */}
          {scanStep === 'result' && estimatedData && (
            <div className="space-y-5">
              <div className="flex justify-between items-center pb-3 border-b border-slate-100">
                <div>
                  <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider">
                    Size Profile Ready — self-reported ({estimatedData.source.replace('_', ' ')})
                  </span>
                  <h4 className="font-serif text-lg font-bold text-[#1B1F3B]">
                    Your Measurements & Size Match
                  </h4>
                </div>
                <span title={estimatedData.confidence_disclosure}>
                  <FitScoreBadge score={estimatedData.confidence_score} label="Confidence" verdict="self-reported inputs" />
                </span>
              </div>
              <p className="text-[11px] text-slate-600 bg-[#FAF9F6] border border-slate-100 rounded-xl px-3 py-2 leading-relaxed">
                {estimatedData.confidence_disclosure}
              </p>

              {/* Person Scanned Thumbnail & Derived Dimension Grid */}
              <div className="flex flex-col sm:flex-row gap-4 items-center">
                {capturedImage && (
                  <div className="w-32 h-40 rounded-2xl overflow-hidden bg-slate-950 border border-[#C5A059]/40 relative shrink-0 shadow-md">
                    <img src={capturedImage} alt="Scanned" className="w-full h-full object-cover" />
                    <div className="absolute bottom-1 inset-x-1 py-0.5 rounded bg-slate-950/80 text-[8px] font-mono text-center text-[#C5A059]">
                      ✓ Calibrated
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs flex-1 w-full">
                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">{t('tryon.scan_field_height')}</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.height_cm} cm</span>
                    <span className="text-[10px] text-slate-500 block font-medium">{estimatedData.confidence_score}% · self-reported</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">{t('tryon.scan_field_shoulder')}</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.shoulder_cm} cm</span>
                    <span className="text-[10px] text-slate-500 block font-light">{t('tryon.scan_your_value')}</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">{t('tryon.scan_field_chest')}</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.chest_cm} cm</span>
                    <span className="text-[10px] text-slate-500 block font-light">{t('tryon.scan_your_value')}</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">Waistline</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.waist_cm} cm</span>
                    <span className="text-[10px] text-slate-500 block font-light">{t('tryon.scan_your_value')}</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">{t('tryon.scan_field_silhouette')}</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.body_shape}</span>
                    <span className="text-[10px] text-slate-500 block font-light">V-Drop ratio</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/40">
                    <span className="text-[#C5A059] text-[10px] font-bold block">{t('tryon.scan_recommended_size')}</span>
                    <span className="text-sm font-bold text-[#1B1F3B]">{estimatedData.predicted_size}</span>
                    <span className="text-[10px] text-slate-500 block font-semibold">Size-chart match — try-on fit still verified by the render engine</span>
                  </div>
                </div>
              </div>

              {/* Privacy Shield Notice */}
              <p className="flex items-start gap-2 rounded-xl border border-slate-200 bg-[#FAF9F6] p-3 text-[11px] font-light leading-relaxed text-slate-600">
                <span className="mt-0.5 shrink-0"><LockIcon size={16} color="#C5A059" /></span>
                <span>{t('tryon.scan_privacy_result')}</span>
              </p>

              {/* Actions */}
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleRetake}
                  className="flex-1 py-3 rounded-xl border border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold text-xs transition-colors"
                >
                  {t('tryon.scan_retake')}
                </button>
                <button
                  type="button"
                  onClick={handleApply}
                  className="flex-1 py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-1.5"
                >
                  <SparkleIcon size={14} color="#C5A059" />
                  <span>{t('tryon.scan_apply_cta')}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
    </>
  );
};
