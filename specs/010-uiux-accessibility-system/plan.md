# Implementation Plan: UI/UX, Accessibility, i18n/RTL & Motion System

**Branch**: `010-uiux-accessibility-system` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Deliver shared design-system primitives (accessible controls, `HonestProductImage` usage, i18n catalog completeness, reduced-motion wrapper, standard empty/loading/error components, live status) and apply them across the surfaces flagged by every audit (VTON upload, stylist drawer, checkout, admin/brand consoles). This is the cross-cutting dependency consumed by workstreams 004, 006, 007, 008, 009.

## Technical Context

**Language/Version**: TypeScript/React 18
**Primary Dependencies**: Vite, Tailwind, zustand, i18n (EN/AR + RTL), framer-motion (reduced-motion), axe for testing, `HonestProductImage`
**Storage**: N/A (frontend)
**Testing**: axe automated scans, RTL/i18n lint, keyboard/SR manual checklist, component tests for states/reduced-motion
**Target Platform**: Browser (Vercel-hosted SPA)
**Project Type**: Web application (frontend-focused)
**Constraints**: WCAG 2.2 AA; honest imagery; no hardcoded strings.

## Constitution Check

- **I. Evidence Before Appearance**: PASS — axe + manual results recorded separately; no "accessible" claim without the scan.
- **IV. Honest AI & Integrations**: PASS — honest imagery via `HonestProductImage`.
- **Accessibility constraint**: PASS/core.
- **II/III**: N/A (no server authority change). **V**: PASS.

No violations.

## Project Structure

```text
frontend/
├── src/
│   ├── components/ (HonestProductImage usage; accessible form controls; MotionReduced wrapper; Empty/Loading/Error)
│   ├── i18n/ (EN/AR catalogs completed; RTL)
│   └── views/ (apply primitives to VTON upload, stylist drawer, checkout, admin, brand)
└── tests/ (axe scans; i18n lint; reduced-motion; state components)
```

**Structure Decision**: Frontend-focused; provides primitives other workstreams import.

## Complexity Tracking

> No violations.
