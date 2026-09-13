# Design

Surface mode: **Operate** (task-focused app UI, not a marketing surface). Design read: *a case-preparation tool for a stressed, non-technical business owner or their lawyer, used under time pressure, where trust comes from restraint and precision rather than visual flourish.* No branding system, tokens only, per `spec/frontend.md` F7 (out of scope: branding system).

Chosen deliberately over the generic AI defaults: no purple/blue glow gradients, no glassmorphism, no display serif dressing up a compliance tool. One neutral scale, one accent, a fixed semantic-state vocabulary that must stay legible under stress (someone scanning for "what's still wrong with my dossier").

## Color

Strategy: **Restrained** (neutrals + one accent), the Operate-mode floor. Light theme only for this MVP (no confirmed need for dark mode; revisit if requested).

Authored in **OKLCH** so lightness can be tuned without disturbing hue or chroma. Chroma is deliberately higher than a "safe" compliance palette: the states are the product's real content, and a state the user cannot see at a glance is a failed state. Every pair the UI renders is verified by `node scripts/check-contrast.mjs`, which parses `src/index.css` directly and exits non-zero on a failure. Do not adjust a token without rerunning it.

Neutral scale (cool, hue 258):

| Token | Value | Use |
| --- | --- | --- |
| `--color-canvas` | `oklch(0.974 0.005 258)` | App background |
| `--color-surface` | `oklch(1 0 0)` | Cards, panels, inputs |
| `--color-surface-muted` | `oklch(0.963 0.008 258)` | Secondary panels, hover fills |
| `--color-surface-sunken` | `oklch(0.948 0.010 258)` | Toolbars and quiet strips (second neutral layer) |
| `--color-border` | `oklch(0.902 0.012 258)` | Dividers. Decorative, so 3:1 does not apply |
| `--color-border-strong` | `oklch(0.780 0.020 258)` | Emphasis dividers, quote rails, hover borders |
| `--color-border-control` | `oklch(0.620 0.026 258)` | Input / select / secondary-button boundary. Verified at 3:1 (WCAG 1.4.11) |
| `--color-text` | `oklch(0.245 0.021 265)` | Primary text |
| `--color-text-muted` | `oklch(0.470 0.024 262)` | Secondary text, captions |
| `--color-text-subtle` | `oklch(0.527 0.022 262)` | Meta text, placeholders. Still AA on the darkest surface |

Accent, one color, used only for primary actions, current selection, and links (never decoration):

| Token | Value | Use |
| --- | --- | --- |
| `--color-accent` | `oklch(0.515 0.196 264)` | Primary buttons, active step, links |
| `--color-accent-hover` | `oklch(0.445 0.185 264)` | Hover/active of the above |
| `--color-accent-contrast` | `oklch(1 0 0)` | Text/icons on accent fill |
| `--color-accent-soft` | `oklch(0.955 0.032 264)` | Selected row, text selection, focus tints |
| `--color-accent-ring` | `oklch(0.655 0.160 264)` | Attention flash on a jumped-to card |

The accent is also bound to `accent-color` and `caret-color` on `html`, so native checkboxes, radios and the text caret stop rendering in browser blue.

Semantic state colors. This app's real content is a small fixed vocabulary of document/check/job states, so these five pairs are used everywhere that vocabulary appears and nowhere else:

| Token | Value (fg / soft bg) | Maps to |
| --- | --- | --- |
| `--color-success` / `-bg` | `oklch(0.508 0.135 156)` / `oklch(0.955 0.048 156)` | `satisfied`, `resolved`, `ready`, `succeeded` |
| `--color-warning` / `-bg` | `oklch(0.520 0.128 72)` / `oklch(0.958 0.058 82)` | `partial`, `unassessable`, `processing`, `queued`, `running`, `needs_information` |
| `--color-danger` / `-bg` | `oklch(0.518 0.196 26)` / `oklch(0.955 0.038 26)` | `contradicted`, `rejected`, `unreadable`, `failed`, `outdated` |
| `--color-info` / `-bg` | `oklch(0.500 0.090 250)` / `oklch(0.955 0.028 250)` | `uploaded`, `not_checked`, neutral informational states |
| `--color-muted` / `-bg` | `oklch(0.500 0.015 262)` / `oklch(0.952 0.006 262)` | `not_applicable`, `superseded`, disabled/inactive |

### How state is encoded (and how it is not)

- **Not a colored edge rail.** A tone-colored `border-inline-start` above 1px is banned on cards, list items, callouts and alerts. It is the cheapest way to look "designed" and it reads as a template.
- **Severity is carried by fill:** a tinted header band or panel background in the state's `-bg`, a 1px border in the state tone at low alpha, and a filled round glyph (solid tone with white icon for outstanding work, soft tint for a settled one).
- **On a tinted surface, secondary text is derived from that hue,** never neutral gray.
- **Color is never the only signal.** Every state ships an icon and a text label alongside it.

## Typography

**One family, Inter Variable**, self-hosted from `@fontsource-variable/inter` (woff2, `font-display: swap`; no Google Fonts link). Inter is normally a discouraged default, and it is used here on the project owner's explicit instruction: this is a dense French-language Operate surface where a neutral, exhaustively-hinted UI face is the right answer and character belongs in the details, not the letterforms.

```
--font-sans: "Inter Variable", "Inter", "Noto Sans Arabic", "Segoe UI", Roboto, sans-serif;
```

`Noto Sans Arabic` stays in the stack: Inter ships no Arabic coverage and source documents may contain Arabic text.

