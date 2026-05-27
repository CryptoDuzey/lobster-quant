import { fetchJson } from "./client";
import { normalizeBars, normalizeSymbol } from "./marketApi";

const numberOrNull = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

function normalizeMetrics(payload = {}) {
  const source = payload.metrics || payload.performance || payload.summary || payload.statistics || {};
  return {
    total_return: numberOrNull(source.total_return ?? source.totalReturn ?? source.total_returns),
    annual_return: numberOrNull(source.annual_return ?? source.annualReturn ?? source.annualized_returns),
    max_drawdown: numberOrNull(source.max_drawdown ?? source.maxDrawdown),
    sharpe: numberOrNull(source.sharpe ?? source.sharpe_ratio),
    alpha: numberOrNull(source.alpha),
    beta: numberOrNull(source.beta),
    volatility: numberOrNull(source.volatility),
    win_rate: numberOrNull(source.win_rate ?? source.winRate),
    trade_count: numberOrNull(source.trade_count ?? source.tradeCount),
    turnover: numberOrNull(source.turnover),
  };
}

function normalizeTrades(payload = {}, fallbackSymbol) {
  const rows = payload.trades || payload.ledger || payload.trade_records || [];
  return rows.map((row, index) => {
    const rawDirection = String(row.direction || row.action || row.side || "").toUpperCase();
    const direction = rawDirection.includes("SELL") ? "SELL" : rawDirection.includes("BUY") ? "BUY" : rawDirection || "UNKNOWN_DIRECTION";
    return {
      id: row.id || row.order_id || `${row.time || row.date || index}-${index}`,
      time: row.time || row.date || row.datetime || row.trading_datetime || "",
      date: row.date || String(row.time || row.datetime || row.trading_datetime || "").slice(0, 10),
      execution_time: row.execution_time || row.time || row.datetime || row.trading_datetime || "",
      execution_phase: row.execution_phase || "",
      rqalpha_time: row.rqalpha_time || "",
      time_source: row.time_source || "",
      time_note: row.time_note || "",
      execution_precision: row.execution_precision || "",
      execution_label: row.execution_label || "",
      price_source: row.price_source || "",
      signal_source: row.signal_source || "",
      is_precise_intraday: Boolean(row.is_precise_intraday),
      symbol: normalizeSymbol(row.symbol || row.code || fallbackSymbol),
      name: row.name || row.name_cn || "",
      direction,
      price: numberOrNull(row.price ?? row.last_price),
      quantity: Number(row.quantity ?? row.qty ?? row.amount ?? row.last_quantity ?? 0),
      amount: numberOrNull(row.amount),
      reason: row.reason || row.description || "",
      fee: numberOrNull(row.fee ?? row.transaction_cost),
      slippage: numberOrNull(row.slippage),
      status: row.status || "已成交",
      audit: row.audit || row.ai_audit || (direction === "BUY" ? "买入信号确认，已通过 A 股 100 股整手校验" : "卖出信号确认，已通过 A 股 T+1 可卖校验"),
    };
  });
}

function normalizeCurves(payload = {}) {
  const curves = payload.curves || {};
  if (Array.isArray(curves.strategy_curve) || Array.isArray(curves.drawdown_curve)) return curves;
  const equity = Array.isArray(curves.equity_curve) ? curves.equity_curve : [];
  return {
    equity_curve: equity,
    strategy_curve: equity
      .filter((item) => Number.isFinite(Number(item.return)))
      .map((item) => ({ time: item.time, value: Number(item.return) })),
    benchmark_curve: equity
      .filter((item) => Number.isFinite(Number(item.benchmark_return)))
      .map((item) => ({ time: item.time, value: Number(item.benchmark_return) })),
    drawdown_curve: equity
      .filter((item) => Number.isFinite(Number(item.drawdown)))
      .map((item) => ({ time: item.time, value: Number(item.drawdown) })),
  };
}

