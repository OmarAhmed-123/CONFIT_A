/**
 * Design registers — one brand, seven coordinated visual registers.
 *
 * WHY: the product serves very different moments (editorial browsing,
 * closet styling, fit measurement, paying, partner operations, platform
 * governance). Giving every surface family its own *register* — an accent,
 * an ink and a section label — creates recognisable variety while staying
 * inside the single CONFIT palette. This is design DIRECTION taken from the
 * approved references (editorial fashion mastheads: a section gets a colour
 * and a rule, the brand stays constant). No external site's assets, markup
 * or copy are reproduced.
 *
 * CONTRAST — every number below was MEASURED with the WCAG 2.x relative
 * luminance formula (recomputed in registers.test.tsx, so a palette edit
 * that breaks a ratio fails CI):
 *
 *   ink on body #FAF9F6 / on card #FFFFFF
 *   · editorial #6B4F1E   7.22 / 7.60   (AAA)
 *   · atelier   #6E4458   7.58 / 7.98   (AAA)
 *   · fit       #2F5547   7.94 / 8.36   (AAA)
 *   · commerce  #1B1F3B  15.28 / 16.08  (AAA)
 *   · account   #555A73   6.44 / 6.78   (AA+)
 *   · partner   #35506A   7.96 / 8.38   (AAA)
 *   · admin     #43464F   8.95 / 9.43   (AAA)
 *
 *   accent (hairline/dot — decorative, WCAG 1.4.11 does not apply to pure
 *   decoration; ratios vs #FAF9F6 documented for honesty):
 *   · editorial #C9A227 2.30 — decorative ONLY, never text, never a control
 *   · atelier   #A5718B 3.74 · fit #4E7C6A 4.52 · commerce #1B1F3B 15.28
 *   · account   #555A73 6.44 · partner #3E5C76 6.65 · admin #5A5E6A 6.15
 *
 * RULES (spec 07 + spec 13 constraints, enforced by tests):
 *   · commerce surfaces (cart/checkout/orders) are LIGHT — the dark
 *     editorial language never reaches the money path;
 *   · /admin never resolves to the partner register and vice-versa — the
 *     two portals must stay visually distinguishable;
 *   · the register changes accents and wayfinding only — it never hides,
 *     disables or recolours status semantics (colour is never the only
 *     signal anywhere in the app).
 */

export type RegisterId =
  | "editorial"
  | "atelier"
  | "fit"
  | "commerce"
  | "account"
  | "partner"
  | "admin";

export interface Register {
  id: RegisterId;
  /** Decorative accent — hairline, dot, rule. Never body text. */
  accent: string;
  /** Text-grade ink, AA+ on both #FAF9F6 and #FFFFFF (measured above). */
  ink: string;
  /** i18n key for the section eyebrow label (en.json + ar.json). */
  labelKey: string;
  /** Light scheme is a hard guarantee for commerce (spec 07). */
  scheme: "light";
}

export const REGISTERS: Record<RegisterId, Register> = {
  editorial: {
    id: "editorial",
    accent: "#C9A227",
    ink: "#6B4F1E",
    labelKey: "registers.editorial.label",
    scheme: "light",
  },
  atelier: {
    id: "atelier",
    accent: "#A5718B",
    ink: "#6E4458",
    labelKey: "registers.atelier.label",
    scheme: "light",
  },
  fit: {
    id: "fit",
    accent: "#4E7C6A",
    ink: "#2F5547",
    labelKey: "registers.fit.label",
    scheme: "light",
  },
  commerce: {
    id: "commerce",
    accent: "#1B1F3B",
    ink: "#1B1F3B",
    labelKey: "registers.commerce.label",
    scheme: "light",
  },
  account: {
    id: "account",
    accent: "#555A73",
    ink: "#555A73",
    labelKey: "registers.account.label",
    scheme: "light",
  },
  partner: {
    id: "partner",
    accent: "#3E5C76",
    ink: "#35506A",
    labelKey: "registers.partner.label",
    scheme: "light",
  },
  admin: {
    id: "admin",
    accent: "#5A5E6A",
    ink: "#43464F",
    labelKey: "registers.admin.label",
    scheme: "light",
  },
};

/**
 * Route-family → register. First match wins; longest/most specific
 * prefixes first. Aliases (e.g. /products vs /discover, /partner vs /b2b)
 * resolve to the SAME register so one surface family never flickers
 * between identities.
 */
const ROUTE_TABLE: ReadonlyArray<readonly [prefix: string, id: RegisterId]> = [
  // Platform governance — never the partner register (spec 13).
  ["/admin", "admin"],
  // Partner operations (both aliases).
  ["/b2b", "partner"],
  ["/partner", "partner"],
  // Money path — always light, always navy (spec 07).
  ["/cart", "commerce"],
  ["/checkout", "commerce"],
  ["/orders", "commerce"],
  ["/returns", "commerce"],
  ["/product", "commerce"], // /product/:slug detail
  ["/products", "commerce"], // /products/:slug detail (listing is special-cased)
  // Fit & try-on studio family.
  ["/try-on", "fit"],
  ["/tryon-studio", "fit"],
  ["/fit", "fit"], // covers /fit and /fit-finder
  ["/visual-search", "fit"],
  // Closet / styling family.
  ["/wardrobe", "atelier"],
  ["/builder", "atelier"],
  ["/outfits", "atelier"],
  ["/my-looks", "atelier"],
  ["/looks", "atelier"], // public shared look
  // Account & legal.
  ["/profile", "account"],
  ["/settings", "account"],
  ["/notifications", "account"],
  ["/privacy", "account"],
  ["/privacy-policy", "account"],
  ["/terms", "account"],
  ["/terms-of-service", "account"],
  ["/gdpr", "account"],
  // Editorial browsing (home, discover, stylist alias).
  ["/discover", "editorial"],
  ["/stylist", "editorial"],
];

/**
 * Resolve the register for a pathname. `/products` (the catalogue listing)
 * is editorial; `/products/:slug` (a single product) is commerce — the
 * listing sells the story, the detail page sells the item.
 */
export function resolveRegister(pathname: string): RegisterId {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (path === "/products" || path === "/products/") return "editorial";
  for (const [prefix, id] of ROUTE_TABLE) {
    if (path === prefix || path.startsWith(`${prefix}/`)) return id;
    // /fit-finder style: alias sharing the prefix with a dash.
    if (prefix === "/fit" && path.startsWith("/fit-")) return id;
  }
  return "editorial";
}

/** Inline custom properties for a surface root (consumed by index.css). */
export function registerStyle(id: RegisterId): Record<string, string> {
  const r = REGISTERS[id];
  return {
    "--register-accent": r.accent,
    "--register-ink": r.ink,
  };
}
