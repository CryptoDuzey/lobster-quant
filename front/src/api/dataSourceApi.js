import { fetchJson } from "./client";

export async function listDataSources() {
  return fetchJson("/api/v1/data-sources", { timeout: 20000 });
}
