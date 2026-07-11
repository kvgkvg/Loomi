## ADDED Requirements

### Requirement: Debounced task matching
The Next.js composer client component SHALL request recommendations 650 milliseconds after the
latest edit when the normalized task contains at least 24 characters.

#### Scenario: User pauses on a meaningful task
- **WHEN** a user enters at least 24 characters and does not edit for 650 milliseconds
- **THEN** the composer sends one recommendation request for the current text

#### Scenario: Input remains too short
- **WHEN** a user enters fewer than 24 normalized characters
- **THEN** the composer sends no recommendation request and shows no ghost suggestion

### Requirement: Cancel stale recommendation work
The client MUST cancel an outstanding recommendation request when the task
changes and MUST ignore any stale response that completes later.

#### Scenario: User edits during search
- **WHEN** a recommendation request is active and the user changes the task
- **THEN** the client aborts the active request and only the newest task can update the suggestion

### Requirement: Confidence-gated ghost suggestion
The system SHALL show only the highest-ranked asset as a ghost suggestion when
its score meets the configured threshold, defaulting to 0.45.

#### Scenario: Strong semantic match exists
- **WHEN** the top recommendation score is at least the active threshold
- **THEN** the composer shows a visually secondary suggestion with title, owner, match score, and Review action without modifying the user's text

#### Scenario: No strong match exists
- **WHEN** no recommendation reaches the active threshold
- **THEN** the composer remains usable and shows no suggestion card

### Requirement: Suggestion remains user-controlled
The system MUST NOT automatically replace or append to the user's task or
prompt based on a recommendation.

#### Scenario: Suggestion appears
- **WHEN** a ghost suggestion is displayed
- **THEN** the user's input remains unchanged until the user explicitly selects Review or Use prompt
