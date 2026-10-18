import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { usePrefersReducedMotion } from "./InteractionPrimitives";

/**
 * Reveal — intersection-observed entrance animations.
 *
 * Content fades in as it scrolls into view, with staggered children
 * for lists/grids. Respects prefers-reduced-motion (renders instantly).
 * Uses IntersectionObserver — no scroll listeners, no layout thrashing.
 */

interface RevealProps {
  children: React.ReactNode;
  /** Delay before this group starts (ms) */
  delay?: number;
  /** Stagger between children (ms) — only when used with RevealGroup */
  stagger?: number;
  /** Initial offset Y (px) */
  y?: number;
  /** Duration (ms) */
  duration?: number;
  className?: string;
  /** Threshold for intersection (0-1) */
  threshold?: number;
  /** Only animate once */
  once?: boolean;
  as?: keyof JSX.IntrinsicElements;
}

export const Reveal: React.FC<RevealProps> = ({
  children,
  delay = 0,
  y = 12,
  duration = 480,
  className = "",
  threshold = 0.12,
  once = true,
  as: Tag = "div",
}) => {
  const reduceMotion = usePrefersReducedMotion();
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (reduceMotion) {
      setVisible(true);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          if (once) obs.disconnect();
        } else if (!once) {
          setVisible(false);
        }
      },
      { threshold, rootMargin: "0px 0px -40px 0px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [reduceMotion, threshold, once]);

  if (reduceMotion) {
    return <div className={className}>{children}</div>;
  }

  const MotionTag = motion[Tag as keyof typeof motion] as typeof motion.div;

  return (
    <MotionTag
      ref={ref as never}
      initial={{ opacity: 0, y }}
      animate={visible ? { opacity: 1, y: 0 } : { opacity: 0, y }}
      transition={{
        duration: duration / 1000,
        delay: delay / 1000,
        ease: [0.25, 1, 0.5, 1] as const,
      }}
      className={className}
    >
      {children}
    </MotionTag>
  );
};

/**
 * RevealGroup — staggers children automatically.
 * Each child gets an increasing delay.
 */
export const RevealGroup: React.FC<{
  children: React.ReactNode;
  stagger?: number;
  delay?: number;
  y?: number;
  duration?: number;
  className?: string;
  threshold?: number;
  once?: boolean;
}> = ({
  children,
  stagger = 70,
  delay = 0,
  y = 12,
  duration = 480,
  className = "",
  threshold = 0.1,
  once = true,
}) => {
  const reduceMotion = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (reduceMotion) {
      setVisible(true);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          if (once) obs.disconnect();
        } else if (!once) {
          setVisible(false);
        }
      },
      { threshold, rootMargin: "0px 0px -32px 0px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [reduceMotion, threshold, once]);

  if (reduceMotion) {
    return <div ref={ref} className={className}>{children}</div>;
  }

  const childArray = React.Children.toArray(children);

  return (
    <div ref={ref} className={className}>
      {childArray.map((child, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y }}
          animate={visible ? { opacity: 1, y: 0 } : { opacity: 0, y }}
          transition={{
            duration: duration / 1000,
            delay: (delay + i * stagger) / 1000,
            ease: [0.25, 1, 0.5, 1] as const,
          }}
        >
          {child}
        </motion.div>
      ))}
    </div>
  );
};

/**
 * CountUp — animates a number from 0 to target on reveal.
 */
export const CountUp: React.FC<{
  value: number;
  duration?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}> = ({ value, duration = 800, decimals = 0, prefix = "", suffix = "", className = "" }) => {
  const reduceMotion = usePrefersReducedMotion();
  const [display, setDisplay] = useState(reduceMotion ? value : 0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  useEffect(() => {
    if (reduceMotion) {
      setDisplay(value);
      return;
    }
    const el = ref.current;
    if (!el || started.current) return;

    const obs = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting || started.current) return;
      started.current = true;
      obs.disconnect();

      const startTime = performance.now();
      const animate = (now: number) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        setDisplay(eased * value);
        if (progress < 1) requestAnimationFrame(animate);
        else setDisplay(value);
      };
      requestAnimationFrame(animate);
    }, { threshold: 0.3 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [value, duration, reduceMotion]);

  // Reset on value change
  useEffect(() => {
    if (!reduceMotion) started.current = false;
  }, [value, reduceMotion]);

  const formatted = decimals > 0
    ? display.toFixed(decimals)
    : Math.round(display).toLocaleString();

  return (
    <span ref={ref} className={className} aria-live="polite">
      {prefix}{formatted}{suffix}
    </span>
  );
};
