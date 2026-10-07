import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

/**
 * Caps-Lock detection for password fields (auth cluster pass 2).
 *
 * The single most common silent cause of "wrong password": Caps Lock is on
 * and the dots hide it. The OS state is read from the REAL keyboard event
 * (`getModifierState('CapsLock')`) — never guessed from character case —
 * and the warning drops on blur so it can't go stale while the shopper
 * types elsewhere.
 *
 * Functional: keydown/keyup update, blur reset; no network, no timers.
 * Non-functional: the hint is TEXT in a polite status region (never
 * colour/icon alone), amber not red (it is a heads-up, not an error).
 */
export const useCapsLock = () => {
  const [capsLockOn, setCapsLockOn] = useState(false);
  const keyHandler = (e: React.KeyboardEvent) => {
    setCapsLockOn(e.getModifierState?.('CapsLock') ?? false);
  };
  const reset = () => setCapsLockOn(false);
  return {
    capsLockOn,
    /** Spread onto the password input. */
    capsLockProps: {
      onKeyDown: keyHandler,
      onKeyUp: keyHandler,
      onBlur: reset,
    },
  };
};

export const CapsLockHint: React.FC<{ on: boolean }> = ({ on }) => {
  const { t } = useTranslation();
  return (
    <p role="status" aria-live="polite" className="min-h-0">
      {on && (
        <span className="mt-1 block text-[11px] font-semibold text-amber-700">
          {t('auth.caps_lock_on')}
        </span>
      )}
    </p>
  );
};
