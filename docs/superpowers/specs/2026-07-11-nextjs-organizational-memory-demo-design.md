# Next.js Organizational Memory Demo Design

## Objective

Build one hackathon demo in which Loomi detects a prompt-changing Git commit,
preserves its rationale, notifies another employee, and proactively suggests
the stored prompt while that employee writes a related assigned task.

The approved product layout is a Narrative Canvas: the latest memory event is
shown first and the chat/task composer continues the story directly below it.

## Approved Architecture

```text
Next.js App Router
  -> Express REST + Server-Sent Events
       -> PostgreSQL
       -> Python core service
            -> existing capture/recommend/onboarding functions
            -> Chroma
            -> Featherless API
            -> Git poller
```

Docker Compose runs separate frontend, API, core, PostgreSQL, and Chroma
services in one stack. SQLite and embedded Chroma remain available for offline
Python tests.

## Approved Interaction

- The Git poller checks HEAD every three seconds and only processes a new SHA.
- Successful relational and vector persistence produces `memory_ready`.
- The task composer searches after a 650 millisecond pause and at least 24
  normalized characters.
- Only the top result at score 0.45 or above appears as a ghost suggestion.
- A suggestion never changes user input without an explicit Use prompt action.
- Review shows content, attribution, rationale, constraints, usage, and versions.
- Failed capture remains retryable and never produces a false success notice.

## Visual Direction

- Product demo for an AI Lead, not a marketing landing page.
- Design dials: variance 7, motion 6, density 5.
- Geist and Geist Mono, zinc neutrals, one muted green accent.
- Automatic light/dark tokens and one consistent radius system.
- Motion only communicates notification arrival, suggestion appearance, and
  review transitions; reduced-motion mode is static.
- No generic dashboard grid, AI-purple styling, decorative animation, or fake
  product screenshots.

## Detailed Contracts

The authoritative requirements are split by capability under:

`openspec/changes/build-nextjs-organizational-memory-demo/specs/`

- `platform-runtime`
- `git-memory-detection`
- `proactive-memory-recommendation`
- `asset-onboarding`
- `narrative-demo-ui`

Technical decisions and trade-offs are authoritative in the OpenSpec
`design.md` for the same change.

## Success Criteria

- `docker compose up --build` makes all required services healthy.
- A real prompt-changing commit creates one live memory notification.
- A different user enters a semantically related task and receives a ghost
  suggestion without knowing the asset exists.
- Review and Use prompt are grounded in stored evidence and usage is recorded.
- Existing Python tests plus new core, Express, Next.js, Compose, accessibility,
  reduced-motion, and browser-flow checks pass.

## Boundaries

- Always: validate public input, preserve retry state, use `db/client.py`, keep
  the MiniLM model consistent, and run verification before completion.
- Ask first: changing public Python signatures, database schema contracts,
  embedding model, or Docker service boundaries.
- Never: commit secrets, fabricate successful capture, add full RBAC, introduce
  graph storage, or rewrite core logic in Express.
