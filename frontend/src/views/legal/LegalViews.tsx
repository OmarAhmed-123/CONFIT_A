import React from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ShieldIcon } from '../../components/icons/ConfitIcons';

/**
 * LEGAL-01 — real Privacy Policy / Terms of Service / GDPR pages.
 *
 * Audit 2026-09-05: "Privacy Policy, Terms of Service and GDPR links all go
 * to /profile, which shows Authentication Required instead of legal text —
 * a placeholder route instead of legal pages."
 *
 * Every statement here describes behaviour that actually exists in the
 * product (export: GET /api/v1/auth/gdpr-export; erasure: DELETE
 * /api/v1/auth/account; try-on photo retention: 24h anonymous expiry;
 * payments: simulated demo adapter until a PSP is connected). Do not edit
 * these claims ahead of the code — LEGAL text that overstates the system is
 * the same defect class the audit flagged.
 */

export const LEGAL_LAST_UPDATED = '6 September 2026';
export const LEGAL_VERSION = '3.0';
export const LEGAL_CONTACT = 'privacy@confit.io';

const Shell: React.FC<{ title: string; subtitle: string; active: 'privacy' | 'terms' | 'gdpr'; children: React.ReactNode }> = ({
  title,
  subtitle,
  active,
  children,
}) => {
  const { t } = useTranslation();
  const tabs = [
    { key: 'privacy', to: '/privacy', label: 'Privacy Policy' },
    { key: 'terms', to: '/terms', label: 'Terms of Service' },
    { key: 'gdpr', to: '/gdpr', label: 'GDPR & Your Rights' },
  ] as const;
  return (
    <div className="space-y-8 pb-20">
      <div className="bg-gradient-to-r from-[#0C0E1E] to-[#1B1F3B] rounded-3xl text-white p-8 sm:p-10 shadow-xl border border-slate-800">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#C5A059]/20 border border-[#C5A059]/40 text-[#E2BF70] text-xs font-semibold uppercase tracking-wider mb-3">
          <ShieldIcon size={14} color="#E2BF70" />
          <span>Legal · Version {LEGAL_VERSION}</span>
        </div>
        <h1 className="font-serif text-3xl sm:text-4xl font-bold">{title}</h1>
        <p className="text-xs sm:text-sm text-slate-300 font-light mt-2 max-w-2xl leading-relaxed">{subtitle}</p>
        <p className="text-[11px] text-slate-400 mt-3">Last updated: {LEGAL_LAST_UPDATED} · Applies to confit-a.vercel.app and its API</p>
      </div>

      <nav aria-label="Legal documents" className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <Link
            key={tab.key}
            to={tab.to}
            aria-current={active === tab.key ? 'page' : undefined}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              active === tab.key
                ? 'bg-[#1B1F3B] text-white shadow-2xs'
                : 'bg-white border border-slate-200 text-slate-600 hover:border-[#C5A059]'
            }`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      <article className="bg-white rounded-3xl border border-slate-200/80 p-6 sm:p-10 shadow-2xs space-y-6 max-w-4xl [&_h2]:font-serif [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-[#1B1F3B] [&_h2]:pt-2 [&_p]:text-sm [&_p]:text-slate-600 [&_p]:leading-relaxed [&_li]:text-sm [&_li]:text-slate-600 [&_li]:leading-relaxed [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:space-y-1.5 [&_table]:w-full [&_table]:text-xs [&_th]:text-left [&_th]:py-2 [&_th]:text-slate-400 [&_th]:uppercase [&_th]:text-[10px] [&_th]:tracking-wider [&_td]:py-2 [&_td]:border-t [&_td]:border-slate-100 [&_td]:text-slate-600">
        {children}
        <div className="pt-4 border-t border-slate-100 text-xs text-slate-500">
          Questions or requests: <span className="font-semibold text-slate-700">{LEGAL_CONTACT}</span>. In-app:
          Profile → Privacy → export or erase your data without emailing us.
        </div>
      </article>
    </div>
  );
};

const H: React.FC<{ children: React.ReactNode }> = ({ children }) => <h2>{children}</h2>;

/* ============================== PRIVACY ============================== */
export const PrivacyPolicyView: React.FC = () => (
  <Shell
    title="Privacy Policy"
    subtitle="What CONFIT collects, why, how long it is kept, and who it is shared with. Written to describe the system as it actually behaves today."
    active="privacy"
  >
    <H>1. Data we process</H>
    <ul>
      <li><strong>Account data:</strong> email, name, optional phone, password (bcrypt-hashed — never readable by us), role, language preference.</li>
      <li><strong>Style profile:</strong> the style/onboarding answers you give to personalize recommendations.</li>
      <li><strong>Measurements:</strong> body measurements you enter in the Fit Finder or derive from the camera scan. They are processed to compute size recommendations. They are only persisted when you explicitly press “Save these measurements to my profile”.</li>
      <li><strong>Try-on photos:</strong> photos you upload to Virtual Try-On, processed to render the garment on your image. Anonymous try-on jobs are auto-expired after 24 hours. You can trigger deletion at any time from the studio.</li>
      <li><strong>Wardrobe items:</strong> garment photos and attributes you upload to your Smart Wardrobe.</li>
      <li><strong>Commerce data:</strong> cart, orders, returns, promotions. Orders placed in Demo Payment Mode contain a `payment_mode: demo` marker and no real card data ever reaches CONFIT.</li>
      <li><strong>Technical logs:</strong> request logs including IP and user-agent for security and rate limiting.</li>
    </ul>

    <H>2. What we do NOT do</H>
    <ul>
      <li>We do not sell personal data.</li>
      <li>We do not use your try-on photos to train models without a separate explicit opt-in.</li>
      <li>We do not store readable passwords or full card numbers (in demo mode no card data is collected at all).</li>
    </ul>

    <H>3. Cookies & sessions</H>
    <p>
      Authentication uses an <code>httpOnly</code> session cookie (<code>confit_token</code>) plus a readable CSRF
      token (<code>confit_csrf</code>) for double-submit protection. Guests get a random session token
      (localStorage) so carts and measurement sessions work without an account. Preference storage: language and
      cart contents locally in your browser.
    </p>

    <H>4. Retention</H>
    <table>
      <thead><tr><th>Data</th><th>Retention</th></tr></thead>
      <tbody>
        <tr><td>Anonymous try-on jobs & photos</td><td>24 hours (automatic expiry)</td></tr>
        <tr><td>Saved measurements</td><td>Until you delete them or erase your account</td></tr>
        <tr><td>Wardrobe items</td><td>Until you delete them or erase your account</td></tr>
        <tr><td>Orders & invoices</td><td>Commerce/tax retention requirements</td></tr>
        <tr><td>Security logs</td><td>Short-lived operational window</td></tr>
      </tbody>
    </table>

    <H>5. Processors & sub-processors</H>
    <ul>
      <li><strong>Hosting:</strong> Vercel (application + serverless API) and Neon (PostgreSQL database, EU region endpoint).</li>
      <li><strong>AI providers:</strong> styling and vision features may call configured AI APIs (e.g. Groq/Gemini/OpenAI) with the minimum payload needed for the feature. When a provider is not configured the feature degrades honestly instead of shipping your data elsewhere.</li>
      <li><strong>Payments:</strong> currently a simulated adapter (Demo Payment Mode). No payment data leaves CONFIT until a PSP (Stripe/Tabby/Tamara) is connected and this policy is updated.</li>
    </ul>

    <H>6. Your controls</H>
    <ul>
      <li>Export everything: Profile → Privacy → <em>Export my data</em> (machine-readable JSON via <code>/auth/gdpr-export</code>).</li>
      <li>Erase everything: Profile → Privacy → <em>Delete account</em> (<code>DELETE /auth/account</code>) — irrevocable removal of profile, measurements, wardrobe and photos.</li>
      <li>Delete individual try-on jobs and wardrobe items at any time from their screens.</li>
    </ul>
  </Shell>
);

/* ============================== TERMS ============================== */
export const TermsOfServiceView: React.FC = () => (
  <Shell
    title="Terms of Service"
    subtitle="The agreement between you and CONFIT when you use the storefront, the styling tools, or the brand portal."
    active="terms"
  >
    <H>1. Acceptance</H>
    <p>By using CONFIT you agree to these terms. If you do not agree, do not use the service.</p>

    <H>2. The service today — honest capability statement</H>
    <ul>
      <li>Catalog, search, outfit building, fit recommendations, wardrobe and demo checkout are live features.</li>
      <li><strong>Payments are in Demo Payment Mode:</strong> checkout uses a simulated payment adapter; orders are labelled <code>payment_mode: demo</code> and <strong>no real charge is made and no goods are shipped</strong>. Live payment requires an explicit “payments live” deployment with a connected PSP.</li>
      <li>Virtual Try-On renders only when a GPU inference worker is configured; when it is not, the feature shows an explicit unavailability state instead of a fabricated result.</li>
      <li>AI styling answers are generated; they can be wrong. Fit recommendations are decision support, not a guarantee of physical fit.</li>
    </ul>

    <H>3. Accounts</H>
    <ul>
      <li>You are responsible for your credentials and activity under your account.</li>
      <li>One person per account; consumer accounts cannot self-elevate to brand or admin roles — roles are granted server-side.</li>
      <li>We may suspend accounts that abuse the platform (scraping, fraud attempts, rate-limit evasion, uploading unlawful imagery).</li>
    </ul>

    <H>4. Acceptable use of photos</H>
    <p>
      Only upload photos of yourself or photos you have the right to use. No minors’ photos in try-on, no
      impersonation, no unlawful content. Uploaded photos are processed only to render your try-on or tag your
      wardrobe.
    </p>

    <H>5. Purchases, orders & returns (when payments are live)</H>
    <ul>
      <li>Prices, tax and shipping are computed server-side at checkout.</li>
      <li>Stock is reserved during checkout; order confirmation is authoritative from the server, not from the UI.</li>
      <li>The return window is 30 days unless a brand’s policy states otherwise on the product page.</li>
      <li>In Demo Payment Mode, “placed” orders are test artifacts and carry no payment obligation.</li>
    </ul>

    <H>6. Brand partners</H>
    <p>
      Brand portal accounts may manage only their own brand’s catalog, inventory and analytics (tenant isolation is
      enforced server-side). Import tooling must not be used to upload unlawful or infringing content; sample/demo
      imports are clearly labelled and never presented as live inventory.
    </p>

    <H>7. Disclaimers & liability</H>
    <p>
      The service is provided “as is”. To the maximum extent permitted by law, CONFIT is not liable for indirect or
      consequential damages. Nothing in these terms limits liability that cannot be limited by law.
    </p>

    <H>8. Changes</H>
    <p>We may update these terms; material changes will be announced in-app with the new “Last updated” date above.</p>
  </Shell>
);

/* ============================== GDPR ============================== */
export const GdprView: React.FC = () => (
  <Shell
    title="GDPR & Your Rights"
    subtitle="How CONFIT implements GDPR rights for EU/EEA users — with the in-product controls that exercise each right."
    active="gdpr"
  >
    <H>1. Who is the controller?</H>
    <p>CONFIT (operated by the project owner) is the controller for personal data described in the Privacy Policy. Contact: {LEGAL_CONTACT}.</p>

    <H>2. Lawful bases</H>
    <table>
      <thead><tr><th>Processing</th><th>Basis</th></tr></thead>
      <tbody>
        <tr><td>Account & session operation</td><td>Contract performance</td></tr>
        <tr><td>Try-on photo processing</td><td>Consent (explicit, per upload; retention consent optional)</td></tr>
        <tr><td>Saved measurements</td><td>Consent (explicit “Save” action)</td></tr>
        <tr><td>Security logs & rate limiting</td><td>Legitimate interests</td></tr>
        <tr><td>Order/invoice records</td><td>Legal obligation (once payments are live)</td></tr>
      </tbody>
    </table>

    <H>3. Your rights and where to exercise them in the product</H>
    <ul>
      <li><strong>Access & portability:</strong> Profile → Privacy → <em>Export my data</em> — structured JSON download (<code>GET /api/v1/auth/gdpr-export</code>), authenticated, rate-limited.</li>
      <li><strong>Erasure:</strong> Profile → Privacy → <em>Delete account</em> (<code>DELETE /api/v1/auth/account</code>) — erases profile, measurements, wardrobe, photos and revokes sessions. Irrevocable.</li>
      <li><strong>Rectification:</strong> edit your name, phone, language and style profile directly in Profile.</li>
      <li><strong>Objection/withdrawal of consent:</strong> delete individual try-on jobs or wardrobe items; declining “Save measurements” keeps processing ephemeral.</li>
      <li><strong>Complaint:</strong> you may lodge a complaint with your local supervisory authority.</li>
    </ul>

    <H>4. Special category data (biometrics)</H>
    <p>
      Body measurements and try-on photos can be sensitive. CONFIT processes them only on explicit action: photos
      are used to render your try-on and anonymous jobs expire automatically after 24 hours; measurements persist
      only after an explicit save. Account deletion removes the encrypted biometric store. We do not perform
      face recognition and do not uniquely identify individuals from photos.
    </p>

    <H>5. Data transfers</H>
    <p>
      Primary hosting and the database endpoint are in the EU (Vercel + Neon EU-central). AI provider calls, when
      configured, may process payloads outside the EEA under the provider’s transfer safeguards; when a provider is
      not configured the feature degrades rather than transferring data.
    </p>

    <H>6. Breach notification</H>
    <p>
      Confirmed personal-data breaches affecting your rights are reported to the competent supervisory authority
      within 72 hours and to affected users without undue delay.
    </p>
  </Shell>
);
