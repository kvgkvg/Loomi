## Why

Loomi already captures, recommends, and explains organizational AI assets, but
the capabilities are only accessible through Python entry points. The hackathon
demo needs one coherent web experience that proves a changed Git prompt can be
preserved and proactively reused by a different employee.

## What Changes

- Add a Next.js narrative canvas combining proactive Git-change notifications
  with a task composer and non-blocking ghost prompt suggestions.
- Add an Express public API for recommendation, asset review, usage tracking,
  health checks, and Server-Sent Events.
- Add a thin internal Python HTTP service around the existing core functions
  without changing their public signatures.
- Add a Git poller that detects new commits, runs the retry-safe capture
  pipeline, and publishes lifecycle events only after confirmed state changes.
- Run the web application, Python core, PostgreSQL, and Chroma as independently
  health-checked services in one Docker Compose stack.
- Preserve SQLite as a local test fallback while PostgreSQL is the Compose
  runtime database.
- Use motion-anything as a development reference for focused interaction
  patterns, not as a production runtime dependency.
- Non-goals: full RBAC/governance, graph storage, multi-branch asset identity,
  multi-environment deployment, and rewriting the Python core in TypeScript.

## Capabilities

### New Capabilities

- `platform-runtime`: Defines the Next.js and Express gateway boundaries, Python core boundary, storage,
  health checks, and Docker Compose runtime.
- `git-memory-detection`: Detects prompt-related Git changes, processes them
  safely, retries failures, and publishes capture lifecycle events.
- `proactive-memory-recommendation`: Matches an in-progress assigned task to
  stored assets and presents a cancellable ghost prompt suggestion.
- `asset-onboarding`: Lets a user review, understand, and adopt a recommended
  prompt with grounded rationale, constraints, attribution, and versions.
- `narrative-demo-ui`: Defines the combined story-first and chat-first product
  experience, responsive behavior, motion, accessibility, and UI states.

### Modified Capabilities

None. This repository has no existing OpenSpec capability specifications.

## Impact

- New frontend, Express API, and thin Python service entry points.
- `db/client.py` gains a PostgreSQL runtime path while remaining the only
  relational database access boundary.
- The capture pipeline gains polling and event publication orchestration but
  retains its existing core function contracts and retry semantics.
- Docker Compose, service Dockerfiles, environment examples, and browser-level
  verification are added.
- Existing Python tests remain authoritative for core behavior; web and
  Compose layers add focused unit, integration, and end-to-end checks.
