## ADDED Requirements

### Requirement: Poll repository HEAD
The system SHALL poll the configured Git repository every three seconds by
default and act only when the observed HEAD SHA differs from the last
successfully observed SHA.

#### Scenario: New commit appears
- **WHEN** a prompt-related commit becomes the configured repository HEAD
- **THEN** the poller captures that SHA exactly once and begins memory processing

#### Scenario: HEAD is unchanged
- **WHEN** repeated polling observes the same SHA
- **THEN** the poller performs no duplicate capture or processing

### Requirement: Persist poll position
The poller MUST persist its last observed and last successfully processed SHAs
in PostgreSQL so container restarts do not duplicate completed work.

#### Scenario: Poller restarts
- **WHEN** the core container restarts after a commit was processed successfully
- **THEN** the poller resumes from persisted state and does not recapture that commit

### Requirement: Retry-safe processing
Capture failures MUST preserve `raw_events.processed = false`, MUST NOT crash
the poll loop, and SHALL be retried with bounded backoff.

#### Scenario: Rationale extraction fails
- **WHEN** the LLM call fails while processing a captured raw event
- **THEN** the event remains unprocessed, a retry lifecycle event is emitted, and polling continues

#### Scenario: Retry succeeds
- **WHEN** a previously failed event completes on a later retry
- **THEN** it is marked processed once and becomes eligible for a success notification

### Requirement: Capture lifecycle events
The core SHALL publish `capture_started`, `capture_retrying`, and
`memory_ready` lifecycle events, and SHALL emit `memory_ready` only after both
relational and vector persistence succeed.

#### Scenario: Commit processing succeeds
- **WHEN** a new asset version and its embedding are stored successfully
- **THEN** connected users receive one `memory_ready` event containing the asset identifier, title, source, and version

#### Scenario: Vector persistence fails
- **WHEN** relational writes succeed but embedding persistence fails
- **THEN** connected users do not receive `memory_ready` and the raw event remains retryable
