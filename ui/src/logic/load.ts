import type { Bundle, Points, Works } from "../types";

export const SCHEMA_VERSION = "research-signal-radar-bundle/0.1";

/** Throws if the bundle is not one this UI can read, or if a signal points outside the map. */
export function validateBundle(bundle: Bundle, points: Points): void {
  if (bundle.schema_version !== SCHEMA_VERSION) {
    throw new Error(`Unsupported bundle schema "${bundle.schema_version}" (expected ${SCHEMA_VERSION})`);
  }
  if (points.x.length !== points.n) throw new Error("points.json: column lengths do not match n");
  for (const s of bundle.signals) {
    for (const i of s.work_idx) {
      if (!Number.isInteger(i) || i < 0 || i >= points.n) {
        throw new Error(`Signal ${s.id} refers to work index ${i}, outside the map (n = ${points.n})`);
      }
    }
  }
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Cannot load ${url} (HTTP ${response.status}). Run \`uv run radar export\`.`);
  return (await response.json()) as T;
}

export async function loadCore(base = "data"): Promise<{ bundle: Bundle; points: Points }> {
  const [bundle, points] = await Promise.all([getJson<Bundle>(`${base}/bundle.json`), getJson<Points>(`${base}/points.json`)]);
  validateBundle(bundle, points);
  return { bundle, points };
}

export function loadWorks(base = "data"): Promise<Works> {
  return getJson<Works>(`${base}/works.json`);
}
