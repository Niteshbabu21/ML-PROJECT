import type { PropertyFeatures } from "../types/api";

const KEY = "propval:last-property";

/** Cross-page convenience: the last property the user valued is offered
 * as a prefill on the Explainability, Risk and Tokenisation pages. */
export function saveLastProperty(p: PropertyFeatures): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* storage unavailable — prefill is optional */
  }
}

export function loadLastProperty(): PropertyFeatures | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as PropertyFeatures) : null;
  } catch {
    return null;
  }
}
