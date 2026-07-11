## ADDED Requirements

### Requirement: Narrative canvas composition
The web demo SHALL present Git memory activity before the assigned-task
composer so the screen tells one continuous capture-to-reuse story.

#### Scenario: User opens the application
- **WHEN** the initial data request completes
- **THEN** the page shows the latest organizational memory event above the task composer and keeps the primary composer action visible

### Requirement: Live memory notifications
The Next.js application SHALL subscribe to Express Server-Sent Events and render
capture lifecycle states without requiring a page refresh.

#### Scenario: Memory becomes ready
- **WHEN** the browser receives a `memory_ready` event
- **THEN** it presents one accessible notification with a Review action and updates the narrative event region

#### Scenario: Event stream disconnects
- **WHEN** the SSE connection is interrupted
- **THEN** the application indicates reconnection status, retries automatically, and keeps the composer usable

### Requirement: Complete interface states
The interface SHALL provide contextual loading, empty, success, degraded, and
retry states for memory activity, recommendation, asset review, and service
availability.

#### Scenario: No memory exists
- **WHEN** the memory feed returns no captured assets
- **THEN** the narrative region explains that a prompt-changing commit will populate it and does not display fabricated data

#### Scenario: Platform is degraded
- **WHEN** health reporting identifies an unavailable backend dependency
- **THEN** the interface names the unavailable capability and leaves unaffected interactions enabled

### Requirement: Responsive and accessible presentation
The interface MUST support keyboard operation, visible focus, semantic status
announcements, WCAG AA contrast, and an explicit single-column layout below
768 pixels.

#### Scenario: Keyboard-only user reviews a suggestion
- **WHEN** a keyboard-only user navigates from the composer to a suggestion
- **THEN** focus order is logical, focus is visible, and Review can be activated without a pointer

#### Scenario: Narrow viewport renders
- **WHEN** viewport width is below 768 pixels
- **THEN** the narrative region, composer, and review panel render in one column without horizontal scrolling

### Requirement: Purposeful reduced motion
The interface SHALL use motion only for notification arrival, suggestion
appearance, and review-panel state transition, and MUST provide static behavior
when reduced motion is requested.

#### Scenario: Reduced motion is enabled
- **WHEN** the operating system reports `prefers-reduced-motion: reduce`
- **THEN** all non-essential transitions become immediate while content and state changes remain understandable

### Requirement: Consistent visual system
The interface SHALL use Geist and Geist Mono, neutral zinc surfaces, one muted
green accent, automatic light/dark tokens, and the documented radius system.

#### Scenario: Theme preference changes
- **WHEN** the operating system switches between light and dark preferences
- **THEN** the entire page changes token set without mixed-theme sections or loss of contrast
