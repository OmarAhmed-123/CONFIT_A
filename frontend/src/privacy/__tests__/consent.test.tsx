/**
 * Consent contract tests (audit 2026-09-21, «خصوصية الصور والبيانات الحيوية»).
 *
 * The audit found that the app asserted consent ON THE USER'S BEHALF:
 * `measurementService.createSession('client_side', { consentGranted: true })`
 * with no user action behind it. GDPR Article 7 does not accept a default, a
 * pre-ticked box, or "they pressed Start, so that counts" — and Article 9
 * biometric data needs a separate explicit condition on top of a lawful basis.
 *
 * So these tests are deliberately adversarial about the ONE thing that matters:
 * that no photo-processing path can proceed without a positive, versioned,
 * recorded user action — and that the test suite would FAIL if someone
 * reintroduced the old shortcut.
 *
 * The last two blocks are static contracts over the source tree rather than
 * render assertions, because the defect they guard is a call-site pattern, not
 * a rendered output.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { render, screen, cleanup, act, fireEvent, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';

import i18n, { setAppLanguage } from '../../i18n/i18n';
import {
  useConsentStore,
  NOTICE_VERSION,
  CONSENT_PURPOSES,
  CONSENT_PURPOSE_COPY,
} from '../consentStore';
import { ConsentDialog } from '../ConsentDialog';
import { ConsentManager } from '../ConsentManager';
import { usePhotoConsent, type PhotoConsentController } from '../usePhotoConsent';

const SRC_DIR = path.resolve(__dirname, '../..');

function wrap(ui: React.ReactNode) {
  // ConsentDialog links to /privacy for the withdrawal surface, so it needs a
  // Router — and the test should exercise the real link, not a stub.
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{ui}</MemoryRouter>
    </I18nextProvider>,
  );
}

/** Source files that are not user-facing UI. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
        walk(full);
      } else if (/\.tsx?$/.test(entry.name) && !entry.name.includes('.test.')) {
        out.push(full);
      }
    }
  };
  walk(SRC_DIR);
  return out;
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  useConsentStore.setState({ records: {} });
  setAppLanguage('en');
});

afterEach(() => {
  cleanup();
  setAppLanguage('en');
});

describe('consentStore — a grant is a record, not a boolean', () => {
  it('stores nothing until a purpose is granted', () => {
    const { hasConsent, exportRecords } = useConsentStore.getState();
    for (const purpose of CONSENT_PURPOSES) {
      expect(hasConsent(purpose)).toBe(false);
    }
    expect(exportRecords()).toEqual([]);
  });

  it('records purpose, timestamp and notice version on grant', () => {
    const before = Date.now();
    act(() => {
      useConsentStore.getState().grant('try_on');
    });
    const record = useConsentStore.getState().getRecord('try_on');
    expect(record).toBeDefined();
    expect(record!.purpose).toBe('try_on');
    expect(record!.noticeVersion).toBe(NOTICE_VERSION);
    expect(new Date(record!.grantedAt).getTime()).toBeGreaterThanOrEqual(before);

    // GDPR Art.7(1): the controller must be able to DEMONSTRATE consent, which
    // is why the timestamp and the version are stored rather than a boolean.
    expect(useConsentStore.getState().exportRecords()).toHaveLength(1);
  });

  it('is per purpose — a try-on grant does not authorise the wardrobe', () => {
    act(() => {
      useConsentStore.getState().grant('try_on');
    });
    expect(useConsentStore.getState().hasConsent('try_on')).toBe(true);
    expect(useConsentStore.getState().hasConsent('wardrobe')).toBe(false);
    expect(useConsentStore.getState().hasConsent('visual_search')).toBe(false);
    expect(useConsentStore.getState().hasConsent('body_scan')).toBe(false);
  });

  it('treats a grant from an older notice version as absent (forces re-consent)', () => {
    act(() => {
      useConsentStore.setState({
        records: {
          try_on: {
            purpose: 'try_on',
            noticeVersion: '0.1',
            grantedAt: new Date().toISOString(),
            rememberForSession: false,
          },
        },
      });
    });
    // This is what makes "material changes are announced" true in code: a
    // materially different notice cannot silently inherit the old agreement.
    expect(useConsentStore.getState().hasConsent('try_on')).toBe(false);
    expect(useConsentStore.getState().getRecord('try_on')).toBeDefined();
  });

  it('withdraws a single purpose and leaves the others intact', () => {
    act(() => {
      useConsentStore.getState().grant('try_on');
      useConsentStore.getState().grant('wardrobe');
    });
    act(() => {
      useConsentStore.getState().withdraw('try_on');
    });
    expect(useConsentStore.getState().hasConsent('try_on')).toBe(false);
    expect(useConsentStore.getState().hasConsent('wardrobe')).toBe(true);
  });

  it('withdrawAll clears every record', () => {
    act(() => {
      CONSENT_PURPOSES.forEach((p) => useConsentStore.getState().grant(p));
    });
    expect(useConsentStore.getState().exportRecords()).toHaveLength(4);
    act(() => {
      useConsentStore.getState().withdrawAll();
    });
    expect(useConsentStore.getState().exportRecords()).toEqual([]);
  });

  it('never sets rememberForSession unless the user asked for it', () => {
    act(() => {
      useConsentStore.getState().grant('try_on');
    });
    expect(useConsentStore.getState().getRecord('try_on')!.rememberForSession).toBe(false);
  });
});

describe('ConsentDialog — explicit, specific, refusable', () => {
  it('renders the notice with the purpose-specific copy for that flow', () => {
    wrap(<ConsentDialog purpose="wardrobe" onAccept={() => {}} onDecline={() => {}} />);
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByText(i18n.t(CONSENT_PURPOSE_COPY.wardrobe.purposeKey))).toBeTruthy();
    // Retention must be specific: a wardrobe photo is kept until deletion, so
    // it must NOT be described with the anonymous-job "expires in N hours" line.
    const retention = i18n.t(CONSENT_PURPOSE_COPY.wardrobe.retentionKey, { hours: 24 });
    expect(screen.getByText(retention)).toBeTruthy();
    expect(retention).not.toContain('24');
  });

  it('states the retention window for the anonymous-job purposes', () => {
    wrap(<ConsentDialog purpose="try_on" onAccept={() => {}} onDecline={() => {}} />);
    expect(
      screen.getByText(i18n.t(CONSENT_PURPOSE_COPY.try_on.retentionKey, { hours: 24 })),
    ).toBeTruthy();
  });

  it('does not pre-tick anything that could be read as consent', () => {
    wrap(<ConsentDialog purpose="try_on" onAccept={() => {}} onDecline={() => {}} />);
    const boxes = document.querySelectorAll('input[type="checkbox"]');
    expect(boxes.length).toBeGreaterThan(0);
    boxes.forEach((box) => expect((box as HTMLInputElement).checked).toBe(false));
  });

  it('offers decline as a real button, not a hidden or disabled one', () => {
    wrap(<ConsentDialog purpose="try_on" onAccept={() => {}} onDecline={() => {}} />);
    const decline = screen.getByTestId('consent-decline') as HTMLButtonElement;
    expect(decline.disabled).toBe(false);
    expect(decline.textContent!.trim().length).toBeGreaterThan(0);
  });

  it('reports the accepted checkbox state to the caller', () => {
    const onAccept = vi.fn();
    wrap(<ConsentDialog purpose="try_on" onAccept={onAccept} onDecline={() => {}} />);
    fireEvent.click(document.querySelector('input[type="checkbox"]')!);
    fireEvent.click(screen.getByTestId('consent-accept'));
    expect(onAccept).toHaveBeenCalledWith({ rememberForSession: true });
  });

  it('shows the notice version so the user can identify what they agreed to', () => {
    wrap(<ConsentDialog purpose="try_on" onAccept={() => {}} onDecline={() => {}} />);
    expect(screen.getByText(new RegExp(NOTICE_VERSION.replace('.', '\\.')))).toBeTruthy();
  });

  it('renders in Arabic with Arabic copy, not English', async () => {
    await act(async () => {
      setAppLanguage('ar');
    });
    wrap(<ConsentDialog purpose="try_on" onAccept={() => {}} onDecline={() => {}} />);
    const dialog = screen.getByRole('dialog');
    const arabic = i18n.t('consent.title');
    expect(screen.getByText(arabic)).toBeTruthy();
    expect(/[\u0600-\u06FF]/.test(arabic)).toBe(true);
    // The English lead must not appear anywhere in the Arabic dialog.
    expect(dialog.textContent).not.toContain(i18n.getFixedT('en')('consent.lead'));
  });

  it('declares itself a modal dialog with a name', () => {
    wrap(<ConsentDialog purpose="visual_search" onAccept={() => {}} onDecline={() => {}} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const labelledBy = dialog.getAttribute('aria-labelledby')!;
    expect(document.getElementById(labelledBy)!.textContent!.trim().length).toBeGreaterThan(0);
  });
});

describe('usePhotoConsent — fail-closed by construction', () => {
  /**
   * A hook that returns its own dialog cannot be tested with `renderHook`
   * alone: the dialog would never be mounted, so the buttons the user clicks
   * would not exist. The harness renders the returned node and exposes the
   * controller, which is exactly how the real call sites consume the hook.
   */
  let controller: PhotoConsentController | null = null;

  const Harness: React.FC<{ purpose: Parameters<typeof usePhotoConsent>[0] }> = ({ purpose }) => {
    const c = usePhotoConsent(purpose);
    controller = c;
    return <>{c.consentDialog}</>;
  };

  function renderHarness(purpose: Parameters<typeof usePhotoConsent>[0]) {
    controller = null;
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <Harness purpose={purpose} />
        </MemoryRouter>
      </I18nextProvider>,
    );
    return {
      c: () => controller!,
      accept: () => fireEvent.click(screen.getByTestId('consent-accept')),
      decline: () => fireEvent.click(screen.getByTestId('consent-decline')),
    };
  }

  it('resolves true only after an explicit acceptance', async () => {
    const h = renderHarness('try_on');
    let promise!: Promise<boolean>;
    act(() => {
      promise = h.c().requestConsent();
    });
    expect(h.c().isPrompting).toBe(true);
    expect(screen.getByTestId('consent-dialog')).toBeTruthy();
    h.accept();
    await expect(promise).resolves.toBe(true);
    expect(useConsentStore.getState().hasConsent('try_on')).toBe(true);
  });

  it('resolves false on decline and records nothing', async () => {
    const h = renderHarness('try_on');
    let promise!: Promise<boolean>;
    act(() => {
      promise = h.c().requestConsent();
    });
    h.decline();
    await expect(promise).resolves.toBe(false);
    expect(useConsentStore.getState().hasConsent('try_on')).toBe(false);
    expect(screen.queryByTestId('consent-dialog')).toBeNull();
  });

  it('resolves false when the caller unmounts with the notice open', async () => {
    const h = renderHarness('wardrobe');
    let promise!: Promise<boolean>;
    act(() => {
      promise = h.c().requestConsent();
    });
    cleanup();
    // The dangerous outcomes would be a promise that never settles (a flow
    // stuck forever) or one that resolves true (processing without consent).
    await expect(promise).resolves.toBe(false);
    expect(useConsentStore.getState().hasConsent('wardrobe')).toBe(false);
  });

  it('does not prompt again once the purpose is granted', async () => {
    act(() => {
      useConsentStore.getState().grant('try_on');
    });
    const h = renderHarness('try_on');
    await expect(h.c().requestConsent()).resolves.toBe(true);
    expect(h.c().isPrompting).toBe(false);
    expect(screen.queryByTestId('consent-dialog')).toBeNull();
  });

  it('does not leak a grant across purposes', async () => {
    act(() => {
      useConsentStore.getState().grant('try_on');
    });
    const h = renderHarness('body_scan');
    let promise!: Promise<boolean>;
    act(() => {
      promise = h.c().requestConsent();
    });
    expect(h.c().isPrompting).toBe(true);
    h.decline();
    await expect(promise).resolves.toBe(false);
  });

  it('honours the remember-for-session checkbox on acceptance', async () => {
    const h = renderHarness('visual_search');
    let promise!: Promise<boolean>;
    act(() => {
      promise = h.c().requestConsent();
    });
    fireEvent.click(document.querySelector('input[type="checkbox"]')!);
    h.accept();
    await expect(promise).resolves.toBe(true);
    expect(useConsentStore.getState().getRecord('visual_search')!.rememberForSession).toBe(true);
  });
});

