/**
 * Client-side normalization for `claimed_amount` (spec/backend.md B3: "Nonnegative
 * canonical decimal string, maximum 12 integer digits and 3 fractional digits ...
 * never a JSON float"). This never parses to a number — every step stays on strings
 * so no float rounding can occur.
 *
 * French comma input is converted to a canonical dot only when unambiguous
 * (frontend.md F4 / brief). A comma is ambiguous when it could also be read as a
 * thousands separator, i.e. when 3 or fewer digits precede it (e.g. "1,000") or
 * when the string mixes both "," and "." (e.g. "20.000,5") — those are rejected
 * and the user is asked to clarify rather than guessed at.
 */

const CANONICAL = /^\d{1,12}(\.\d{1,3})?$/;

export type AmountValidation = { ok: true; value: string } | { ok: false; message: string };

export function normalizeClaimedAmount(raw: string): AmountValidation {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: false, message: "Le montant réclamé est obligatoire." };
  }
  if (trimmed.startsWith("-")) {
    return { ok: false, message: "Le montant réclamé ne peut pas être négatif." };
  }

  const hasComma = trimmed.includes(",");
  const hasDot = trimmed.includes(".");
  let candidate = trimmed;

  if (hasComma && hasDot) {
    return {
      ok: false,
      message: "Format ambigu : n'utilisez qu'un seul séparateur décimal, par ex. 20000.500.",
    };
  }

  if (hasComma) {
    const parts = trimmed.split(",");
    if (parts.length > 2) {
      return {
        ok: false,
        message: "Format ambigu (plusieurs virgules) : indiquez seulement les décimales, par ex. 20000,500.",
      };
    }
    const [intPart, fracPart] = parts;
    if (intPart.length <= 3) {
      return {
        ok: false,
        message:
          "Format ambigu : la virgule pourrait être un séparateur de milliers. Reformulez, par ex. 20000,500 ou 20000.500.",
      };
    }
    candidate = `${intPart}.${fracPart}`;
  } else if (hasDot) {
    const dotCount = trimmed.split(".").length - 1;
    if (dotCount > 1) {
      return {
        ok: false,
        message: "Format ambigu (plusieurs points) : indiquez seulement les décimales, par ex. 20000.500.",
      };
    }
  }

  if (!CANONICAL.test(candidate)) {
    return {
      ok: false,
      message: "Montant invalide : au plus 12 chiffres entiers et 3 décimales, par ex. 20000.500.",
    };
  }

  return { ok: true, value: candidate };
}
