import React, { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Rocket, Sparkles, Send, ShoppingBag, Wand2, Zap } from "lucide-react";
import { buttonMotion, type ButtonIntent } from "./buttonMotion";
import { usePrefersReducedMotion } from "./InteractionPrimitives";

/**
 * LaunchButton — the signature CONFIT commit interaction.
 *
 * Realizes the "arrow → rocket with rising bubbles" metaphor:
 *   idle      → arrow glyph points forward (direction)
 *   hover     → arrow nudges, hinting at propulsion
 *   active    → brief compression (tension before launch)
 *   launching → arrow crossfades to rocket, exhaust particles rise
 *   launched  → rocket trails off, success check pops in
 *
 * The animation is pure CSS (interactive-animations.css) driven by
 * data-launch-state. JS only toggles the state attribute and resets
 * after the success dwell.
 *
 * Respects prefers-reduced-motion: particles suppressed, morph is instant.
 * Accessible name never changes to an icon — text carries meaning.
 */

type LaunchVariant = "arrow-rocket" | "spark-magic" | "send-flight" | "bag-check" | "zap-action";
type LaunchState = "idle" | "launching" | "launched";

interface LaunchButtonProps {
  children: React.ReactNode;
  onClick?: () => void | Promise<void>;
  type?: "button" | "submit";
  variant?: LaunchVariant;
  intent?: ButtonIntent;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
  size?: "sm" | "md" | "lg";
  fullWidth?: boolean;
  "data-testid"?: string;
  "aria-label"?: string;
}

const VARIANT_ICONS: Record<LaunchVariant, { idle: React.ReactNode; launching: React.ReactNode }> = {
  "arrow-rocket": {
    idle: <ArrowRight size={16} strokeWidth={2.2} aria-hidden="true" />,
    launching: <Rocket size={16} strokeWidth={1.9} aria-hidden="true" />,
  },
  "spark-magic": {
    idle: <Sparkles size={16} strokeWidth={1.9} aria-hidden="true" />,
    launching: <Wand2 size={16} strokeWidth={1.9} aria-hidden="true" />,
  },
  "send-flight": {
    idle: <Send size={15} strokeWidth={2} aria-hidden="true" />,
    launching: <Rocket size={16} strokeWidth={1.9} aria-hidden="true" />,
  },
  "bag-check": {
    idle: <ShoppingBag size={16} strokeWidth={1.9} aria-hidden="true" />,
    launching: <ShoppingBag size={16} strokeWidth={1.9} aria-hidden="true" />,
  },
  "zap-action": {
    idle: <Zap size={16} strokeWidth={2} aria-hidden="true" />,
    launching: <Zap size={16} strokeWidth={2} aria-hidden="true" />,
  },
};

const SIZE_CLASSES: Record<string, string> = {
  sm: "min-h-9 px-4 text-xs gap-2",
  md: "min-h-11 px-5 text-sm gap-2.5",
  lg: "min-h-12 px-7 text-sm gap-3",
};

