import React, { useEffect, useRef, useState, type HTMLAttributes } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

// A simple utility for conditional class names.
const cn = (...classes: (string | undefined | null | false)[]) => {
  return classes.filter(Boolean).join(' ');
};

// Define the type for a single gallery item.
export interface GalleryItem {
  common: string;
  binomial: string;
  photo: {
    url: string;
    text: string;
    pos?: string;
    by: string;
  };
}

// Define the props for the CircularGallery component.
interface CircularGalleryProps extends HTMLAttributes<HTMLDivElement> {
  items: GalleryItem[];
  /** Controls how far the items are from the center. */
  radius?: number;
  /**
   * Speed of idle auto-rotation. Defaults to 0 (OFF): spec 10 §6.4 bans
   * autoplay by default — rotation should be driven by the user's scroll.
   */
  autoRotateSpeed?: number;
  /** Translated accessible name for the gallery region (spec 10 §7). */
  ariaLabel?: string;
  /**
   * Translated copy injected by the host (spec 11 §7). Defaults are a dev
   * safety net only — every real caller passes t() strings.
   */
  labels?: {
    previous?: string;
    next?: string;
    position?: (current: number, total: number) => string;
    credit?: (name: string) => string;
  };
}

const CircularGallery = React.forwardRef<HTMLDivElement, CircularGalleryProps>(
  ({ items, className, radius = 600, autoRotateSpeed = 0, ariaLabel, labels, ...props }, ref) => {
    const [rotation, setRotation] = useState(0);
    // Spec 11 §7: scroll must never be the only way to rotate — the manual
    // offset is driven by real buttons and works with keyboard alone.
    const [manualOffset, setManualOffset] = useState(0);
    const [announced, setAnnounced] = useState('');
    const [isScrolling, setIsScrolling] = useState(false);
    const [reduceMotion, setReduceMotion] = useState(false);
    const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const animationFrameRef = useRef<number | null>(null);


    // Honor the user's OS-level reduced-motion preference. The gallery remains
    // visible and scroll-position addressable, but decorative auto-rotation is
    // disabled for motion-sensitive users.
    useEffect(() => {
      if (typeof window === 'undefined' || !window.matchMedia) return;
      const media = window.matchMedia('(prefers-reduced-motion: reduce)');
      const syncPreference = () => setReduceMotion(media.matches);
      syncPreference();
      media.addEventListener?.('change', syncPreference);
      return () => media.removeEventListener?.('change', syncPreference);
    }, []);

    // Effect to handle scroll-based rotation.
    useEffect(() => {
      const handleScroll = () => {
        setIsScrolling(true);
        if (scrollTimeoutRef.current) {
          clearTimeout(scrollTimeoutRef.current);
        }

        const scrollableHeight = document.documentElement.scrollHeight - window.innerHeight;
        const scrollProgress = scrollableHeight > 0 ? window.scrollY / scrollableHeight : 0;
        const scrollRotation = scrollProgress * 360;
        setRotation(scrollRotation);

        scrollTimeoutRef.current = setTimeout(() => {
          setIsScrolling(false);
        }, 150);
      };

      window.addEventListener('scroll', handleScroll, { passive: true });
      return () => {
        window.removeEventListener('scroll', handleScroll);
        if (scrollTimeoutRef.current) {
          clearTimeout(scrollTimeoutRef.current);
        }
      };
    }, []);

    // Effect for auto-rotation when not scrolling.
    useEffect(() => {
      const autoRotate = () => {
        if (!isScrolling && !reduceMotion) {
          setRotation((prev) => prev + autoRotateSpeed);
        }
        animationFrameRef.current = requestAnimationFrame(autoRotate);
      };

      animationFrameRef.current = requestAnimationFrame(autoRotate);

      return () => {
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
      };
    }, [isScrolling, autoRotateSpeed, reduceMotion]);

    if (items.length === 0) {
      return null;
    }

    const anglePerItem = 360 / items.length;
    const totalRotationValue = rotation + manualOffset;

    const L = {
      previous: labels?.previous ?? 'Previous',
      next: labels?.next ?? 'Next',
      position:
        labels?.position ??
        ((current: number, total: number) => `Item ${current} of ${total}`),
      credit: labels?.credit ?? ((name: string) => `Photo: ${name}`),
    };

    /** Index of the item currently facing the viewer. */
    const frontIndexFor = (t: number) => {
      const n = items.length;
      return ((Math.round(-t / anglePerItem) % n) + n) % n;
    };
    const frontIndex = frontIndexFor(totalRotationValue);

    const step = (direction: 1 | -1) => {
      // +1 brings the NEXT item to the front (wheel rotates backwards).
      const nextOffset = manualOffset - direction * anglePerItem;
      setManualOffset(nextOffset);
      const front = frontIndexFor(rotation + nextOffset);
      // The state change is announced as TEXT, never implied by motion (§7).
      setAnnounced(L.position(front + 1, items.length));
    };

    return (
      <div
        ref={ref}
        role="region"
        aria-label={ariaLabel ?? "Gallery"}
        className={cn('relative flex h-full w-full items-center justify-center', className)}
        style={{ perspective: '2000px' }}
        {...props}
      >
        <div
          className="relative h-full w-full"
          style={{
            transform: `rotateY(${totalRotationValue}deg)`,
            transformStyle: 'preserve-3d',
          }}
        >
          {items.map((item, i) => {
            const itemAngle = i * anglePerItem;
            const totalRotation = totalRotationValue % 360;
            const relativeAngle = (itemAngle + totalRotation + 360) % 360;
            const normalizedAngle = Math.abs(relativeAngle > 180 ? 360 - relativeAngle : relativeAngle);
            const opacity = Math.max(0.3, 1 - normalizedAngle / 180);

            return (
              <div
                key={item.photo.url}
                role="group"
                aria-label={item.common}
                className="absolute h-[400px] w-[300px]"
                style={{
                  transform: `rotateY(${itemAngle}deg) translateZ(${radius}px)`,
                  left: '50%',
                  top: '50%',
                  marginLeft: '-150px',
                  marginTop: '-200px',
                  opacity,
                  transition: 'opacity 0.3s linear',
                }}
              >
                <div className="group relative h-full w-full overflow-hidden rounded-lg border border-border bg-card/70 shadow-2xl backdrop-blur-lg dark:bg-card/30">
                  <img
                    src={item.photo.url}
                    alt={item.photo.text}
                    loading={i === 0 ? 'eager' : 'lazy'}
                    decoding="async"
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover"
                    style={{ objectPosition: item.photo.pos || 'center' }}
                  />
                  <div className="absolute inset-x-0 bottom-0 w-full bg-gradient-to-t from-black/80 to-transparent p-4 text-white">
                    <h2 className="text-xl font-bold">{item.common}</h2>
                    <em className="text-sm italic opacity-80">{item.binomial}</em>
                    <p className="mt-2 text-xs opacity-70">{L.credit(item.photo.by)}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Manual rotation controls: scroll is never the only way (§7).
            Real ≥44px buttons, visible "n / N" (kept LTR — numeric code),
            and one polite live region fed only by user steps. */}
        <div className="absolute inset-x-0 bottom-3 z-10 flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => step(-1)}
            aria-label={L.previous}
            className="min-h-11 min-w-11 flex items-center justify-center rounded-xl border border-white/30 bg-black/40 text-white backdrop-blur-sm hover:bg-black/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44]"
          >
            <span aria-hidden="true" className="rtl:rotate-180">
              <ChevronLeft size={18} />
            </span>
          </button>
          <span
            dir="ltr"
            className="rounded-full bg-black/40 px-3 py-1 text-[11px] font-semibold text-white backdrop-blur-sm"
          >
            {frontIndex + 1} / {items.length}
          </span>
          <button
            type="button"
            onClick={() => step(1)}
            aria-label={L.next}
            className="min-h-11 min-w-11 flex items-center justify-center rounded-xl border border-white/30 bg-black/40 text-white backdrop-blur-sm hover:bg-black/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44]"
          >
            <span aria-hidden="true" className="rtl:rotate-180">
              <ChevronRight size={18} />
            </span>
          </button>
        </div>
        <span className="sr-only" role="status" aria-live="polite">
          {announced}
        </span>
      </div>
    );
  },
);

CircularGallery.displayName = 'CircularGallery';

export { CircularGallery };
