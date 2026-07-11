# App Directory Migration Design

## Objective

Move the Loomi runtime out of the temporary Git worktree layout and organize it
under one explicit `app/` directory without losing commits, uncommitted Task 6
work, tests, Docker behavior, or rollback capability.

The final checked-out source must live directly at
`/home/pearspringmind/Hackathon/Loomi/app/`. The temporary
`.worktrees/nextjs-memory-demo` checkout and its auxiliary branch are removed
only after the root checkout is updated and verified.

## Target Structure

```text
app/
  frontend/                 # Next.js App Router product UI
  backend/                  # Express public API and SSE gateway
  core/                     # Python domain and internal HTTP service
    adapters/
    capture_pipeline/
    core_service/
    db/
    onboarding/
    recommend/
    tests/
    requirements.txt
    Dockerfile
docker/
  chroma/
    Dockerfile
docker-compose.yml
DESIGN.md
docs/
memory/
openspec/
```

Root-level orchestration and project documentation remain at the repository
root. Runtime source and service-specific tests live with their owning service.

## Exact Path Mapping

| Current path | Target path |
| --- | --- |
| `frontend/` | `app/frontend/` |
| `api/` | `app/backend/` |
| `adapters/` | `app/core/adapters/` |
| `capture_pipeline/` | `app/core/capture_pipeline/` |
| `core_service/` | `app/core/core_service/` |
| `db/` | `app/core/db/` |
| `onboarding/` | `app/core/onboarding/` |
| `recommend/` | `app/core/recommend/` |
| `tests/` | `app/core/tests/` |
| `requirements.txt` | `app/core/requirements.txt` |
| `Dockerfile.core` | `app/core/Dockerfile` |
| `chroma/` | `docker/chroma/` |

Existing root files such as `demo.py` that import Python modules must either be
moved into `app/core/` or documented as root launchers using `PYTHONPATH=app/core`.
The migration chooses the smallest option after auditing each caller.

## Python Import Strategy

Existing imports remain stable:

```python
from db.client import get_pg_connection
from recommend.engine import recommend
```

The migration does not rewrite them to `app.core.*`. Python runs with
`app/core` as its working directory in containers and with `PYTHONPATH=app/core`
from the repository root. This preserves public contracts and avoids a broad
package refactor unrelated to the directory change.

## Runtime Path Strategy

- Next.js commands use `npm --prefix app/frontend`.
- Express commands use `npm --prefix app/backend`.
- Python tests use `PYTHONPATH=app/core pytest app/core/tests`.
- Compose remains at the repository root.
- Compose build contexts become `./app/frontend`, `./app/backend`, `./app/core`,
  and `./docker/chroma`.
- The core image uses `/workspace/app/core` as its working directory.
- Named PostgreSQL and Chroma volumes are unchanged.
- Browser-facing ports and service names are unchanged.

## Migration Sequence

1. Inventory commits, dirty files, ignored files, Docker paths, scripts, docs,
   and Python imports in the current worktree.
2. Preserve Task 6 dependency and test-scaffold changes as part of the migration
   branch; do not discard or overwrite them.
3. Perform Git-aware moves inside `feature/nextjs-memory-demo`.
4. Update runtime configuration, test commands, docs, OpenSpec, and plans to the
   new paths.
5. Run static path and import audits.
6. Run all service tests, builds, and Compose verification in the worktree.
7. Commit the migration and verification evidence.
8. Fast-forward the root `feature/app-demo` branch to the verified branch.
9. Repeat critical path checks from the root checkout.
10. Remove the linked worktree and auxiliary branch only after root verification.

## Static Path Audit

The audit must distinguish stale operational references from historical text.
Runtime configuration, executable commands, Dockerfiles, tests, and active docs
must not reference:

- root `frontend/`
- root `api/`
- root `core_service/`
- root `Dockerfile.core`
- `.worktrees/nextjs-memory-demo`

Historical memory may mention the former worktree only when clearly labeled as
past context. No executable command may depend on it.

## Verification

Run in the migrated branch:

```bash
PYTHONPATH=app/core pytest app/core/tests -m "not live" -q
npm --prefix app/backend test -- --run
npm --prefix app/backend run build
npm --prefix app/frontend test -- --run
npm --prefix app/frontend run build
docker compose config
docker compose build
openspec validate build-nextjs-organizational-memory-demo
git diff --check
```

After fast-forwarding the root checkout, repeat the Python suite, both Node
builds, Compose config, OpenSpec validation, and static path audit from
`/home/pearspringmind/Hackathon/Loomi`.

## Error Handling and Rollback

- A failing move, import, test, build, or Compose check stops the migration.
- The linked worktree is retained while any verification is unresolved.
- The root branch is not updated until the migration branch is clean and tested.
- The worktree is not removed until the root checkout passes critical checks.
- If root fast-forward is not possible, stop and inspect branch divergence; do
  not force-reset or overwrite either branch.
- No runtime data volume is deleted by this migration.

## Boundaries

- Always preserve commit history, ignored runtime state, and Task 6 uncommitted
  work.
- Always use Git-aware moves and update active path references in the same
  migration.
- Ask before resolving unexpected root-branch divergence or conflicting user
  edits.
- Never use `git reset --hard`, delete unverified work, remove data volumes, or
  remove the worktree before root verification.

## Success Criteria

- All runtime source exists under `app/frontend`, `app/backend`, or `app/core`.
- The root checkout contains the verified migration commits.
- Python, Express, Next.js, Compose, and OpenSpec checks pass using new paths.
- No active runtime or command references the old root service paths.
- `.worktrees/nextjs-memory-demo` and its auxiliary branch are removed safely.
