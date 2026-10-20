import React, { useState, useEffect, useRef } from 'react';
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
 * flag makes the side effect idempotent: the session is claimed exactly once.
 *
 * That constraint is why the work is split across two effects rather than one:
 *
 *   1. CLAIM — decides whether this load shows the splash, once per module.
 *      It owns no timers, so cancelling it loses nothing.
 *   2. RUN — arms the two timers *while the splash is visible* and clears both
 *      on unmount.
 *
 * The earlier single-effect version worked around StrictMode by never cleaning
 * up — which leaked the timers. That leak is not just a test nuisance: the
 * 1500ms timer called `setState` and `onComplete` after unmount, and in the test
 * runner it fired after jsdom had torn down `window`, producing a
 * `ReferenceError: window is not defined` in whichever suite happened to be
 * running. It failed a `frontend` required check on a PR that changed no
 * TypeScript at all.
 *
 * Because effect 2 arms on visibility, the StrictMode double-invoke still ends
 * with exactly one live pair of timers (the first pair is cleared by cleanup and
 * immediately re-armed), so the splash completes in development as before.
 */
let splashArmed = false;

export const SplashScreen: React.FC<{ onComplete?: () => void }> = ({ onComplete }) => {
  const [isVisible, setIsVisible] = useState(false);
  const [isFading, setIsFading] = useState(false);

  // Latest callback without making it an effect dependency: a parent re-render
  // must not restart the timers and stretch the splash out.
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  // 1. CLAIM — once per module load, and only on a fresh session.
  useEffect(() => {
    if (splashArmed) return;
    splashArmed = true;

    // Only display the splash on a fresh session load.
    if (sessionStorage.getItem('confit_splash_viewed')) return;
    sessionStorage.setItem('confit_splash_viewed', 'true');
    setIsVisible(true);
  }, []);

  // 2. RUN — arm while visible, and always clear. A timer that outlives the
  // component is a leak: it calls setState on an unmounted tree and, in tests,
  // can fire after the environment is gone.
  useEffect(() => {
    if (!isVisible) return;

    const fadeTimer = setTimeout(() => {
      setIsFading(true);
    }, 1100);

    const finishTimer = setTimeout(() => {
      setIsVisible(false);
      if (onCompleteRef.current) onCompleteRef.current();
    }, 1500);

    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(finishTimer);
    };
  }, [isVisible]);

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