**Numerals use Inter, not monospace.** `.tabular` applies `font-variant-numeric: tabular-nums` with `tnum`/`ss03`, so money, revisions, IDs, dates and counts still align column-wise without a monospace costume. `--font-mono` is not defined and no UI text uses one.

Fixed rem scale, ~1.125-1.2 ratio (Operate guidance: no fluid/clamp type):

| Token | Size | Use |
| --- | --- | --- |
| `--text-xs` | 0.75rem (12px) | Meta captions, badge labels |
| `--text-sm` | 0.8125rem (13px) | Secondary UI text, table cells |
| `--text-base` | 0.9375rem (15px) | Body, form inputs, default UI text |
| `--text-md` | 1.0625rem (17px) | Card titles, emphasized body |
| `--text-lg` | 1.25rem (20px) | Section headings, verdict headline |
| `--text-xl` | 1.5rem (24px) | Page titles |

Inter runs loose at heading sizes, so `h1`/`h2`/`h3` carry `letter-spacing: -0.014em` from the base layer and body copy carries `-0.006em`; `--tracking-tight` / `--tracking-tighter` tighten specific display moments further. Line-height 1.45 for body, 1.25 for headings. Prose caps at 65-68ch; data is unconstrained.

## Spacing & shape

4px base grid: `--space-1` (4px) through `--space-16` (64px), steps 1/2/3/4/5/6/8/10/12/16.

Radius, one scale, locked by role (never mix radii for the same role):

| Token | Value | Role |
| --- | --- | --- |
| `--radius-sm` | 6px | Inputs, buttons, checkboxes |
| `--radius-md` | 10px | Cards, panels, modals |
| `--radius-full` | 9999px | Badges/pills, avatars |

Elevation is tinted to the canvas hue and always carries an offset plus a soft blur, never a zero-offset halo: `--shadow-raised`, `--shadow-lifted`, `--shadow-overlay`, and `--shadow-action` (accent-tinted, primary buttons only).

## States & components

Every interactive element implements default, hover, focus-visible, active, pending and disabled. Focus ring: 2px `--color-accent` outline at 2px offset, never removed.

**Button intent decides the variant**, not visual balance:

| Variant | Look | Intent |
| --- | --- | --- |
| `primary` | Accent fill, accent-tinted shadow | Submit, confirm, advance the flow |
| `secondary` | `--color-border-control` outline on surface | Anything reversible |
| `ghost` | Text only | Tertiary actions, in-place toggles |
| `danger` | Solid `--color-danger` fill | The confirming step of a destructive action |
| `dangerQuiet` | Danger text with a danger outline | Offering a destructive action before confirmation |

`pending` marks the control busy and runs a 2px indeterminate sweep along its bottom edge, tinted from the button's own foreground. Loading elsewhere uses skeletons that mirror the final layout shape, never a spinner floating in empty content. Empty states name the next action.

**Progressive disclosure carries density.** In the Vérifications step the verdict answers the question, the documented balance and its qualification stay visible, and the coverage counts, per-result tallies and change summary collapse into one "Détail de l'analyse" disclosure. A finding card is itself a disclosure: outstanding issues open themselves because they are the work, settled checks collapse to a single scannable row. No modal is used as a first resort.

**One statement of outcome per finding.** The old vocabulary stacked result, status and delta as three pills on every card, which turned the answer into decoration. Now the result is tone-colored typography with one icon, the open/resolved status is a clause on the same line ("Écart avec les pièces · à traiter"), and the delta appears in the header only when it asks for attention (`new`, `reopened`), otherwise in the technical detail.

## Motion

150-250ms transitions for state changes only: hover and press feedback, expand/collapse, drawer/toast entry. Named animations are limited to work-in-progress (analysis phase rail, upload, skeleton shimmer, button sweep), surface entry, and the attention flash on a jumped-to finding. Everything collapses under `prefers-reduced-motion: reduce`. No page-load choreography and no decorative loops: this is a tool used under stress.

## Browser surfaces

The parts we did not draw still carry the design: `::selection` uses `--color-accent-soft`, `caret-color` and `accent-color` use the accent, `scrollbar-color` uses `--color-border-strong` on a transparent track, links set `text-underline-offset`, and native `<summary>` markers are replaced by an icon. Buttons get their pointer cursor back in a single base-layer rule, because Tailwind v4's preflight resets them to `cursor: default`.

## French / Arabic text handling

- Document `lang="fr"`, UI copy in French; identifiers/code stay in English.
- Any rendered source-document text (OCR/extracted quotes, filenames containing Arabic) sits in a container with `dir="auto"` and `unicode-bidi: plaintext`, so an Arabic paragraph lays out right-to-left inside the French LTR shell without flipping the surrounding chrome.
- Such containers get a visible "quoted source" treatment (`.source-quote`: `--color-surface-muted` fill inside a 1px `--color-border`, one step smaller than body, looser leading) so a verbatim excerpt is never confused with UI copy. Deliberately a bordered block, not a thick inline-start rail: provenance is carried by the "Voir facture.pdf, page 1" control directly beneath each quote.
- All document text is escaped and rendered as text, never `dangerouslySetInnerHTML`.

## Fixture-mode banner (FE-12)

A persistent, non-dismissible banner (`--color-warning-bg` background, `--color-warning` text/icon) reading "Données de démonstration. Aucune analyse réelle n'est en cours." at the top of the authenticated app shell whenever `VITE_DATA_MODE=fixture`. It is chrome, not a toast: it does not auto-hide and does not stack with other banners.
