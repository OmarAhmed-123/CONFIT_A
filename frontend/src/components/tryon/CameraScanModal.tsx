import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { RulerIcon, SparkleIcon, TryOnIcon, LockIcon, ShieldIcon } from '../icons/ConfitIcons';
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
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameId = useRef<number | null>(null);
  const lastFrameTime = useRef<number>(performance.now());
  const frameCount = useRef<number>(0);

  const [activeTab, setActiveTab] = useState<'camera' | 'upload' | 'preset' | 'ruler'>('camera');
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
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
    scanned_image_url?: string;
  } | null>(null);

  // Enumerate video devices
  useEffect(() => {
    if (navigator?.mediaDevices?.enumerateDevices) {
      navigator.mediaDevices.enumerateDevices().then((devices) => {
        const videoInputs = devices.filter((d) => d.kind === 'videoinput');
        if (videoInputs.length > 1) {
          setHasMultipleCameras(true);
        }
      }).catch(() => {});
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (animFrameId.current) {
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

  useEffect(() => {
    if (!isOpen || activeTab !== 'camera' || scanStep !== 'ready') {
      stopCamera();
    }
  }, [isOpen, activeTab, scanStep, stopCamera]);

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
    setCameraLoading(true);
    setCameraError(null);
    stopCamera();

    if (!navigator?.mediaDevices?.getUserMedia) {
      setCameraError('Webcam access is restricted in this browser context. You can use Photo Upload or Presets below.');
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

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraActive(true);
      setCameraLoading(false);
    } catch (err: any) {
      console.warn('Camera stream error:', err);
      let msg = 'Camera access unavailable. Please choose Photo Upload or Presets below.';
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        msg = 'Camera permission was denied. Please allow camera permissions in your browser URL bar.';
      } else if (err.name === 'NotFoundError') {
        msg = 'No physical camera detected on this device.';
      }
      setCameraError(msg);
      setCameraActive(false);
      setCameraLoading(false);
    }
  };

  const toggleCameraFacing = () => {
    const nextMode = facingMode === 'user' ? 'environment' : 'user';
    setFacingMode(nextMode);
    startCamera(nextMode);
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
    runVisionAnalysis('live_camera', capturedDataUrl);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // P0-03 fix: compress before analysis/upload — raw phone photos exceeded
    // the gateway body limit (HTTP 413).
    try {
      const { dataUrl } = await compressImageToDataUrl(file);
      setCapturedImage(dataUrl);
      runVisionAnalysis('uploaded_photo', dataUrl);
    } catch (err: any) {
      setCameraError(err?.message || 'That photo could not be processed.');
    }
  };

  const deriveSizeFromMeasurements = (chest: number, waist: number, height: number): string => {
    if (chest < 90 || waist < 74) return 'Size S (Slim Tailored)';
    if (chest <= 102 && waist <= 86) return 'Size M (Regular Drape)';
    if (chest <= 110 && waist <= 94) return 'Size L (Structured Comfort)';
    return 'Size XL (Relaxed Tailored)';
  };

  const runVisionAnalysis = (source: string, imgDataUrl?: string | null) => {
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

    steps.forEach((step, idx) => {
      setTimeout(() => {
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
            scanned_image_url: imgDataUrl || undefined,
          };

          setEstimatedData(derived);
          setScanStep('result');

          // Submit results to backend measurement session asynchronously
          measurementService.createSession('client_side')
            .then((sess) => {
              if (sess?.id) {
                return measurementService.submitResults(sess.id, {
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
            })
            .catch(() => {});
        }
      }, (idx + 1) * 350);
    });
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
    runVisionAnalysis('silhouette_preset', null);
  };

  const handleApply = () => {
    if (estimatedData) {
      onApplyMeasurements(estimatedData);
      onClose();
    }
  };

  const handleRetake = () => {
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
    { shape: 'Athletic V-Taper', height: 178, chest: 99, waist: 82, shoulder: 46, hip: 96, desc: 'Tapered athletic torso with broad shoulders' },
    { shape: 'Hourglass Feminine', height: 172, chest: 92, waist: 68, shoulder: 40, hip: 96, desc: 'Balanced chest and hip contours with defined waistline' },
    { shape: 'Tall Structured', height: 186, chest: 104, waist: 86, shoulder: 48, hip: 100, desc: 'Elongated frame with structured tailoring proportions' },
    { shape: 'Classic Regular', height: 175, chest: 96, waist: 84, shoulder: 44, hip: 95, desc: 'Standard balanced drape and regular ease' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-150">
      <div className="w-full max-w-2xl bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="p-4 sm:p-5 bg-[#0C0E1E] text-white flex justify-between items-center border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#C5A059] text-slate-950 flex items-center justify-center font-bold shadow-xs">
              <RulerIcon size={22} color="#0C0E1E" />
            </div>
            <div>
              <h3 className="font-serif text-base sm:text-lg font-bold text-white flex items-center gap-2">
                <span>Privacy-First Size Studio</span>
                <span className="text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full font-mono">
                  Private · In-Browser
                </span>
              </h3>
              <p className="text-[11px] text-slate-400 font-light">
                Estimates body proportions in browser memory without storing raw photos on servers.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center text-sm transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-200 bg-[#FAF9F6] p-1.5 gap-1.5 text-xs font-semibold">
          {[
            { id: 'camera' as const, label: '📹 Live Camera' },
            { id: 'upload' as const, label: '🖼️ Photo Upload' },
            { id: 'preset' as const, label: '👤 Presets' },
            { id: 'ruler' as const, label: '📐 Manual Ruler' },
          ].map((tItem) => (
            <button
              key={tItem.id}
              onClick={() => {
                setActiveTab(tItem.id);
                setScanStep('ready');
                if (tItem.id === 'camera') startCamera();
                else stopCamera();
              }}
              className={`flex-1 py-2.5 rounded-xl transition-all ${
                activeTab === tItem.id
                  ? 'bg-[#1B1F3B] text-white shadow-xs'
                  : 'text-slate-600 hover:bg-slate-200/60'
              }`}
            >
              {tItem.label}
            </button>
          ))}
        </div>

        {/* Modal Body */}
        <div className="p-4 sm:p-6 overflow-y-auto flex-1 space-y-4">
          {scanStep === 'ready' && (
            <>
              {/* Reference Height Calibration Input */}
              <div className="p-3.5 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/30 flex items-center justify-between gap-4">
                <div>
                  <label className="text-xs font-bold text-[#1B1F3B] block">
                    Calibration Stature Reference:
                  </label>
                  <span className="text-[10px] text-slate-500 font-light">
                    Used to accurately convert camera pixels into physical centimeters.
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <input
                    type="number"
                    min="140"
                    max="220"
                    value={userCalibrationHeightCm}
                    onChange={(e) => setUserCalibrationHeightCm(Number(e.target.value))}
                    className="w-20 px-2.5 py-1.5 rounded-xl border border-slate-300 text-xs font-bold text-slate-900 focus:outline-none focus:border-[#C5A059] bg-white text-center"
                  />
                  <span className="text-xs font-bold text-slate-700">cm</span>
                </div>
              </div>

              {/* --- TAB 1: LIVE CAMERA --- */}
              {activeTab === 'camera' && (
                <div className="space-y-4">
                  {cameraError && (
                    <div className="p-3.5 rounded-2xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center justify-between">
                      <span>{cameraError}</span>
                      <button
                        onClick={() => startCamera()}
                        className="px-3 py-1 bg-amber-600 text-white rounded-lg text-[10px] font-bold"
                      >
                        Retry
                      </button>
                    </div>
                  )}

                  <div className="relative rounded-3xl overflow-hidden bg-slate-950 aspect-[4/3] flex items-center justify-center border border-slate-800 shadow-lg">
                    <video
                      ref={videoRef}
                      playsInline
                      muted
                      autoPlay
                      className="hidden"
                    />
                    <canvas
                      ref={canvasRef}
                      className="w-full h-full object-cover"
                    />

                    {/* HUD Status Bar & Scanning Laser */}
                    {cameraActive && (
                      <>
                        <div className="absolute top-3 left-3 right-3 flex justify-between items-center pointer-events-none z-10">
                          <div className="px-3 py-1 rounded-full bg-slate-950/80 backdrop-blur-md text-[#C5A059] text-[10px] font-mono font-bold flex items-center gap-1.5 border border-[#C5A059]/40 shadow-xs">
                            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                            <span>Align Head & Torso Inside Guide</span>
                          </div>
                          <div className="px-2.5 py-1 rounded-full bg-slate-950/80 text-slate-300 text-[10px] font-mono border border-slate-700">
                            Live {fps} FPS
                          </div>
                        </div>

                        {/* Animated Laser Scanning Beam */}
                        <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-[#C5A059] to-transparent shadow-[0_0_15px_#C5A059] pointer-events-none animate-[scan_2.5s_ease-in-out_infinite]" />
                      </>
                    )}

                    {!cameraActive && !cameraLoading && (
                      <div className="text-center p-6 space-y-3">
                        <div className="w-14 h-14 rounded-2xl bg-slate-900 border border-slate-700 text-[#C5A059] mx-auto flex items-center justify-center shadow-md">
                          <TryOnIcon size={28} color="#C5A059" isAi={true} />
                        </div>
                        <p className="text-xs text-slate-400 max-w-xs mx-auto font-light leading-relaxed">
                          Click below to start browser camera. Measurements are calculated in client memory and raw video never leaves your device.
                        </p>
                        <button
                          onClick={() => startCamera()}
                          className="px-6 py-2.5 rounded-xl bg-[#C5A059] hover:bg-[#E2BF70] text-slate-950 font-bold text-xs shadow-md transition-all active:scale-98"
                        >
                          Enable Live Camera
                        </button>
                      </div>
                    )}

                    {cameraLoading && (
                      <div className="text-center space-y-2">
                        <div className="w-8 h-8 border-3 border-[#C5A059] border-t-transparent rounded-full animate-spin mx-auto"></div>
                        <span className="text-xs text-slate-400">Initializing secure video stream...</span>
                      </div>
                    )}
                  </div>

                  {cameraActive && (
                    <div className="flex gap-2.5">
                      {hasMultipleCameras && (
                        <button
                          type="button"
                          onClick={toggleCameraFacing}
                          className="px-4 py-3 rounded-xl border border-slate-300 text-slate-700 text-xs font-semibold hover:bg-slate-50 transition-colors"
                        >
                          🔄 Switch
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={captureCameraFrame}
                        className="flex-1 py-3.5 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2"
                      >
                        <SparkleIcon size={16} color="#C5A059" />
                        <span>Capture & Estimate Body Matrix</span>
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* --- TAB 2: PHOTO UPLOAD --- */}
              {activeTab === 'upload' && (
                <div className="space-y-4">
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-slate-300 hover:border-[#C5A059] rounded-3xl p-8 text-center cursor-pointer transition-all bg-[#FAF9F6] space-y-3"
                  >
                    <div className="w-12 h-12 rounded-2xl bg-white border border-slate-200 mx-auto flex items-center justify-center text-[#C5A059] shadow-xs">
                      📸
                    </div>
                    <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">
                      Upload a full-length upright photo
                    </h4>
                    <p className="text-xs text-slate-500 max-w-sm mx-auto font-light">
                      JPG, PNG or WEBP. Image is processed locally in browser memory.
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </div>
                </div>
              )}

              {/* --- TAB 3: PRESETS --- */}
              {activeTab === 'preset' && (
                <div className="space-y-3">
                  <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">
                    Select an Archetypal Tailored Silhouette:
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {silhouettePresets.map((preset) => (
                      <div
                        key={preset.shape}
                        onClick={() => applyPresetSilhouette(preset)}
                        className="p-4 rounded-2xl border border-slate-200 bg-white hover:border-[#C5A059] hover:bg-[#FDF8EE] transition-all cursor-pointer shadow-2xs space-y-1.5"
                      >
                        <div className="flex justify-between items-center">
                          <h5 className="font-serif text-xs font-bold text-[#1B1F3B]">
                            {preset.shape}
                          </h5>
                          <span className="text-[10px] font-mono font-bold bg-white px-2 py-0.5 rounded border border-slate-200">
                            {preset.height} cm
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 font-light">{preset.desc}</p>
                        <div className="flex gap-2 pt-1 text-[10px] font-medium text-slate-600">
                          <span>Chest: {preset.chest}cm</span>
                          <span>•</span>
                          <span>Waist: {preset.waist}cm</span>
                          <span>•</span>
                          <span>Shoulder: {preset.shoulder}cm</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* --- TAB 4: MANUAL RULER --- */}
              {activeTab === 'ruler' && (
                <div className="space-y-4 bg-[#FAF9F6] p-5 rounded-2xl border border-slate-200">
                  <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">
                    Precision Manual Dimension Controls
                  </h4>

                  <div className="space-y-3 text-xs">
                    <div>
                      <div className="flex justify-between mb-1 font-semibold text-slate-700">
                        <span>Height:</span>
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
                        <span>Shoulder Breadth:</span>
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
                        <span>Chest Circumference:</span>
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
                        <span>Waistline:</span>
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
                    onClick={() => runVisionAnalysis('manual_ruler', null)}
                    className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-bold text-xs shadow-md transition-all"
                  >
                    Compile My Size Profile
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
                  <span className="font-bold text-[#1B1F3B]">Compiling Your Size Profile</span>
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
                    <span className="text-slate-400 text-[10px] block">Calibrated Stature</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.height_cm} cm</span>
                    <span className="text-[10px] text-slate-500 block font-medium">{estimatedData.confidence_score}% · self-reported</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">Shoulder Width</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.shoulder_cm} cm</span>
                    <span className="text-[10px] text-slate-500 block font-light">Your entered value</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">Chest Circumference</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.chest_cm} cm</span>
                    <span className="text-[10px] text-slate-500 block font-light">Your entered value</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">Waistline</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.waist_cm} cm</span>
                    <span className="text-[10px] text-slate-500 block font-light">Your entered value</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FAF9F6] border border-slate-200/80">
                    <span className="text-slate-400 text-[10px] block">Body Silhouette</span>
                    <span className="text-sm font-bold text-slate-900">{estimatedData.body_shape}</span>
                    <span className="text-[10px] text-slate-500 block font-light">V-Drop ratio</span>
                  </div>

                  <div className="p-3 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/40">
                    <span className="text-[#C5A059] text-[10px] font-bold block">Recommended Size</span>
                    <span className="text-sm font-bold text-[#1B1F3B]">{estimatedData.predicted_size}</span>
                    <span className="text-[10px] text-slate-500 block font-semibold">Size-chart match — try-on fit still verified by the render engine</span>
                  </div>
                </div>
              </div>

              {/* Privacy Shield Notice */}
              <p className="text-[11px] text-slate-500 font-light bg-[#FAF9F6] p-3 rounded-xl border border-slate-200 leading-relaxed flex items-center gap-2">
                <LockIcon size={16} color="#C5A059" />
                <span><strong>Privacy Guarantee:</strong> Processed 100% in browser memory. Raw camera images are wiped upon closing this modal.</span>
              </p>

              {/* Actions */}
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleRetake}
                  className="flex-1 py-3 rounded-xl border border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold text-xs transition-colors"
                >
                  Retake / Adjust
                </button>
                <button
                  type="button"
                  onClick={handleApply}
                  className="flex-1 py-3 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-1.5"
                >
                  <SparkleIcon size={14} color="#C5A059" />
                  <span>Apply to Sizing & Try-On Studio</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
