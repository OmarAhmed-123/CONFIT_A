import React, { useState, useEffect } from 'react';
import { ConfitLogo } from './ConfitLogo';

export const SplashScreen: React.FC<{ onComplete?: () => void }> = ({ onComplete }) => {
  const [isVisible, setIsVisible] = useState(false);
  const [isFading, setIsFading] = useState(false);

  useEffect(() => {
    // Only display splash on fresh session load
    const hasSeenSplash = sessionStorage.getItem('confit_splash_viewed');
    if (!hasSeenSplash) {
      setIsVisible(true);
      sessionStorage.setItem('confit_splash_viewed', 'true');

      const fadeTimer = setTimeout(() => {
        setIsFading(true);
      }, 1100);

      const hideTimer = setTimeout(() => {
        setIsVisible(false);
        if (onComplete) onComplete();
      }, 1500);

      return () => {
        clearTimeout(fadeTimer);
        clearTimeout(hideTimer);
      };
    }
  }, [onComplete]);

  if (!isVisible) return null;

  return (
    <div
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center bg-[#0C0E1E] text-white transition-opacity duration-400 ${
        isFading ? 'opacity-0 pointer-events-none' : 'opacity-100'
      }`}
      style={{ backdropFilter: 'blur(20px)' }}
    >
      <div className="flex flex-col items-center text-center px-6 space-y-5 animate-in fade-in zoom-in-95 duration-500">
        <div className="relative">
          <div className="absolute -inset-4 rounded-full bg-[#C5A059]/20 blur-xl animate-pulse" />
          <ConfitLogo variant="full" theme="light" size="lg" />
        </div>

        <div className="space-y-2 pt-2">
          <div className="h-px w-16 bg-[#C5A059]/50 mx-auto" />
          <p className="font-serif italic text-sm sm:text-base text-[#C5A059] tracking-wider">
            Where Style Meets Your Character
          </p>
          <span className="text-[10px] uppercase tracking-[0.25em] text-slate-400 block font-light">
            Precision AI Fashion & Virtual Sizing
          </span>
        </div>

        <div className="pt-6">
          <div className="w-10 h-0.5 bg-slate-800 rounded-full overflow-hidden">
            <div className="w-full h-full bg-[#C5A059] origin-left animate-[marquee_1.2s_ease-in-out_infinite]" />
          </div>
        </div>
      </div>
    </div>
  );
};
