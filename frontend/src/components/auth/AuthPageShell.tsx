import React from 'react';
import { motion } from 'framer-motion';

import { ConfitLogo } from '../common/ConfitLogo';
import { usePrefersReducedMotion } from '../common/InteractionPrimitives';

/**
 * AuthPageShell — the ONE card every email-landing auth page stands on.
 *
 * Before this component the identical "cream page + centered white card +
 * logo + entrance tween" markup existed THREE times (ResetPasswordView's
 * local Shell, VerifyEmailView inline, EmailUnsubscribeView inline), each
 * with its own copy of the reduced-motion handling. One shell now owns:
 *  · the landmark (<main>) and card geometry (max-w-md, rounded-3xl),
 *  · the brand mark placement,
 *  · the entrance: 400ms rise/fade on the luxury curve
 *    cubic-bezier(0.25, 1, 0.5, 1) — skipped entirely under
 *    prefers-reduced-motion (initial=false, no 0-duration flash).
 */
export const AuthPageShell: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const reduce = usePrefersReducedMotion();
  return (
    <main className="min-h-screen bg-[#FAF9F6] px-4 py-14">
      <motion.section
        initial={reduce ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={
          reduce ? { duration: 0 } : { duration: 0.4, ease: [0.25, 1, 0.5, 1] }
        }
        className="mx-auto w-full max-w-md rounded-3xl border border-slate-200/80 bg-white p-8 text-center shadow-sm"
      >
        <div className="mx-auto mb-5 flex justify-center">
          <ConfitLogo variant="compact" theme="dark" size="sm" />
        </div>
        {children}
      </motion.section>
    </main>
  );
};
