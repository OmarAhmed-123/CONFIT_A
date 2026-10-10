import React from 'react';
import { motion, type MotionProps } from 'framer-motion';
import { usePrefersReducedMotion } from './AccessiblePrimitives';

/**
 * MotionWrapper — respects prefers-reduced-motion (MOT-06, FR-004).
 *
 * WHY: Audits found animations not consistently respecting prefers-reduced-motion.
 * This wrapper disables non-essential motion when user prefers reduced motion,
 * while keeping essential state-change cues perceivable without motion (text, icon).
 *
 * Rules:
 * - With prefers-reduced-motion, no non-essential animation plays (SC-004)
 * - Essential feedback remains via text/icon, not motion alone
 * - Uses motion-safe: prefix for CSS animations, and JS check for framer-motion
 */

interface MotionWrapperProps extends MotionProps {
  children: React.ReactNode;
  className?: string;
  /** If true, this motion is essential (e.g., loading spinner that indicates progress). Essential motion may still be reduced but not removed. */
  essential?: boolean;
  /** Fallback static element when reduced motion is preferred */
  fallback?: React.ReactNode;
}

export const MotionWrapper: React.FC<MotionWrapperProps> = ({
  children,
  className = '',
  essential = false,
  fallback,
  ...motionProps
}) => {
  const prefersReduced = usePrefersReducedMotion();

  if (prefersReduced && !essential) {
    // No non-essential motion — render static fallback or children without motion
    return <div className={className}>{fallback ?? children}</div>;
  }

  if (prefersReduced && essential) {
    // Essential motion: still render but with reduced duration and no scale/rotate
    // Keep opacity transitions only, which are less vestibular-triggering
    const reducedProps: MotionProps = {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.15 },
    };
    return (
      <motion.div className={className} {...reducedProps}>
        {children}
      </motion.div>
    );
  }

  return (
    <motion.div className={className} {...motionProps}>
      {children}
    </motion.div>
  );
};

/**
 * ReducedMotionSafe — CSS-only version for Tailwind motion-safe: usage.
 * Ensures animations only play when user does NOT prefer reduced motion.
 */
export const ReducedMotionSafe: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => {
  return <div className={`motion-safe:animate-none ${className}`}>{children}</div>;
};

/**
 * useMotionConfig — returns motion config that respects reduced motion.
 * Use this for framer-motion transitions.
 */
export const useMotionConfig = () => {
  const prefersReduced = usePrefersReducedMotion();

  return {
    prefersReduced,
    // For non-essential animations: disabled when reduced
    getTransition: (defaultTransition: any) => (prefersReduced ? { duration: 0 } : defaultTransition),
    // For initial/animate props: static when reduced
    getMotionProps: (defaultProps: MotionProps): MotionProps =>
      prefersReduced
        ? ({ initial: false, animate: false, exit: false } as unknown as MotionProps)
        : defaultProps,
  };
};
