import { fetchJson } from "./client";

export async function listCommunityStrategies() {
  const payload = await fetchJson("/api/v1/strategies", { timeout: 20000 });
  return payload?.items || [];
}

export async function publishCommunityStrategy(strategy) {
  return fetchJson("/api/v1/strategies", {
    method: "POST",
    body: JSON.stringify(strategy),
    timeout: 20000,
  });
}

export async function forkCommunityStrategy(id) {
  return fetchJson(`/api/v1/strategies/${id}/fork`, {
    method: "POST",
    body: JSON.stringify({}),
    timeout: 20000,
  });
}

export async function favoriteCommunityStrategy(id) {
  return fetchJson(`/api/v1/strategies/${id}/favorite`, {
    method: "POST",
    body: JSON.stringify({}),
    timeout: 20000,
  });
}

export async function listStrategyComments(id) {
  const payload = await fetchJson(`/api/v1/strategies/${id}/comments`, { timeout: 20000 });
  return payload?.items || [];
}

export async function addStrategyComment(id, content) {
  return fetchJson(`/api/v1/strategies/${id}/comments`, {
    method: "POST",
    body: JSON.stringify({ content }),
    timeout: 20000,
  });
}
