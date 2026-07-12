# Loomi Landing Page and Installer Design

## Goal

Give first-time visitors a credible explanation of Loomi and one inspectable command that starts the complete local demo. Preserve the existing Narrative Canvas at `/` and Pipeline at `/pipeline`.

## Product Surface

- Add a static-first Next.js landing page at `/landing`.
- Add a quiet `Home`/brand route from the product navigation without changing current application behavior.
- Present the install command as `curl -fsSL <site-origin>/install.sh | bash`, with a copy action and an adjacent link to inspect the script.
- Serve the installer as a repository-owned shell asset from `frontend/public/install.sh` so the displayed command and downloaded script cannot drift.

## Visual Direction

Use Loomi's existing Graphite, Porcelain, Moss, Slate, and structural-line palette. The composition is an asymmetric editorial briefing crossed with a restrained terminal manual: left-aligned typography, visible rules, one terminal slab, and a staggered capture-to-reuse narrative. Avoid gradients, neon, stock imagery, generic three-card feature grids, fake metrics, excessive pills, and decorative animation.

The page should feel authored and technical. It uses the existing system font fallbacks, generous but not empty spacing, and small mono metadata. Motion is limited to CSS hover/focus transitions and respects reduced motion.

## Page Structure

1. Compact landing navigation with product links and a `Launch canvas` action.
2. Asymmetric opening statement that names the knowledge-loss problem and shows the one-line installer.
3. A vertical operating model showing source event, captured rationale, and contextual recommendation.
4. A product proof section built from real Loomi concepts and interface language, not fabricated analytics.
5. Installation details: prerequisites, what the script does, environment-key requirement, local URL, and script inspection path.
6. Final launch action and small project footer.

## Installer Contract

The Bash installer will:

1. Require `git`, Docker, and Docker Compose v2, with clear actionable failures.
2. Install into `${LOOMI_HOME:-$HOME/.loomi-app}`.
3. Clone the configured public repository on first run or fast-forward an existing clean checkout on later runs.
4. Create `.env` from `.env.example` if absent, never overwrite an existing `.env`, and explain that `FEATHERLESS_API_KEY` must be set for LLM features.
5. Start the stack with `docker compose up -d --build`.
6. Seed the demo only when explicitly enabled with `LOOMI_SEED_DEMO=1`, keeping the default installer repeatable and non-destructive.
7. Print the local URL and next commands. It will use strict mode, quote variables, and never pipe secrets or invoke `sudo`.

The repository URL is overridable through `LOOMI_REPO_URL` for forks and local testing. The public command can therefore stay simple while the script remains testable.

## Failure Handling

Every prerequisite and network failure exits non-zero with a concise message. An existing non-git destination or dirty checkout is left untouched. Docker startup failures retain service logs and print the exact inspection command. Missing API credentials do not block startup because non-LLM surfaces remain useful; the warning explains the degraded capabilities.

## Verification

- Lint and production-build the Next.js frontend.
- Syntax-check the installer with `bash -n`.
- Exercise prerequisite, existing-directory, and command-rendering behavior with a lightweight shell test or controlled environment overrides.
- Confirm `/`, `/pipeline`, and `/landing` remain routable and the install command wraps without horizontal overflow on mobile.

## Scope Boundaries

No hosted backend, analytics, account system, package registry, release automation, OS package manager integration, or destructive uninstall flow. The installer is a convenience wrapper around the existing Docker Compose demo.
