# Design System: Loomi Narrative Canvas

## 1. Visual Theme and Atmosphere

Loomi is a high-trust organizational memory product for an AI Lead. It feels
like an intelligence briefing that has become a calm working surface: offset
asymmetric, medium-density, and deliberately alive only when organizational
knowledge changes. Design variance is 7, motion intensity is 6, and visual
density is 5.

The primary screen tells one continuous story. A new Git memory appears first,
an assigned task follows, and a relevant stored prompt becomes visible without
claiming the user's attention. This is product UI, not a marketing landing
page. Do not create a generic dashboard grid.

## 2. Color Palette and Roles

- **Graphite Canvas** (`#181A19`) - main dark background and dark-mode base.
- **Porcelain Surface** (`#F3F5F2`) - main light background and light-mode base.
- **Ink Text** (`#1F2320`) - light-mode primary text.
- **Chalk Text** (`#F4F6F2`) - dark-mode primary text.
- **Moss Accent** (`#3D6B4F`) - the only accent, for primary actions, focus,
  successful memory readiness, and semantic match emphasis.
- **Moss Soft** (`#C9D9CC`) - light-mode active surface and success background.
- **Slate Detail** (`#66706A`) - secondary text and metadata.
- **Structural Line** (`#D8DED8` light, `#373D38` dark) - hairline separators.
- **Alert Rust** (`#A65338`) - error-only state, never used as a second brand accent.

Never use pure black, pure white, purple glow, blue neon, rainbow gradients,
or mixed warm/cool gray families.

## 3. Typography Rules

- **Display:** Cabinet Grotesk, `clamp(2.75rem, 5vw, 5.5rem)`, tight tracking,
  medium to semibold weight. No headline may exceed three lines.
- **Body:** Cabinet Grotesk, 16px minimum, 1.55 line-height, 65ch maximum.
- **Mono:** Geist Mono, 12-14px, for SHA, timestamps, similarity, version, and
  processing metadata.
- **Fallback:** `ui-sans-serif, system-ui, sans-serif` and `ui-monospace`.
- **Banned:** Inter, serif type, all-caps decorative section labels, em dashes,
  and decorative meta copy.

## 4. Layout Principles

- Use a 12-column CSS Grid on desktop with `max-width: 1400px` and 24px gutters.
- The initial Narrative Canvas uses Artistic Asymmetry: a broad event narrative
  occupies 7 columns and a grounded asset preview occupies 5 columns.
- The composer and review panel use a 7/5 split above 768px and collapse to one
  column below 768px.
- Every multi-column grid uses `grid-auto-flow: dense`; grid spans must fill
  their declared row with no empty cell.
- All page roots use `overflow-x-hidden`, `min-height: 100dvh`, and no
  percentage `calc()` layout math.
- Keep content in normal document flow. Absolute positioning is reserved for
  decorative background texture only, never readable content.
- Touch targets are at least 44px. Keyboard focus is a 2px Moss Accent ring.

## 5. Components and States

- **Top navigation:** compact split navigation, 64px desktop height, brand at
  left, health state and theme control at right. The navigation never wraps.
- **Memory event:** an asymmetric narrative panel containing source, prompt
  title, owner, version, and a Review action. It is not a generic notification
  toast.
- **Task composer:** a labeled textarea, clear status, and a ghost suggestion
  that appears only after a valid semantic match. It never edits user input.
- **Ghost suggestion:** a translucent but high-contrast inset surface with
  title, owner, score, and Review. It has no pill tag or decorative dot.
- **Evidence stack:** versions, rationale, constraints, and attribution shown
  in a compact vertical sequence with spacing and sparse dividers.
- **Buttons:** primary Moss Accent fill with Porcelain text; secondary outlined
  surface with Ink or Chalk text; active state translates down 1px. Labels fit
  on one line.
- **Inputs:** label above, helper text in markup, inline error below, and no
  placeholder-only label.
- **Loading:** skeleton blocks sized to their final content. No spinner-only
  state.
- **Empty:** a composed plain-language explanation of how a prompt-changing
  commit populates the memory feed.
- **Error:** inline capability-specific error with Retry where valid.

## 6. Motion and Interaction

GSAP is isolated in one client-only narrative module. It uses the selected
Scrubbed Text Reveal for the memory rationale and selected Scroll Pinning for
the evidence heading on large screens. The implementation must use
`@gsap/react`, `ScrollTrigger`, `start: "top top"`, cleanup via GSAP context,
and static rendering when reduced motion is enabled.

The Ghost Suggestion Composer and Version Evidence Stack have short,
state-driven opacity and transform transitions only. No infinite carousel,
marquee, cursor effect, global scroll listener, layout thrashing, or
unmotivated animation is permitted. Animate only `transform` and `opacity`.

## 7. Asset Direction

The Inline Typography Image selection is expressed as one small generated or
provided Git-diff texture within the display heading, not a fake dashboard
screenshot. Use a real asset only if it supports the memory story. It must not
contain overlaid labels, fabricated metrics, or stock-photo captions.

## 8. Responsive and Accessibility Rules

- Below 768px, every multi-column region becomes one column with 16px gutters.
- No horizontal overflow, clipped focus ring, or hover-only action is allowed.
- Respect `prefers-reduced-motion` and `prefers-color-scheme` from first render.
- All async status changes use appropriate live regions.
- Text and controls meet WCAG AA contrast in light and dark mode.

## 9. Anti-Patterns

- No emojis, generic placeholder names, fake precise metrics, or AI-copy
  cliches.
- No three equal feature cards, hero sales copy, or generic SaaS dashboard.
- No AI-purple gradients, neon outer glows, pure black, pure white, or
  oversaturated accents.
- No decorative status dots, section numbers, version stamps, scroll cues,
  image overlays, or unnecessary pills.
- No fake screenshot made of div rectangles.
- No six-line headline, no centered high-variance hero, and no text overlap.
- No em dash character in visible copy.

## 10. Deterministic Design Selection

```text
Python RNG seed: 71
Hero architecture: Artistic Asymmetry
Component architectures: Ghost Suggestion Composer, Version Evidence Stack, Inline Typography Images
GSAP paradigms: Scrubbed Text Reveal, Scroll Pinning
Typography stack: Cabinet Grotesk plus Geist Mono
```

The page maps AIDA to product narrative: navigation opens the canvas,
Attention is the captured memory event, Interest is the composer and semantic
suggestion, Desire is grounded review evidence, and Action is explicit Use
prompt adoption. The display heading uses `max-w-6xl`, remains under three
lines, and has no stamps or spam tags. The desktop bento uses a 12-column row
with a 7-column narrative and 5-column evidence region, so 7 + 5 = 12 and no
grid void remains.
