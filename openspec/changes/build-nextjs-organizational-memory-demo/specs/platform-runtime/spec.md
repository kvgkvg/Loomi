## ADDED Requirements

### Requirement: Public API boundary
The system SHALL expose browser-facing endpoints only through the Express API,
and Express SHALL invoke the Python core through an internal HTTP boundary.

#### Scenario: Browser requests recommendations
- **WHEN** a user submits a task through the Next.js application
- **THEN** Express validates the request, calls the internal Python service, and returns the normalized recommendation result

#### Scenario: Python core is unavailable
- **WHEN** a user request reaches Express while the Python service is unavailable or exceeds its timeout
- **THEN** Express returns a structured service-unavailable response without exposing an internal stack trace

### Requirement: Existing Python contracts remain stable
The Python HTTP service MUST delegate to the existing public core functions
without changing their signatures or duplicating their domain logic.

#### Scenario: Core service delegates capture
- **WHEN** Express or the poller requests commit capture and processing
- **THEN** the service calls `capture_commit(commit_sha)` and `process_raw_event(raw_event_id)` using their existing contracts

### Requirement: Shared relational storage boundary
All Python relational storage access SHALL continue through `db/client.py`,
with PostgreSQL used in Compose and SQLite retained as a local test fallback.

#### Scenario: Compose runtime starts
- **WHEN** the application starts with its PostgreSQL connection configuration
- **THEN** `db/client.py` connects to PostgreSQL and all core modules use that shared client

#### Scenario: Offline Python tests run
- **WHEN** tests provide an isolated SQLite path and no PostgreSQL URL
- **THEN** the existing Python core runs against SQLite without requiring Docker

### Requirement: One Compose stack
The repository SHALL provide one Docker Compose stack with independently built
and health-checked frontend, API, core, PostgreSQL, and Chroma services.

#### Scenario: Operator launches the demo
- **WHEN** an operator runs `docker compose up --build`
- **THEN** every required service becomes healthy and the web application is reachable through one documented URL

#### Scenario: Containers restart
- **WHEN** stateful containers restart without their named volumes being removed
- **THEN** PostgreSQL data and Chroma vectors remain available

### Requirement: Aggregated health reporting
Express SHALL report the readiness of the API, Python core, PostgreSQL, and
Chroma as healthy or degraded.

#### Scenario: Dependency is degraded
- **WHEN** one required downstream dependency fails its readiness check
- **THEN** `/api/health` identifies that dependency and reports degraded status while the Next.js shell remains renderable