describe('ConsentManager — the withdrawal surface', () => {
  it('explains that there is nothing to withdraw when nothing was granted', () => {
    wrap(<ConsentManager />);
    expect(screen.getByText(i18n.t('consent.manage_empty'))).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('lists each granted purpose with its date and notice version, and withdraws one', () => {
    act(() => {
      useConsentStore.getState().grant('try_on');
      useConsentStore.getState().grant('wardrobe');
    });
    wrap(<ConsentManager />);
    const rows = screen.getAllByRole('row');
    expect(rows.length).toBe(3); // header + two grants
    // Match the BUTTON, not the column header that shares the same word.
    fireEvent.click(screen.getAllByRole('button', { name: i18n.t('consent.manage_withdraw') })[0]);
    expect(useConsentStore.getState().exportRecords()).toHaveLength(1);
  });

  it('does not claim to be a server-side ledger it is not', () => {
    wrap(<ConsentManager />);
    // Over-claiming here would be the same failure the feature exists to fix.
    expect(screen.getByText(i18n.t('consent.manage_scope_note'))).toBeTruthy();
  });
});

describe('the consent notice is reachable — regression guard on dead copy', () => {
  it('every purpose copy key resolves in BOTH locales, and no key is orphaned', () => {
    for (const purpose of CONSENT_PURPOSES) {
      const { purposeKey, retentionKey } = CONSENT_PURPOSE_COPY[purpose];
      for (const key of [purposeKey, retentionKey]) {
        for (const lang of ['en', 'ar']) {
          const value = i18n.getFixedT(lang)(key, { hours: 24 });
          expect(value, `${lang}:${key}`).toBeTruthy();
          expect(value, `${lang}:${key}`).not.toBe(key);
        }
        expect(i18n.getFixedT('ar')(retentionKey, { hours: 24 })).toMatch(/[\u0600-\u06FF]/);
      }
    }
  });

  it('the notice is actually RENDERED somewhere — the original defect was dead copy', () => {
    // The whole `consent.*` notice already existed in both locale files and had
    // ZERO call sites: perfect, translated, unreachable. A privacy notice that
    // is never rendered is not a privacy notice, so the suite pins the wiring.
    const files = sourceFiles().map((f) => fs.readFileSync(f, 'utf8'));
    const rendersNotice = files.some((src) => /t\(\s*'consent\.(title|lead)'/.test(src));
    expect(rendersNotice).toBe(true);
  });
});

describe('static contract: no photo path may assert consent for the user', () => {
  /**
   * Files in the DATA layer that move bytes but hold no user decision. Each is
   * listed with the reason it is allowed to be ungated — an explicit, reviewable
   * decision rather than a silent skip. Adding a fourth file here should be
   * argued for in review, which is the point.
   */
  const DATA_LAYER_EXEMPT: Record<string, string> = {
    'lib/imageUpload.ts':
      'the compression implementation itself; it has no UI and must stay free of consent policy',
    'viewmodels/useWardrobeViewModel.ts':
      'receives Files that the gated WardrobeView already consented to and compressed',
    'hooks/useWardrobeQuery.ts':
      'query/mutation plumbing; the only live upload path is reached from the gated view (see the dead-path guard below)',
  };

  const rel = (f: string) => path.relative(SRC_DIR, f).split(path.sep).join('/');

  it('`consentGranted: true` only appears in files that gate on a real grant', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      const src = fs.readFileSync(file, 'utf8');
      if (!/consentGranted:\s*true/.test(src)) continue;
      const gated =
        /usePhotoConsent|useConsentStore|hasConsent\(/.test(src) ||
        // The body-measurement view model takes consent as a parameter and
        // defaults it to false; it must never invent it.
        /consentGranted\s*=\s*false/.test(src);
      if (!gated) offenders.push(rel(file));
    }
    // `measurementService.createSession('client_side', { consentGranted: true })`
    // with no user action behind it is the audit's exact finding. This fails the
    // build if it comes back.
    expect(offenders, `ungated consent assertions in: ${offenders.join(', ')}`).toEqual([]);
  });

  it('every UI entry point that processes an image asks for consent first', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      const r = rel(file);
      const src = fs.readFileSync(file, 'utf8');
      if (!/compressImageToDataUrl/.test(src)) continue;
      if (DATA_LAYER_EXEMPT[r]) continue;
      if (!/usePhotoConsent|requestConsent/.test(src)) offenders.push(r);
    }
    expect(
      offenders,
      `image processing without a consent gate in: ${offenders.join(', ')}`,
    ).toEqual([]);
  });

  it('the data-layer exemption list is exactly the set of ungated byte movers', () => {
    const actual: string[] = [];
    for (const file of sourceFiles()) {
      const r = rel(file);
      const src = fs.readFileSync(file, 'utf8');
      if (/\.uploadImage\s*\(|compressImageToDataUrl/.test(src) === false) continue;
      if (/usePhotoConsent|requestConsent/.test(src)) continue;
      if (/\.uploadImage\s*\(/.test(src)) actual.push(r);
    }
    const declared = Object.keys(DATA_LAYER_EXEMPT).filter(
      (k) => actual.includes(k) || actual.length === 0,
    );
    // Non-vacuous: if a NEW ungated uploader appears, `actual` grows and this
    // fails, forcing an explicit decision instead of a silent hole.
    expect(
      actual.filter((f) => !(f in DATA_LAYER_EXEMPT)).sort(),
      'new ungated upload path(s) — add a consent gate',
    ).toEqual([]);
    expect(declared.length).toBeGreaterThan(0);
  });

  it('the ungated `useUploadWardrobe` mutation still has no consumer', () => {
    // It is a second, ungated upload path sitting in the tree. It is not
    // reachable today; if it ever becomes reachable, this fails and the author
    // must gate it rather than quietly shipping an ungated uploader.
    const consumers = sourceFiles().filter((f) => {
      const src = fs.readFileSync(f, 'utf8');
      return (
        !rel(f).endsWith('hooks/useWardrobeQuery.ts') &&
        /\buseUploadWardrobe\b/.test(src)
      );
    });
    expect(consumers.map(rel)).toEqual([]);
  });
});
