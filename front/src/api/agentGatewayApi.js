import { fetchJson } from "./client";

export async function listGatewayTools() {
  return fetchJson("/api/v1/agent-gateway/tools", { timeout: 20000 });
}

export async function listGatewayTokens() {
  return fetchJson("/api/v1/agent-gateway/tokens", { timeout: 20000 });
}

export async function createGatewayToken(payload) {
  return fetchJson("/api/v1/agent-gateway/tokens", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 20000,
  });
}

export async function runGatewayJob(payload, idempotencyKey = "") {
  return fetchJson("/api/v1/agent-gateway/run", {
    method: "POST",
    headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    body: JSON.stringify(payload),
    timeout: 20000,
  });
}
