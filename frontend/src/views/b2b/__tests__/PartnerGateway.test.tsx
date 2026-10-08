/**
 * B01 — public partner gateway (/b2b with no partner session).
 *
 * Every assertion here closes a defect that was MEASURED in the previous
 * implementation, which lived inside RoleGuard.tsx. The measured baseline:
 *
 *     <label>              0      aria-describedby  0
 *     autocomplete         0      aria-invalid      0
 *     name=                0      focus-visible     0
 *
 * plus: a duplicate lead painted in the SUCCESS colour, `PartnerLeadOut.id`
 * returned by the server and discarded, one catch block for network / 422 /
 * 429 / 503, no client parity with the server's 2-character and email rules,
 * an invisible 5-per-hour-per-IP ceiling, and a CTA that scrolled the
 * viewport without moving focus.
 *
 * Structure:
 *   A. Field primitive — the a11y contract the old form did not have
 *   B. StatusPanel — four tones, and only two of them interrupt
 *   C. LeadForm — validation parity, error taxonomy, reference, preservation
 *   D. PartnerGatewayView — five tiers, focus management, axe EN + AR
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";

import i18n, { setAppLanguage } from "../../../i18n/i18n";
import { Field } from "../../../components/common/Field";
import { StatusPanel } from "../../../components/common/StatusPanel";

// ---------------------------------------------------------------------------
// Mocks — the API layer and the UI store, rewritten per scenario.
// ---------------------------------------------------------------------------
const requestDemo = vi.fn();
vi.mock("../../../services/apiServices", () => ({
  brandService: { requestDemo: (...args: unknown[]) => requestDemo(...args) },
}));

// ApiError must be the REAL class: LeadForm branches on `instanceof`, so a
// stub would make every 429 fall through to the generic error branch and the
// throttled assertions would pass for the wrong reason.
vi.mock("../../../services/apiClient", async () => {
  class ApiError extends Error {
    code: string;
    status: number;
    details: Record<string, unknown>;
    constructor(message: string, code = "API_ERROR", status = 500, details = {}) {
      super(message);
      this.name = "ApiError";
      this.code = code;
      this.status = status;
      this.details = details;
    }
  }
  return { ApiError };
});

const openAuthModal = vi.fn();
vi.mock("../../../stores/uiStore", () => ({
  useUIStore: (selector?: (s: unknown) => unknown) =>
    selector ? selector({ openAuthModal }) : { openAuthModal },
}));

const renderWithI18n = (ui: React.ReactElement) =>
  render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);


/** Query by ACCESSIBLE NAME, not by raw label text. The required marker is
 *  aria-hidden, so it is excluded from the name a screen reader receives —
 *  but getByLabelText matches the label's textContent, asterisk included. */
const field = (name: string | RegExp): HTMLElement => {
  const found = [
    ...screen.queryAllByRole("textbox", { name }),
    ...screen.queryAllByRole("combobox", { name }),
  ];
  if (found.length !== 1) {
    throw new Error(`expected exactly one control named "${name}", found ${found.length}`);
  }
  return found[0];
};

beforeEach(async () => {
  vi.clearAllMocks();
  window.localStorage.clear();
  await i18n.changeLanguage("en");
});

afterEach(() => cleanup());