export function normalizeBacktestResponse(payload = {}, fallbackSymbol = "000001.XSHE") {
  const barsSource = payload.bars || payload.kline || payload.daily_data || payload.chart_data || [];
  return {
    success: payload.success !== false,
    backtest_id: payload.backtest_id || "",
    symbol: normalizeSymbol(payload.symbol || fallbackSymbol),
    name: payload.name || "",
    period: payload.period || "",
    strategy_name: payload.strategy_name || "",
    time_range: payload.time_range || null,
    data_info: payload.data_info || null,
    engine_info: payload.engine_info || null,
    metrics: normalizeMetrics(payload),
    trades: normalizeTrades(payload, fallbackSymbol),
    bars: normalizeBars(barsSource),
    curves: normalizeCurves(payload),
    warnings: payload.warnings || [],
    trust_audit: payload.trust_audit || null,
    strategy_json: payload.strategy_json || null,
    strategy_hash: payload.strategy_hash || "",
    code_hash: payload.code_hash || payload.strategy_code_hash || "",
    config_hash: payload.config_hash || payload.config_snapshot_hash || "",
    strategy_code_hash: payload.strategy_code_hash || "",
    config_snapshot_hash: payload.config_snapshot_hash || "",
    data_hash: payload.data_hash || "",
    debug: payload.debug || {},
    ai_audit: payload.ai_audit || payload.audit || null,
    raw: payload,
  };
}

export function validateBacktestResult(result) {
  if (!result) throw new Error("回测结果为空");
  if (result.success === false) throw new Error(result.message || "本次回测失败");
  if (result.data_info?.is_mock) throw new Error("当前结果包含 mock 数据，禁止展示为正式回测");
  const blockingErrors = result.trust_audit?.blocking_errors || result.raw?.trust_audit?.blocking_errors || [];
  if (blockingErrors.length) {
    throw new Error(`本次回测结果不可信，已停止展示。原因：${blockingErrors[0]}`);
  }
  if (!result.strategy_hash && !result.raw?.strategy_hash) throw new Error("缺少策略 Hash，无法确认策略是否真实执行");
  const strategyCurve = result.curves?.strategy_curve;
  const drawdownCurve = result.curves?.drawdown_curve;
  if (!Array.isArray(strategyCurve) || strategyCurve.length < 2) {
    throw new Error("策略收益曲线缺失");
  }
  if (!Array.isArray(drawdownCurve) || drawdownCurve.length < 2) {
    throw new Error("回撤曲线缺失");
  }
  return true;
}

export async function listBacktestRuns(limit = 20) {
  const payload = await fetchJson(`/api/v1/backtest/runs?limit=${limit}`, { timeout: 20000 });
  return payload?.items || [];
}

export async function getBacktestRun(backtestId) {
  const payload = await fetchJson(`/api/v1/backtest/runs/${encodeURIComponent(backtestId)}`, { timeout: 20000 });
  return normalizeBacktestResponse(payload, payload?.symbol || "000001.XSHE");
}

export async function renameBacktestRun(backtestId, strategyName) {
  return fetchJson(`/api/v1/backtest/runs/${encodeURIComponent(backtestId)}`, {
    method: "PATCH",
    body: JSON.stringify({ strategy_name: strategyName }),
    timeout: 20000,
  });
}

export async function deleteBacktestRun(backtestId) {
  return fetchJson(`/api/v1/backtest/runs/${encodeURIComponent(backtestId)}`, {
    method: "DELETE",
    timeout: 20000,
  });
}

export async function runBacktest(payload) {
  const body = {
    mode: payload.mode || "single_stock",
    symbol: normalizeSymbol(payload.symbol),
    start_date: payload.startDate || payload.start_date,
    end_date: payload.endDate || payload.end_date,
    strategy_name: payload.strategyName || payload.strategy_name || "龙虾量化策略",
    rules: payload.rules,
    params: payload.params,
    buy_idea: payload.buyIdea || payload.buy_idea,
    sell_idea: payload.sellIdea || payload.sell_idea,
    risk_idea: payload.riskIdea || payload.risk_idea,
    period: payload.period,
    execution_time: payload.executionTime || payload.execution_time || payload.params?.execution_time || null,
    atr_period: 14,
    stop_loss_multiplier: 2,
  };
  const result = await fetchJson("/api/v1/backtest/run", {
    method: "POST",
    body: JSON.stringify(body),
    timeout: 360000,
  });
  if (result?.success === false) {
    const error = new Error(result.message || "本次回测失败");
    error.payload = result;
    throw error;
  }
  const normalized = normalizeBacktestResponse(result, body.symbol);
  validateBacktestResult(normalized);
  return normalized;
}
