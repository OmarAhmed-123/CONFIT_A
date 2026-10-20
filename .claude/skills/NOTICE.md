# Vendored agent skills — attribution and provenance

The skills in this directory are **not** written by CONFIT_A. They are vendored,
unmodified, from an MIT-licensed upstream project so that every agent and human working
in this repository shares one copy.

| | |
|---|---|
| **Upstream** | https://github.com/mattpocock/skills |
| **Author** | Matt Pocock |
| **Licence** | MIT — full text in [`LICENSE`](LICENSE) alongside this file |
| **Upstream commit vendored** | `5beb35b040e3de97e54fa9e386d7e42d15c295c2` (`5beb35b`, 2026-10-19) |
| **Vendored on** | 2026-10-20 |
| **Method** | `npx skills@latest add mattpocock/skills -a claude-code -y` |

Copyright (c) 2026 Matt Pocock. The MIT licence text is reproduced verbatim in
[`LICENSE`](LICENSE); no copyright header has been stripped or altered from any skill.

## What was vendored

24 skills: the 22 named in the integration scope, plus 2 pulled in as dependency closure
(see below). Each is a directory containing `SKILL.md` (YAML frontmatter
with `name` + `description`, then the instructions) plus any support files the skill
needs (`*.md` references, `scripts/`, `agents/`).

**Named in scope (22):** `code-review` · `codebase-design` · `diagnosing-bugs` ·
`domain-modeling` · `grill-me` · `handoff` · `implement` · `implement-spec` ·
`improve-codebase-architecture` · `pr` · `prototype` · `research` · `retro` ·
`setup-matt-pocock-skills` · `tdd` · `teach` · `to-spec` · `to-tickets` · `wait-what` ·
`wayfinder` · `wizard` · `writing-for-agents`

**Dependency closure (2):** `grilling` · `triage`

- `grilling` is a **hard** dependency. `grill-me/SKILL.md` is a 157-byte shim whose entire
  body is "Call the Skill tool with \"grilling\"" — vendoring `grill-me` without
  `grilling` ships a broken skill. `wayfinder` and `improve-codebase-architecture` also
  call it. Found by grepping every kept skill for references to the ones being dropped.
- `triage` is a **soft** dependency: `setup-matt-pocock-skills`, `to-spec`, `to-tickets`
  and `wayfinder` refer to it, and the triage-label vocabulary in `AGENTS.md` §7.5 is
  meaningless without it. Vendored so that vocabulary actually has a consumer.

## What was deliberately NOT vendored

1. **Upstream machinery.** The installer also writes a root `skills-lock.json` (a
   lockfile) and can drop `package.json`/lockfile, `.changeset`, `.github/` and CI
   configuration. None of that is here: CONFIT_A already has its own dependency, release
   and CI configuration and this repository does not need a second one. The upstream
   commit above is the pin, recorded here instead of in a lockfile.

2. **14 skills outside this slice's scope.** The installer offers 38; this repository took
   24. The 14 not taken are:
   `ask-matt`, `chief-of-staff`, `claude-handoff`, `git-guardrails-claude-code`,
   `grill-with-docs`, `loop-me`, `migrate-to-shoehorn`, `scaffold-exercises`,
   `setup-pre-commit`, `setup-ts-deep-modules`, `to-questionnaire`,
   `writing-beats`, `writing-fragments`, `writing-shape`.

   `grill-with-docs` is named once, in `setup-matt-pocock-skills/domain.md`, as a route to
   `/domain-modeling` — a passing mention, not a dependency: the same sentence also routes
   through `improve-codebase-architecture`, which **is** installed.

   Several are specific to other stacks or to producing course material
   (`migrate-to-shoehorn`, `scaffold-exercises`) and have no CONFIT_A use. They can be
   added later by re-running the installer — the set is a choice, not a limitation.

## Updating

```bash
npx skills@latest add mattpocock/skills -a claude-code -y   # requires Node >= 22.20
```

Re-prune to the list above, delete the generated `skills-lock.json`, update the commit SHA
in this file, and note the change in the PR. Review the diff: skills run with the agent's
own permissions, so a silently changed instruction file is a real change in agent
behaviour.

## Precedence

These skills **assist**; they do not govern. The project's own process wins wherever they
overlap — see the "Agent skills" section of [`/AGENTS.md`](../../AGENTS.md). In
particular the speckit flow in `.cursor/commands/speckit.*` and
`.specify/memory/constitution.md` are the authoritative spec/plan/tasks process for
CONFIT_A workstreams.
