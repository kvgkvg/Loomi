## ADDED Requirements

### Requirement: Grounded asset review
The system SHALL let a user review a recommended asset with its content,
owner attribution, source, usage count, rationale, constraints, and complete
ordered version history.

#### Scenario: User reviews a suggestion
- **WHEN** a user selects Review on a ghost suggestion
- **THEN** the system loads and displays the asset and its grounded relational evidence without altering the composer

### Requirement: Grounded explanation
The system SHALL answer an optional asset question through the existing
onboarding assistant and MUST restrict citations to stored versions and exact
stored constraints.

#### Scenario: User asks why the prompt exists
- **WHEN** a user submits a question from the asset review panel
- **THEN** the response explains the stored rationale and returns only validated version and constraint citations

#### Scenario: Explanation provider fails
- **WHEN** the LLM or database fails during explanation
- **THEN** the review panel shows a contextual retryable error with empty citations and remains open

### Requirement: Explicit prompt adoption
The system SHALL insert stored prompt content into the composer only after the
user selects Use prompt and SHALL record that adoption in `asset_usage`.

#### Scenario: User adopts a prompt
- **WHEN** a user selects Use prompt in the review panel
- **THEN** the stored prompt content is inserted into the composer and one usage record is created for the assigned task

#### Scenario: Usage recording fails
- **WHEN** prompt insertion succeeds locally but usage persistence fails
- **THEN** the composer retains the inserted prompt and shows a non-destructive usage-recording warning
