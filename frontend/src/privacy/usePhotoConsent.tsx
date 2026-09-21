import React, { useCallback, useRef, useState } from 'react';
import { ConsentDialog } from './ConsentDialog';
import { useConsentStore, type ConsentPurpose } from './consentStore';

export interface PhotoConsentController {
  /**
   * Resolves `true` when the user has granted consent for this purpose under
   * the current notice version, and `false` when they declined (or the modal
   * was dismissed). Await it INSIDE the file-selected / scan-started handler,
   * before any bytes leave the device.
   */
  requestConsent: () => Promise<boolean>;
  /** True while the notice is on screen. Callers use it to hold their own UI. */
  isPrompting: boolean;
  /** Render this next to the flow's JSX. */
  consentDialog: React.ReactNode;
}

/**
 * The single gate in front of every photo-processing flow.
 *
 * WHY A HOOK RATHER THAN A CHECKBOX IN EACH MODAL
 *   Four flows (try-on, visual search, wardrobe, body scan) previously handled
 *   consent three different ways: one asserted it (`consentGranted: true`),
 *   one had an untracked local boolean, and two had nothing at all. Copying a
 *   checkbox into a fifth flow is how the inconsistency happened. Here the
 *   notice, the record and the version check live in one place, and a new flow
 *   gets the correct behaviour by calling one function.
 *
 * FAIL-CLOSED BY CONSTRUCTION
 *   `requestConsent` returns a promise that resolves to `false` on every path
 *   that is not an explicit acceptance: decline, Escape, backdrop dismissal,
 *   and component unmount while the notice is open (the resolver is drained on
 *   unmount). A caller cannot accidentally continue on a falsy value, because
 *   the promise never resolves truthy without a real button press.
 *
 * @param purpose Which purpose this gate covers. Consent is per purpose, so a
 *   try-on grant does not silently authorise wardrobe tagging.
 */
export function usePhotoConsent(purpose: ConsentPurpose): PhotoConsentController {
  const [isPrompting, setIsPrompting] = useState(false);
  const resolverRef = useRef<((granted: boolean) => void) | null>(null);
  const hasConsent = useConsentStore((s) => s.hasConsent);
  const grant = useConsentStore((s) => s.grant);

  const settle = useCallback((granted: boolean, options?: { rememberForSession: boolean }) => {
    if (granted && options) grant(purpose, options);
    setIsPrompting(false);
    const resolve = resolverRef.current;
    resolverRef.current = null;
    resolve?.(granted);
  }, [grant, purpose]);

  const requestConsent = useCallback(() => {
    // Already granted under the CURRENT notice version: no second prompt.
    if (hasConsent(purpose)) return Promise.resolve(true);
    setIsPrompting(true);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  }, [hasConsent, purpose]);

  // Unmounting mid-prompt must not leave the caller awaiting forever, and must
  // not be read as agreement. Drain the resolver as a decline.
  React.useEffect(() => () => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    resolve?.(false);
  }, []);

  const consentDialog = (
    <ConsentDialog
      purpose={isPrompting ? purpose : null}
      onAccept={(options) => settle(true, options)}
      onDecline={() => settle(false)}
    />
  );

  return { requestConsent, isPrompting, consentDialog };
}

export default usePhotoConsent;
