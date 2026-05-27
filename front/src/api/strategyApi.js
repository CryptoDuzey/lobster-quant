import { fetchJson } from "./client";
import { normalizeSymbol } from "./marketApi";

export async function generateStrategyCode(payload) {
  return fetchJson("/api/v1/strategy/generate-code", {
    method: "POST",
    body: JSON.stringify({
      mode: payload.mode || "single_stock",
      symbol: normalizeSymbol(payload.symbol),
      period: payload.period || "day",
      start_date: payload.startDate || payload.start_date,
      end_date: payload.endDate || payload.end_date,
      strategy_name: payload.strategyName || payload.strategy_name || "龙虾量化策略",
      rules: payload.rules || {},
      params: payload.params || {},
      buy_idea: payload.buyIdea || payload.buy_idea,
      sell_idea: payload.sellIdea || payload.sell_idea,
      risk_idea: payload.riskIdea || payload.risk_idea,
    }),
    timeout: 60000,
  });
}
