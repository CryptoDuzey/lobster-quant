import { fetchJson, toQuery } from "./client";
import { normalizeSymbol } from "./marketApi";

function normalizeNewsItem(item = {}) {
  return {
    title: item.title || item.headline || "未命名消息",
    source: item.source || "未知来源",
    time: item.time || item.datetime || item.timestamp || "",
    url: /^https?:\/\//.test(item.url || "") ? item.url : "",
    summary: item.summary || item.content || item.title || "",
    related_symbols: item.related_symbols || item.symbols || [],
  };
}

export async function getStockNews(symbol, options = {}) {
  const query = toQuery({ symbol: normalizeSymbol(symbol), limit: 12 });
  const payload = await fetchJson(`/api/v1/news/stock?${query}`, { timeout: 30000, ...options });
  return {
    items: (payload?.items || []).map(normalizeNewsItem),
    source: payload?.source || "",
    latency_ms: payload?.latency_ms ?? null,
    timestamp: payload?.timestamp || "",
  };
}

export async function getMarketNews(keyword = "", options = {}) {
  const query = toQuery({ keyword, limit: 12 });
  const payload = await fetchJson(`/api/v1/news/market?${query}`, { timeout: 30000, ...options });
  return {
    items: (payload?.items || []).map(normalizeNewsItem),
    source: payload?.source || "",
    latency_ms: payload?.latency_ms ?? null,
    timestamp: payload?.timestamp || "",
  };
}
