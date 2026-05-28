import { fetchJson } from "./client";
import { normalizeSymbol } from "./marketApi";

export async function runMarketWatchCommittee(payload) {
  const query = typeof payload.query === "string"
    ? payload.query
    : typeof payload.question === "string"
      ? payload.question
      : String(payload.question || payload.query || "");
  return fetchJson("/api/v1/agents/assistant-chat", {
    method: "POST",
    body: JSON.stringify({
      session_id: payload.sessionId || payload.session_id || "radar_default",
      symbol: normalizeSymbol(payload.symbol),
      name: payload.name || "",
      query,
      period: payload.period || "1m",
      context: payload.context || {
        page: "radar",
        selected_range: payload.selectedRange || null,
        current_timeframe: payload.period || "1m",
      },
      quote: payload.quote || {},
      bars: payload.bars || [],
      news: payload.news || [],
      metrics: payload.metrics || {},
      trades: payload.trades || [],
      data_source: payload.data_source || payload.dataSource || "",
      messages: payload.messages || [],
      target_agents: payload.targetAgents || payload.target_agents || [],
    }),
    timeout: 60000,
  });
}

export async function runFinancialAgent(payload) {
  const query = typeof payload.query === "string"
    ? payload.query
    : typeof payload.question === "string"
      ? payload.question
      : String(payload.question || payload.query || "");
  return fetchJson("/api/v1/agents/financial-agent-chat", {
    method: "POST",
    body: JSON.stringify({
      session_id: payload.sessionId || payload.session_id || "financial_agent_default",
      query,
      page: payload.page || "",
      context: payload.context || {},
      messages: payload.messages || [],
    }),
    timeout: 120000,
  });
}

export async function agentStrategyGenerate(payload) {
  return fetchJson("/api/v1/agents/strategy-generate", {
    method: "POST",
    body: JSON.stringify({
      symbol: normalizeSymbol(payload.symbol),
      period: payload.period || "day",
      start_date: payload.startDate || payload.start_date,
      end_date: payload.endDate || payload.end_date,
      user_input: payload.idea || payload.user_input || "",
      framework: payload.framework || {},
      buy_idea: payload.buyIdea || payload.buy_idea || "",
      sell_idea: payload.sellIdea || payload.sell_idea || "",
      risk_idea: payload.riskIdea || payload.risk_idea || "",
    }),
    timeout: 60000,
  });
}

export async function agentStrategyDebug(payload) {
  return fetchJson("/api/v1/agents/strategy-debug", {
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

export async function agentBacktestAudit(payload) {
  return fetchJson("/api/v1/agents/backtest-audit", {
    method: "POST",
    body: JSON.stringify({
      symbol: normalizeSymbol(payload.symbol),
      name: payload.name || "",
      strategy_name: payload.strategyName || payload.strategy_name || "",
      period: payload.period || "day",
      strategy_json: payload.strategyJson || payload.strategy_json || {},
      metrics: payload.metrics || {},
      trades: payload.trades || [],
      bars: payload.bars || [],
    }),
    timeout: 60000,
  });
}

export async function strategyChat(payload) {
  return fetchJson("/api/v1/agents/strategy-chat", {
    method: "POST",
    body: JSON.stringify({
      messages: payload.messages || [],
      slots: payload.slots || {},
      use_defaults: Boolean(payload.useDefaults),
    }),
    timeout: 60000,
  });
}

export async function listAgentTools() {
  return fetchJson("/api/v1/agents/tools", { timeout: 20000 });
}

export async function listAgentAuditLogs(limit = 100) {
  return fetchJson(`/api/v1/agents/audit-logs?limit=${limit}`, { timeout: 20000 });
}