// ===========================================================================
// A. Field — the contract the old form was missing entirely
// ===========================================================================
describe("A. Field primitive", () => {
  it("renders a real visible <label> bound to the control, not a placeholder", () => {
    renderWithI18n(
      <Field name="company_name" label="Company name" value="" onChange={() => {}} />,
    );
    const input = field("Company name");
    expect(input.tagName).toBe("INPUT");
    // The label must be an element, not an aria-label string: a placeholder
    // vanishes on input and an aria-label is invisible to sighted users.
    expect(document.querySelector("label[for]")).not.toBeNull();
    expect(input.getAttribute("placeholder")).toBeNull();
  });

  it("carries a name and an autocomplete token so browser autofill works", () => {
    renderWithI18n(
      <Field
        name="work_email"
        label="Work email"
        type="email"
        autoComplete="email"
        value=""
        onChange={() => {}}
      />,
    );
    const input = field("Work email");
    expect(input).toHaveAttribute("name", "work_email");
    expect(input).toHaveAttribute("autocomplete", "email");
  });

  it("wires aria-invalid and aria-describedby only when there is an error", () => {
    const { rerender } = renderWithI18n(
      <Field name="contact_name" label="Contact name" value="" onChange={() => {}} />,
    );
    const input = field("Contact name");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).not.toHaveAttribute("aria-describedby");

    rerender(
      <I18nextProvider i18n={i18n}>
        <Field
          name="contact_name"
          label="Contact name"
          value=""
          onChange={() => {}}
          error="Enter at least 2 characters."
          hint="Shown when valid"
        />
      </I18nextProvider>,
    );
    const invalid = field("Contact name");
    expect(invalid).toHaveAttribute("aria-invalid", "true");
    // The described id must resolve to the ERROR, not the hint: announcing
    // "shown when valid" next to an invalid value contradicts itself.
    const describedBy = invalid.getAttribute("aria-describedby")!;
    expect(document.getElementById(describedBy)?.textContent).toBe(
      "Enter at least 2 characters.",
    );
    expect(screen.queryByText("Shown when valid")).not.toBeInTheDocument();
  });

  it("marks a required field in text and an optional one with an explicit marker", () => {
    renderWithI18n(
      <>
        <Field name="a" label="Required one" value="" onChange={() => {}} required />
        <Field name="b" label="Optional one" value="" onChange={() => {}} optional />
      </>,
    );
    expect(screen.getByText(i18n.t("field.optional_marker"))).toBeInTheDocument();
    expect(field(/Required one/)).toBeRequired();
  });

  it("reserves at least a 48px control height", () => {
    renderWithI18n(
      <Field name="company_name" label="Company name" value="" onChange={() => {}} />,
    );
    // jsdom computes no layout, so assert the class that carries the floor
    // rather than a pixel number it cannot measure.
    expect(field("Company name").className).toContain("min-h-[48px]");
  });
});

// ===========================================================================
// B. StatusPanel — four tones; only error and throttled interrupt
// ===========================================================================
describe("B. StatusPanel", () => {
  it("uses role=alert for error and throttled, role=status for success and notice", () => {
    const cases = [
      ["error", "alert"],
      ["throttled", "alert"],
      ["success", "status"],
      ["notice", "status"],
    ] as const;
    for (const [tone, role] of cases) {
      const { unmount } = renderWithI18n(
        <StatusPanel tone={tone} message={`m-${tone}`} data-testid="p" />,
      );
      expect(screen.getByTestId("p")).toHaveAttribute("role", role);
      unmount();
    }
  });

  it("renders the lead reference the previous implementation discarded", () => {
    renderWithI18n(
      <StatusPanel tone="success" message="Request received." reference="CONFIT-1234" />,
    );
    expect(screen.getByText("CONFIT-1234")).toBeInTheDocument();
  });

  it("offers an escape action on the throttled tone, since retrying cannot help", () => {
    renderWithI18n(
      <StatusPanel
        tone="throttled"
        message="Limit reached."
        action={{ label: "Email partnerships instead", href: "mailto:partnerships@confit.app" }}
      />,
    );
    const link = screen.getByText("Email partnerships instead");
    expect(link).toHaveAttribute("href", "mailto:partnerships@confit.app");
  });
});

// ===========================================================================
// C. LeadForm — validation parity, error taxonomy, reference, preservation
// ===========================================================================
import { LeadForm } from "../LeadForm";
import { ApiError } from "../../../services/apiClient";

const fill = async () => {
  fireEvent.change(field(i18n.t("partner.field_company")), {
    target: { value: "Integrity Brand" },
  });
  fireEvent.change(field(i18n.t("partner.field_contact")), {
    target: { value: "Amina Partner" },
  });
  fireEvent.change(field(i18n.t("partner.field_email")), {
    target: { value: "amina@example.com" },
  });
};

