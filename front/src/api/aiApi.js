import { fetchJson } from "./client";
import { normalizeSymbol } from "./marketApi";

export async function auditStrategy(payload) {
  return fetchJson("/api/v1/ai/backtest/audit", {
    method: "POST",
    body: JSON.stringify({
      symbol: normalizeSymbol(payload.symbol),
      name: payload.name || "",
      strategy_name: payload.strategy_name || payload.strategyName || "",
      period: payload.period || "day",
      strategy: payload.strategy,
      metrics: payload.metrics || {},
      trades: payload.trades || [],
      market_context: payload.market_context || payload.marketContext || {},
    }),
    timeout: 60000,
  });
}

export async function generateStrategy(payload) {
  return fetchJson("/api/v1/ai/strategy/parse", {
    method: "POST",
    body: JSON.stringify({
      symbol: normalizeSymbol(payload.symbol),
      period: payload.period || "day",
      start_date: payload.startDate || payload.start_date,
      end_date: payload.endDate || payload.end_date,
      user_input: payload.idea || payload.user_input,
      framework: payload.framework || {},
    }),
    timeout: 60000,
  });
}

export async function aiStockSearch(payload) {
  return fetchJson("/api/v1/ai/stock-search", {
    method: "POST",
    body: JSON.stringify({
      query: payload.query,
      limit: payload.limit || 20,
    }),
    timeout: 60000,
  });
}

export async function analyzeStock(payload) {
  return fetchJson("/api/v1/ai/stock-analysis", {
    method: "POST",
    body: JSON.stringify({
      symbol: normalizeSymbol(payload.symbol),
      name: payload.name || "",
      question: payload.question || "",
      period: payload.period || "1m",
      selected_range: payload.selectedRange || payload.selected_range || null,
      quote: payload.quote || {},
      bars: payload.bars || [],
      news: payload.news || [],
    }),
    timeout: 60000,
  });
}

export async function debugStrategy(payload) {
  return fetchJson("/api/v1/ai/strategy/debug", {
    method: "POST",
    body: JSON.stringify({
      strategy_json: payload.strategyJson || payload.strategy_json || {},
      generated_code: payload.generatedCode || payload.generated_code || "",
      error_message: payload.errorMessage || payload.error_message || "",
      runtime_context: payload.runtimeContext || payload.runtime_context || {},
    }),
    timeout: 60000,
  });
}
