# App Directory Migration Implementation Plan

**Goal:** Move the verified Loomi runtime from the temporary worktree layout into
`app/frontend`, `app/backend`, and `app/core`, then fast-forward the root
checkout and remove the temporary worktree only after fresh verification.

**Architecture:** Keep root orchestration and docs at repository root. Move
Next.js, Express, and all Python runtime/test code under their owning service.
Preserve Python imports by running with `app/core` as the Python working path.

**Tech Stack:** Git-aware moves, Next.js, Express, Python, pytest, Docker
Compose, OpenSpec.

## Global Constraints

- Do not use destructive Git commands, force resets, or delete unverified work.
- Preserve all commits and the uncommitted Task 6 frontend files.
- Keep `capture_commit(commit_sha: str) -> dict` and all existing public Python
  contracts unchanged.
- Root Compose remains the orchestration entrypoint.
- Python commands from root use `PYTHONPATH=app/core`.
- Active runtime commands must not reference the old root service paths or the
  temporary worktree path.
- Remove the worktree only after root checkout verification passes.

## Task 1: Preserve and inventory the current state

- [ ] Record `git status`, current branch, worktree branch, commit list, and all
  uncommitted files in `.superpowers/sdd/migration-before.md`.
- [ ] Ensure Task 6 frontend files and package lock changes are included in the
  migration working tree before any move.
- [ ] Run `git diff --check` and save the result in the migration evidence.

Verify:

```bash
git status --short --branch
git log --oneline --decorate -15
git diff --check
```

## Task 2: Move runtime and tests with Git

- [ ] Create `app/`, `app/core/`, `app/backend/`, and `docker/` directories.
- [ ] Move `frontend` to `app/frontend` and `api` to `app/backend`.
- [ ] Move Python runtime directories to `app/core` and `tests` to
  `app/core/tests`.
- [ ] Move `requirements.txt` to `app/core/requirements.txt` and
  `Dockerfile.core` to `app/core/Dockerfile`.
- [ ] Move `chroma` to `docker/chroma`.
- [ ] Preserve uncommitted frontend files and lock changes during every move.

Verify:

```bash
git status --short
test -f app/frontend/package.json
test -f app/backend/package.json
test -f app/core/core_service/app.py
test -f app/core/db/client.py
test -f app/core/requirements.txt
test -f app/core/Dockerfile
test -f docker/chroma/Dockerfile
```

## Task 3: Rewrite active paths and launch commands

- [ ] Update `docker-compose.yml` build contexts, Dockerfile paths, health
  commands, and environment mounts to the new layout.
- [ ] Update `app/core/Dockerfile` build context assumptions and working path.
- [ ] Update package scripts and Next.js/backend references only where the move
  changed relative paths.
- [ ] Update README, OpenSpec, plans, and active memory commands to the new
  paths; retain old paths only as explicitly labeled historical migration
  context.
- [ ] Update `.gitignore` for new local state locations without ignoring source.

Verify:

```bash
rg -n "(^|[^A-Za-z0-9_])(frontend|api|core_service|Dockerfile\.core)/|\.worktrees/nextjs-memory-demo" \
  --glob '!memory/**' --glob '!docs/superpowers/specs/2026-07-11-app-directory-migration-design.md' \
  --glob '!docs/superpowers/plans/2026-07-11-app-directory-migration.md' .
```

Expected: no active runtime/config/command matches.

## Task 4: Verify from the migrated worktree

- [ ] Run Python tests using `PYTHONPATH=app/core`.
- [ ] Run backend tests/build using `npm --prefix app/backend`.
- [ ] Run frontend tests/build using `npm --prefix app/frontend`.
- [ ] Run Compose config/build and OpenSpec validation.
- [ ] Record all commands and exit codes in `.superpowers/sdd/migration-after.md`.

Verify:

```bash
PYTHONPATH=app/core .venv311/bin/pytest app/core/tests -m "not live" -q
npm --prefix app/backend test -- --run
npm --prefix app/backend run build
npm --prefix app/frontend test -- --run
npm --prefix app/frontend run build
docker compose config
docker compose build
openspec validate build-nextjs-organizational-memory-demo
git diff --check
```

## Task 5: Integrate into root checkout

- [ ] Commit the migration and all preserved Task 6 work on
  `feature/nextjs-memory-demo`.
- [ ] From the root checkout, fast-forward `feature/app-demo` to the verified
  migration commit using `git merge --ff-only feature/nextjs-memory-demo`.
- [ ] Re-run root path audit, Python tests, Node tests/builds, Compose config,
  and OpenSpec validation from `/home/pearspringmind/Hackathon/Loomi`.
- [ ] Confirm root `git status` contains only intentional ignored local state.

Verify:

```bash
git merge --ff-only feature/nextjs-memory-demo
git status --short --branch
PYTHONPATH=app/core .venv311/bin/pytest app/core/tests -m "not live" -q
npm --prefix app/backend run build
npm --prefix app/frontend run build
docker compose config
openspec validate build-nextjs-organizational-memory-demo
```

## Task 6: Remove temporary worktree safely

- [ ] Confirm root verification evidence is complete and branch pointers are
  correct.
- [ ] Remove `.worktrees/nextjs-memory-demo` with `git worktree remove`.
- [ ] Delete the auxiliary `feature/nextjs-memory-demo` branch only after the
  root branch contains its migration commit.
- [ ] Confirm no active path references the removed worktree.

Verify:

```bash
git worktree list
test ! -d .worktrees/nextjs-memory-demo
git branch --list feature/nextjs-memory-demo
git status --short --branch
```