describe("C. LeadForm", () => {
  it("rejects a one-character company name locally and makes ZERO network requests", async () => {
    renderWithI18n(<LeadForm />);
    fireEvent.change(field(i18n.t("partner.field_company")), {
      target: { value: "x" },
    });
    fireEvent.change(field(i18n.t("partner.field_contact")), {
      target: { value: "Amina" },
    });
    fireEvent.change(field(i18n.t("partner.field_email")), {
      target: { value: "amina@example.com" },
    });

    fireEvent.click(screen.getByTestId("lead-submit"));

    // The server enforces len(...) >= 2; discovering that over a round trip
    // is the defect. No request may leave the device.
    await waitFor(() =>
      expect(field(i18n.t("partner.field_company"))).toHaveAttribute(
        "aria-invalid",
        "true",
      ),
    );
    expect(requestDemo).not.toHaveBeenCalled();
  });

  it("rejects a malformed email locally without a round trip", async () => {
    renderWithI18n(<LeadForm />);
    await fill();
    fireEvent.change(field(i18n.t("partner.field_email")), {
      target: { value: "not-an-email" },
    });
    fireEvent.click(screen.getByTestId("lead-submit"));

    await waitFor(() =>
      expect(field(i18n.t("partner.field_email"))).toHaveAttribute(
        "aria-invalid",
        "true",
      ),
    );
    expect(requestDemo).not.toHaveBeenCalled();
  });

  it("renders the server reference on success", async () => {
    requestDemo.mockResolvedValue({
      id: 4242,
      status: "received",
      notification_status: "sent",
      duplicate: false,
      message: "Request received.",
    });
    renderWithI18n(<LeadForm />);
    await fill();
    fireEvent.click(screen.getByTestId("lead-submit"));

    const panel = await screen.findByTestId("lead-result");
    expect(panel).toHaveAttribute("data-tone", "success");
    expect(within(panel).getByText("CONFIT-4242")).toBeInTheDocument();
  });

  it("renders a duplicate as notice, never as success", async () => {
    requestDemo.mockResolvedValue({
      id: 99,
      status: "duplicate",
      notification_status: "skipped",
      duplicate: true,
      message: "duplicate",
    });
    renderWithI18n(<LeadForm />);
    await fill();
    fireEvent.click(screen.getByTestId("lead-submit"));

    const panel = await screen.findByTestId("lead-result");
    expect(panel).toHaveAttribute("data-tone", "notice");
    expect(panel).not.toHaveAttribute("data-tone", "success");
    expect(within(panel).getByText(i18n.t("partner.duplicate_title"))).toBeInTheDocument();
  });

  it("routes a 429 to the throttled tone with a mailto escape, not a retry", async () => {
    requestDemo.mockRejectedValue(
      new ApiError("Too many partner-demo requests", "RATE_LIMITED", 429, {
        retry_after_seconds: 1200,
        scope: "partner_lead_ip",
      }),
    );
    renderWithI18n(<LeadForm />);
    await fill();
    fireEvent.click(screen.getByTestId("lead-submit"));

    const panel = await screen.findByTestId("lead-result");
    expect(panel).toHaveAttribute("data-tone", "throttled");
    expect(panel).toHaveAttribute("role", "alert");
    expect(
      within(panel).getByRole("link").getAttribute("href"),
    ).toBe("mailto:partnerships@confit.app");
  });

  it("does not confuse a 422 field rejection with a 429 ceiling", async () => {
    requestDemo.mockRejectedValue(
      new ApiError("A valid work email is required.", "VALIDATION_ERROR", 422, {}),
    );
    renderWithI18n(<LeadForm />);
    await fill();
    fireEvent.click(screen.getByTestId("lead-submit"));

    const panel = await screen.findByTestId("lead-result");
    expect(panel).toHaveAttribute("data-tone", "error");
    // A validation error must not offer the mailto escape — the fix is the
    // field, not a different channel.
    expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
  });

  it("preserves what the user typed when the request fails", async () => {
    requestDemo.mockRejectedValue(new ApiError("boom", "API_ERROR", 503, {}));
    renderWithI18n(<LeadForm />);
    await fill();
    fireEvent.click(screen.getByTestId("lead-submit"));

    await screen.findByTestId("lead-result");
    expect(field(i18n.t("partner.field_company"))).toHaveValue(
      "Integrity Brand",
    );
    expect(field(i18n.t("partner.field_email"))).toHaveValue(
      "amina@example.com",
    );
  });

  it("warns before the ceiling fires rather than after", async () => {
    window.localStorage.setItem("confit_partner_lead_sent", "4");
    renderWithI18n(<LeadForm />);
    // The ceiling is 5 per hashed IP per hour, shared by everyone behind one
    // NAT. Telling the prospect only once it fires leaves a dead end.
    expect(screen.getByTestId("lead-throttle-warning")).toBeInTheDocument();
  });

  it("submits source_path=/b2b so the lead records where it came from", async () => {
    requestDemo.mockResolvedValue({
      id: 1,
      status: "received",
      notification_status: "sent",
      duplicate: false,
      message: "ok",
    });
    renderWithI18n(<LeadForm />);
    await fill();
    fireEvent.click(screen.getByTestId("lead-submit"));
    await screen.findByTestId("lead-result");

    expect(requestDemo).toHaveBeenCalledWith(
      expect.objectContaining({ source_path: "/b2b" }),
    );
  });
});

// ===========================================================================
// D. PartnerGatewayView — five tiers, focus management, axe
// ===========================================================================
import { PartnerGatewayView } from "../PartnerGatewayView";

/** jsdom computes no layout, so color-contrast and target-size cannot be
 *  evaluated here and are disabled rather than allowed to "pass" vacuously.
 *  Mirrors the helper in navigationShell.test.tsx so both suites judge axe the
 *  same way: fail on critical/serious, not on anything the DOM cannot show. */
