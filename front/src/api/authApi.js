import { fetchJson } from "./client";

export async function register(payload) {
  return fetchJson("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 20000,
  });
}

export async function login(payload) {
  return fetchJson("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: 20000,
  });
}

export async function me() {
  return fetchJson("/api/v1/auth/me", { timeout: 20000 });
}

export async function logout() {
  return fetchJson("/api/v1/auth/logout", {
    method: "POST",
    body: JSON.stringify({}),
    timeout: 20000,
  });
}
