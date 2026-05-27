export const API_BASE = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export function toQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, value);
    }
  });
  return search.toString();
}

export async function fetchJson(path, options = {}) {
  const timeout = options.timeout ?? 30000;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeout);
  const signal = options.signal || controller.signal;
  try {
    const { signal: _ignoredSignal, timeout: _ignoredTimeout, ...fetchOptions } = options;
    const response = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers: {
        "Content-Type": "application/json",
        ...(localStorage.getItem("lobster_token") ? { Authorization: `Bearer ${localStorage.getItem("lobster_token")}` } : {}),
        ...(options.headers || {}),
      },
      signal,
    });
    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { detail: text };
      }
    }
    if (!response.ok) {
      const detail = payload?.detail || payload?.message || response.statusText;
      throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg || item.detail).join("; ") : detail);
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(options.signal?.aborted ? `请求已取消：${path}` : `网络请求超时：${path}`);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}
