# Design

Surface mode: **Operate** (task-focused app UI, not a marketing surface). Design read: *a case-preparation tool for a stressed, non-technical business owner or their lawyer, used under time pressure, where trust comes from restraint and precision rather than visual flourish.* No branding system — tokens only, per `spec/frontend.md` F7 (out of scope: branding system).

Chosen deliberately over the generic AI defaults: no purple/blue glow gradients, no glassmorphism, no display serif dressing up a compliance tool. One neutral scale, one accent, a fixed semantic-state vocabulary that must stay legible under stress (someone scanning for "what's still wrong with my dossier").

## Color

Strategy: **Restrained** (neutrals + one accent), the Operate-mode floor. Light theme only for this MVP (no confirmed need for dark mode; revisit if requested).

Neutral scale (cool, slightly blue-tinted — pairs with the accent without competing):

| Token | Value | Use |
| --- | --- | --- |
| `--color-canvas` | `#F6F7FA` | App background |
| `--color-surface` | `#FFFFFF` | Cards, panels, inputs |
| `--color-surface-muted` | `#EEF1F5` | Header, sidebar, secondary panels |
| `--color-border` | `#DCE0E7` | Default borders/dividers |
| `--color-border-strong` | `#B9C0CC` | Emphasized borders, input focus rest state |
| `--color-text` | `#161A22` | Primary text |
| `--color-text-muted` | `#565E6E` | Secondary text, captions |
| `--color-text-subtle` | `#8991A3` | Placeholders, disabled text |

Accent — one color, used only for primary actions, current selection, and links (never decoration):

| Token | Value | Use |
| --- | --- | --- |
| `--color-accent` | `#2B4E8C` | Primary buttons, active nav, links |
| `--color-accent-hover` | `#213D6E` | Hover/active of the above |
| `--color-accent-contrast` | `#FFFFFF` | Text/icons on accent fill |
| `--color-accent-soft` | `#E7EDF7` | Selected row, focus-tint backgrounds |

Semantic state colors — this app's real content is a small fixed vocabulary of document/check/job states, so these five pairs are used everywhere that vocabulary appears (badges, banners, borders) and nowhere else:

| Token | Value (fg / soft bg) | Maps to |
| --- | --- | --- |
| `--color-success` / `--color-success-bg` | `#1B7A4D` / `#E4F4EA` | `satisfied`, `resolved`, `ready` (document/analysis), `succeeded` |
| `--color-warning` / `--color-warning-bg` | `#8A5A0A` / `#FBF0DA` | `partial`, `unassessable`, `processing`, `queued`, `running`, `needs_information` |
| `--color-danger` / `--color-danger-bg` | `#B02A25` / `#FAE7E5` | `contradicted`, `rejected`, `unreadable`, `failed`, `outdated` |
| `--color-info` / `--color-info-bg` | `#3A5273` / `#E9EEF5` | `uploaded`, `not_checked`, neutral informational states |
| `--color-muted` / `--color-muted-bg` | `#666D7A` / `#EEF0F3` | `not_applicable`, `superseded`, disabled/inactive |

Contrast checked at AA (4.5:1) for text-on-background and text-on-soft-bg pairs above.

## Typography

One family (Operate-mode guidance: a well-tuned sans carries headings, labels, body, and data — no display/body pairing, no invented brand face). System font stack — loads instantly, renders correctly for French and has broad Arabic glyph coverage for embedded source-document text without shipping a webfont for a two-day-build compliance tool.

```
--font-sans: -apple-system, "Segoe UI", Roboto, "Noto Sans Arabic", "Noto Sans", Arial, sans-serif;
--font-mono: ui-monospace, "SF Mono", "Cascadia Mono", Consolas, monospace;
```

`--font-mono` with `font-variant-numeric: tabular-nums` is used for money amounts, revision numbers, IDs and dates — anything meant to be scanned/compared column-wise.

Fixed rem scale, ~1.125–1.2 ratio (Operate guidance: no fluid/clamp type):

| Token | Size | Use |
| --- | --- | --- |
| `--text-xs` | 0.75rem (12px) | Meta captions, badge labels |
| `--text-sm` | 0.8125rem (13px) | Secondary UI text, table cells |
| `--text-base` | 0.9375rem (15px) | Body, form inputs, default UI text |
| `--text-md` | 1.0625rem (17px) | Card titles, emphasized body |
| `--text-lg` | 1.25rem (20px) | Section headings |
| `--text-xl` | 1.5rem (24px) | Page titles |

Line-height: 1.45 for body copy, 1.25 for headings. Prose (narrative text, explanations) caps at `65ch`; tables and dense data are unconstrained.

## Spacing & shape

4px base grid: `--space-1` (4px) through `--space-16` (64px), steps 1/2/3/4/5/6/8/10/12/16.

Radius — one scale, locked by role (shape-consistency rule: never mix radii for the same role):

| Token | Value | Role |
| --- | --- | --- |
| `--radius-sm` | 6px | Inputs, buttons, checkboxes |
| `--radius-md` | 10px | Cards, panels, modals |
| `--radius-full` | 9999px | Badges/pills, avatars |

## States & components

Every interactive element implements: default, hover, focus-visible, active, disabled — and loading/error where relevant (form fields, buttons that trigger a request). Focus ring: 2px `--color-accent` outline with 2px offset, never removed. No custom scrollbars, no non-standard form controls, no modal as a first resort (the finding/response flows use inline expansion, not dialogs, except where a true interrupt is needed, e.g. the submission confirmation).

Loading uses skeletons that mirror final layout shape, not spinners floating in empty content. Empty states name the next action ("Aucun dossier pour l'instant — créez-en un").

## Motion

150–250ms transitions (`--motion-fast: 150ms`, `--motion-base: 220ms`, `cubic-bezier(0.4,0,0.2,1)`) for state changes only: hover/press feedback, expand/collapse, banner/toast entry. No page-load choreography, no decorative loops — this is a tool used under stress, and a user should never wait on a curtain-raise.

## French / Arabic text handling

- Document `lang="fr"`, UI copy in French; identifiers/code stay in English.
- Any rendered source-document text (OCR/extracted quotes, filenames when they contain Arabic) is wrapped in a container with `dir="auto"` and `unicode-bidi: plaintext`, so a paragraph that is actually Arabic lays out right-to-left even inside the French left-to-right shell, without flipping the surrounding chrome.
- Such containers get a visible "quoted source" treatment (left border in `--color-border-strong`, `--color-surface-muted` background, `--font-mono` off for prose — keep `--font-sans` but slightly smaller) so a verbatim excerpt from a document is never visually confused with UI copy.
- All document text is escaped and rendered as text, never `dangerouslySetInnerHTML`.

## Fixture-mode banner (FE-12)

A persistent, non-dismissible banner (`--color-warning-bg` background, `--color-warning` text/icon) reading "Données de démonstration — aucune analyse réelle en cours." rendered at the top of the authenticated app shell whenever `VITE_DATA_MODE=fixture`. It is chrome, not a toast: it does not auto-hide and does not stack with other banners.