export const LaunchButton: React.FC<LaunchButtonProps> = ({
  children,
  onClick,
  type = "button",
  variant = "arrow-rocket",
  intent = "progressive",
  disabled = false,
  loading = false,
  className = "",
  size = "md",
  fullWidth = false,
  "data-testid": testId,
  "aria-label": ariaLabel,
}) => {
  const reduceMotion = usePrefersReducedMotion();
  const [launchState, setLaunchState] = useState<LaunchState>("idle");
  const [isPending, setIsPending] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync external loading prop
  useEffect(() => {
    if (loading) {
      setIsPending(true);
      setLaunchState("launching");
    } else if (isPending && !loading) {
      // External loading finished → show success briefly
      setIsPending(false);
      setLaunchState("launched");
      resetTimer.current = setTimeout(() => setLaunchState("idle"), 1800);
    }
    return () => { if (resetTimer.current) clearTimeout(resetTimer.current); };
  }, [loading, isPending]);

  const handleClick = useCallback(async (e: React.MouseEvent<HTMLButtonElement>) => {
    if (disabled || isPending || launchState === "launching") {
      e.preventDefault();
      return;
    }
    if (!onClick) return;

    // If onClick is async, drive the launch sequence through its lifecycle
    const result = onClick();
    if (result && typeof (result as Promise<void>).then === "function") {
      setIsPending(true);
      setLaunchState("launching");
      try {
        await result;
        setIsPending(false);
        setLaunchState("launched");
        resetTimer.current = setTimeout(() => setLaunchState("idle"), 1800);
      } catch {
        setIsPending(false);
        setLaunchState("idle");
      }
    } else {
      // Sync action — brief launch flourish
      setLaunchState("launching");
      resetTimer.current = setTimeout(() => {
        setLaunchState("launched");
        resetTimer.current = setTimeout(() => setLaunchState("idle"), 1400);
      }, 420);
    }
  }, [disabled, isPending, launchState, onClick]);

  useEffect(() => {
    return () => { if (resetTimer.current) clearTimeout(resetTimer.current); };
  }, []);

  const icons = VARIANT_ICONS[variant];
  const isLaunching = launchState === "launching" || isPending;
  const isLaunched = launchState === "launched";

  return (
    <button data-motion="neutral" data-motion-tone="icon"
      type={type}
      onClick={handleClick}
      disabled={disabled}
      aria-disabled={disabled || isPending}
      aria-busy={isPending}
      aria-label={ariaLabel}
      data-launch=""
      data-launch-state={launchState}
      data-launch-variant={variant}
      data-testid={testId}
      {...buttonMotion({ intent })}
      className={[
        "relative inline-flex items-center justify-center",
        "rounded-xl font-semibold tracking-wide",
        "bg-brand-charcoal text-white",
        "hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        "transition-colors duration-200",
        SIZE_CLASSES[size],
        fullWidth ? "w-full" : "",
        className,
      ].filter(Boolean).join(" ")}
    >
      <span className="flex items-center justify-center gap-2">
        {/* Glyph morph container */}
        <span className="confit-launch-glyph" aria-hidden="true">
          <span className="confit-launch-arrow">{icons.idle}</span>
          <span className="confit-launch-rocket">{icons.launching}</span>
          <span className="confit-launch-success">
            <Check size={14} strokeWidth={2.6} className="text-emerald-400" />
          </span>
          {/* Exhaust particles */}
          {!reduceMotion && (
            <span className="confit-launch-exhaust" aria-hidden="true">
              <span className="confit-launch-particle" />
              <span className="confit-launch-particle" />
              <span className="confit-launch-particle" />
            </span>
          )}
        </span>

        {/* Label — text never animates, only the glyph does */}
        <span className="relative">
          {isLaunched ? "Done" : children}
        </span>
      </span>

      {/* Pending spinner overlay (when async) */}
      {isPending && (
        <span
          aria-hidden="true"
          className="absolute inset-0 flex items-center justify-center rounded-xl bg-brand-charcoal/90"
        >
          <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white motion-safe:animate-spin" />
        </span>
      )}
    </button>
  );
};

/**
 * LaunchIcon — standalone morphing glyph for use inside existing ActionButton
 * or any custom control. Same CSS engine, no button wrapper.
 */
export const LaunchIcon: React.FC<{
  state: LaunchState;
  variant?: LaunchVariant;
  size?: number;
  className?: string;
}> = ({ state, variant = "arrow-rocket", size = 16, className = "" }) => {
  const reduceMotion = usePrefersReducedMotion();
  const icons = VARIANT_ICONS[variant];

  return (
    <span
      data-launch=""
      data-launch-state={state}
      data-launch-variant={variant}
      className={`confit-launch-glyph ${className}`}
      aria-hidden="true"
      style={{ width: size, height: size }}
    >
      <span className="confit-launch-arrow">{icons.idle}</span>
      <span className="confit-launch-rocket">{icons.launching}</span>
      <span className="confit-launch-success">
        <Check size={Math.round(size * 0.85)} strokeWidth={2.6} className="text-emerald-500" />
      </span>
      {!reduceMotion && (
        <span className="confit-launch-exhaust" aria-hidden="true">
          <span className="confit-launch-particle" />
          <span className="confit-launch-particle" />
          <span className="confit-launch-particle" />
        </span>
      )}
    </span>
  );
};
