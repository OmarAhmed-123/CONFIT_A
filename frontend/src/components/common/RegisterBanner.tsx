import React from "react";
import { useTranslation } from "react-i18next";
import { REGISTERS, type RegisterId } from "../../design/registers";

/**
 * Section masthead — the visible face of the design register system.
 * An accent dot, an uppercase section label (register ink, AA+ measured in
 * registers.ts) and a hairline rule. Pure wayfinding: no controls, no
 * status semantics, so the accent colour is never the only signal for
 * anything (§4 colour-not-only-signal).
 *
 * The editorial register (home/discover) does NOT render a banner — those
 * pages open with the hero masthead already; doubling it would be noise.
 * RTL: flex + logical margins mirror automatically; the rule grows from
 * the text side in both directions.
 */
export const RegisterBanner: React.FC<{ register: RegisterId }> = ({ register }) => {
  const { t } = useTranslation();
  if (register === "editorial") return null;
  const r = REGISTERS[register];
  return (
    <div className="register-banner flex items-center gap-2.5 mb-5" data-testid="register-banner">
      <span
        aria-hidden="true"
        className="inline-block w-2 h-2 rounded-full shrink-0"
        style={{ backgroundColor: r.accent }}
      />
      <span
        className="text-[11px] font-bold uppercase tracking-[0.18em] whitespace-nowrap"
        style={{ color: r.ink }}
      >
        {t(r.labelKey)}
      </span>
      <span aria-hidden="true" className="register-rule h-px flex-1" style={{ backgroundColor: r.accent, opacity: 0.35 }} />
    </div>
  );
};