const JSDOM_UNCOMPUTABLE = ["color-contrast", "target-size"];
async function expectNoSeriousViolations(node: HTMLElement, label: string) {
  const results = await axe(node, {
    rules: Object.fromEntries(JSDOM_UNCOMPUTABLE.map((r) => [r, { enabled: false }])),
  });
  const bad = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  if (bad.length) {
    throw new Error(`${label}: ${bad.map((v) => `${v.id} — ${v.help}`).join("; ")}`);
  }
}


describe("D. PartnerGatewayView", () => {
  it("renders the lead form in the first section, above the fold", () => {
    renderWithI18n(
      <MemoryRouter>
        <PartnerGatewayView />
      </MemoryRouter>,
    );
    const form = screen.getByTestId("lead-form");
    // Tier 1 owns the masthead AND the form. The previous page put the form
    // third in the DOM, behind the hero and a 2x2 grid.
    const sections = Array.from(
      document.querySelectorAll("main > section"),
    ) as HTMLElement[];
    expect(sections.length).toBeGreaterThanOrEqual(5);
    expect(sections[0].contains(form)).toBe(true);
  });

  it("has five sections and no two share the same container pattern", () => {
    renderWithI18n(
      <MemoryRouter>
        <PartnerGatewayView />
      </MemoryRouter>,
    );
    // The old page was nine identical containers, seven from two .map() calls.
    // Tier 2 is a ledger (<ul>), tier 4 is an accordion (buttons with
    // aria-expanded), tier 5 has no container at all.
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getAllByRole("button", { expanded: true })).toHaveLength(1);
    expect(screen.getAllByRole("button", { expanded: false })).toHaveLength(2);
  });

  it("moves focus to the form when the CTA is activated", async () => {
    // scrollIntoView and Element.focus are no-ops in jsdom; spy on focus to
    // prove the viewport move is accompanied by a focus move. Scrolling alone
    // strands keyboard and screen-reader users on the masthead.
    const focusSpy = vi
      .spyOn(HTMLElement.prototype, "focus")
      .mockImplementation(function (this: HTMLElement) {
        this.dataset.focused = "true";
      });
    Element.prototype.scrollIntoView = vi.fn();

    renderWithI18n(
      <MemoryRouter>
        <PartnerGatewayView />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getAllByText(i18n.t("partner.request_partnership"))[0]);

    await waitFor(() => expect(focusSpy).toHaveBeenCalled());
    const focused = document.querySelector<HTMLElement>("[data-focused='true']");
    expect(focused).not.toBeNull();
    expect(focused!.closest("form")).toBe(screen.getByTestId("lead-form"));
    focusSpy.mockRestore();
  });

  it("opens one pillar at a time and exposes the accordion semantics", async () => {
    renderWithI18n(
      <MemoryRouter>
        <PartnerGatewayView />
      </MemoryRouter>,
    );
    const second = screen.getByTestId("pillar-trigger-1");
    expect(second).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(second);

    await waitFor(() => expect(second).toHaveAttribute("aria-expanded", "true"));
    // One open at a time: opening the second closes the first.
    expect(screen.getByTestId("pillar-trigger-0")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(second).toHaveAttribute("aria-controls", "pillar-panel-1");
  });

  it("resolves the partner design register rather than hard-coding colours", () => {
    renderWithI18n(
      <MemoryRouter>
        <PartnerGatewayView />
      </MemoryRouter>,
    );
    const main = screen.getByTestId("partner-gateway");
    // registers.ts: partner accent #3E5C76, ink #35506A. The old page used
    // #C5A059 — a value that is not in the confit.gold scale at all — and
    // never read the register.
    expect(main.style.getPropertyValue("--register-accent")).toBe("#3E5C76");
    expect(main.style.getPropertyValue("--register-ink")).toBe("#35506A");
  });

  it("has no critical or serious axe violations in English / LTR", async () => {
    const { container } = renderWithI18n(
      <MemoryRouter>
        <PartnerGatewayView />
      </MemoryRouter>,
    );
    await expectNoSeriousViolations(container, "B01 EN/LTR");
  });

  it("has no critical or serious axe violations in Arabic / RTL", async () => {
    await setAppLanguage("ar");
    document.documentElement.dir = "rtl";
    document.documentElement.lang = "ar";
    const { container } = renderWithI18n(
      <MemoryRouter>
        <PartnerGatewayView />
      </MemoryRouter>,
    );
    await expectNoSeriousViolations(container, "B01 AR/RTL");
    await setAppLanguage("en");
    document.documentElement.dir = "ltr";
    document.documentElement.lang = "en";
  });
});
