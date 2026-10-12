import React, { useState, useEffect } from 'react';
import { ConfitLogo } from './ConfitLogo';

/**
 * Brand splash (Logo #3). Shown once per browser session on the first
 * consumer page load: a white field, the centred official logo, and one thin
 * progress rule. No blur, no pulsing halo, no italic slogan.
 *
 * StrictMode-safe session guard (kept from the previous implementation).
 * Under React 18 <StrictMode>, effects run setup → cleanup → setup. Arming the
 * timers inside an effect that cleanup can cancel left the splash stuck on top
 * of the app in development, swallowing every click. A module-level `armed`
 * flag makes the side effect idempotent: timers are created exactly once.
 */
let splashArmed = false;

export const SplashScreen: React.FC<{ onComplete?: () => void }> = ({ onComplete }) => {
  const [isVisible, setIsVisible] = useState(false);
  const [isFading, setIsFading] = useState(false);

  useEffect(() => {
    if (splashArmed) return;
    splashArmed = true;

    // Only display the splash on a fresh session load.
    if (sessionStorage.getItem('confit_splash_viewed')) return;
    sessionStorage.setItem('confit_splash_viewed', 'true');
    setIsVisible(true);

    setTimeout(() => {
      setIsFading(true);
    }, 1100);

    setTimeout(() => {
      setIsVisible(false);
      if (onComplete) onComplete();
    }, 1500);
  }, [onComplete]);

  if (!isVisible) return null;

  return (
    <div
      aria-hidden="true"
      role="presentation"
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center bg-white transition-opacity duration-300 ${
        isFading ? 'opacity-0 pointer-events-none' : 'opacity-100'
      }`}
    >
      <div className="flex flex-col items-center">
        <ConfitLogo variant="full" theme="dark" size="lg" />
        <div className="mt-10 h-px w-24 overflow-hidden bg-[#E8E6E2]">
          <div className="confit-splash-rule h-full w-full bg-[#252729]" />
        </div>
      </div>
    </div>
  );
};
