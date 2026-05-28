import { fetchJson } from "./client";

export async function getUserSettings() {
  return fetchJson("/api/v1/settings/user", { timeout: 20000 });
}

export async function saveUserSettings(payload) {
  return fetchJson("/api/v1/settings/user", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 20000,
  });
}

export async function listModelProviders() {
  return fetchJson("/api/v1/settings/model-providers", { timeout: 20000 });
}

export async function saveModelProvider(payload) {
  return fetchJson("/api/v1/settings/model-providers", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 20000,
  });
}

export async function testModelProvider(payload) {
  return fetchJson("/api/v1/settings/model-providers/test", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 30000,
  });
}
