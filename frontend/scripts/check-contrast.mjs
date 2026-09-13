/**
 * Contrast verification for the design tokens in src/index.css.
 *
 * Parses every `--color-*: oklch(...)` declaration out of the stylesheet,
 * converts to sRGB and checks the pairs the UI actually renders. Run with
 * `node scripts/check-contrast.mjs`; a non-zero exit means a pair fails WCAG AA
 * and the token needs its lightness adjusted, not a comment explaining it away.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(here, "../src/index.css"), "utf8");

/** oklch(L C H) -> linear sRGB, via Oklab (Björn Ottosson's published matrices). */
function oklchToLinearSrgb(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;

  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;

  return [
    +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

/** Relative luminance per WCAG 2.x, clamping out-of-gamut channels the browser would clip too. */
function relativeLuminance([r, g, b]) {
  const clamp = (v) => Math.min(1, Math.max(0, v));
  const [lr, lg, lb] = [clamp(r), clamp(g), clamp(b)];
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

function ratio(a, b) {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

const tokens = new Map();
const declaration = /--color-([a-z0-9-]+):\s*oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\)/g;
for (const [, name, L, C, H] of css.matchAll(declaration)) {
  tokens.set(name, oklchToLinearSrgb(Number(L), Number(C), Number(H)));
}
tokens.set("white", oklchToLinearSrgb(1, 0, 0));

function token(name) {
  const value = tokens.get(name);
  if (!value) throw new Error(`Token --color-${name} is not declared as oklch() in src/index.css`);
  return value;
}

const SURFACES = ["canvas", "surface", "surface-muted", "surface-sunken"];
const TONES = ["success", "warning", "danger", "info", "muted"];

/** [foreground, background, minimum, what it is]. */
const checks = [];

for (const surface of SURFACES) {
  checks.push(["text", surface, 4.5, "body text"]);
  checks.push(["text-muted", surface, 4.5, "secondary text"]);
  checks.push(["text-subtle", surface, 4.5, "placeholder / meta text"]);
  checks.push(["accent", surface, 4.5, "link / accent text"]);
  checks.push(["border-control", surface, 3, "control boundary"]);
}

for (const tone of TONES) {
  checks.push([tone, `${tone}-bg`, 4.5, `${tone} text on its own tint`]);
  checks.push([tone, "surface", 4.5, `${tone} text on a card`]);
  checks.push([tone, "canvas", 4.5, `${tone} text on the canvas`]);
  checks.push(["white", tone, 4.5, `white on solid ${tone}`]);
}

checks.push(["white", "accent", 4.5, "primary button label"]);
checks.push(["white", "accent-hover", 4.5, "primary button label, hover"]);
checks.push(["accent", "accent-soft", 4.5, "accent text on its tint"]);
checks.push(["accent-ring", "surface", 3, "focus ring"]);
checks.push(["text", "accent-soft", 4.5, "body text on the selected tint"]);

let failures = 0;
for (const [fg, bg, min, label] of checks) {
  const value = ratio(token(fg), token(bg));
  const ok = value >= min;
  if (!ok) failures += 1;
  const line = `${ok ? "ok  " : "FAIL"}  ${value.toFixed(2)}:1  (min ${min})  ${fg} on ${bg}  ${label}`;
  console.log(line);
}

console.log(`\n${checks.length - failures}/${checks.length} pairs pass.`);
process.exit(failures === 0 ? 0 : 1);
