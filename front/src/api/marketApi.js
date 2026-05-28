import { fetchJson, toQuery } from "./client";

const numberOrNull = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

export function normalizeSymbol(value) {
  const raw = String(value || "").trim().toUpperCase();
  if (!raw) return "000001.XSHE";
  if (raw.endsWith(".SH")) return raw.replace(".SH", ".XSHG");
  if (raw.endsWith(".SZ")) return raw.replace(".SZ", ".XSHE");
  if (/^\d{6}$/.test(raw)) return `${raw}.${raw.startsWith("6") || raw.startsWith("9") ? "XSHG" : "XSHE"}`;
  return raw;
}

export function normalizeBars(payload) {
  const rows = Array.isArray(payload) ? payload : payload?.bars || payload?.data || payload?.kline || payload?.daily_data || [];
  return rows
    .map((row) => {
      const time = row.time || row.date || row.datetime || row.trading_datetime || row["日期"] || row["时间"];
      const open = numberOrNull(row.open ?? row.o ?? row["开盘"]);
      const high = numberOrNull(row.high ?? row.h ?? row["最高"]);
      const low = numberOrNull(row.low ?? row.l ?? row["最低"]);
      const close = numberOrNull(row.close ?? row.c ?? row["收盘"] ?? row.price);
      if (!time || open === null || high === null || low === null || close === null) return null;
      return {
        time: String(time),
        open,
        high,
        low,
        close,
        volume: numberOrNull(row.volume ?? row.vol ?? row["成交量"]) ?? 0,
        amount: numberOrNull(row.amount ?? row.turnover ?? row["成交额"]),
        ma20: numberOrNull(row.ma20 ?? row.ma_20 ?? row.MA20),
        atr: numberOrNull(row.atr ?? row.ATR),
        atr_upper: numberOrNull(row.atr_upper ?? row.atrUpper),
        atr_lower: numberOrNull(row.atr_lower ?? row.atrLower),
      };
    })
    .filter(Boolean)
    .sort((a, b) => String(a.time).localeCompare(String(b.time)));
}

export function normalizeQuote(payload) {
  if (!payload) return null;
  return {
    symbol: normalizeSymbol(payload.symbol || payload.code),
    name: payload.name || payload.short_name || payload.symbol || "A股",
    price: numberOrNull(payload.price ?? payload.last ?? payload.close),
    change: numberOrNull(payload.change),
    change_pct: numberOrNull(payload.change_pct ?? payload.changePct ?? payload.pct_chg),
    open: numberOrNull(payload.open),
    high: numberOrNull(payload.high),
    low: numberOrNull(payload.low),
    pre_close: numberOrNull(payload.pre_close ?? payload.preClose),
    volume: numberOrNull(payload.volume),
    amount: numberOrNull(payload.amount ?? payload.turnover),
    timestamp: payload.timestamp || payload.time || "",
    source: payload.source || "",
    latency_ms: numberOrNull(payload.latency_ms ?? payload.latencyMs),
  };
}

export async function searchStocks(keyword, options = {}) {
  const query = toQuery({ keyword });
  const payload = await fetchJson(`/api/v1/market/search?${query}`, { timeout: 20000, ...options });
  return payload?.items || [];
}

export async function getMarketBarsPayload(params, options = {}) {
  const query = toQuery({
    symbol: normalizeSymbol(params.symbol),
    period: params.period,
    start_date: params.startDate || params.start_date,
    end_date: params.endDate || params.end_date,
    adjust: params.adjust || "qfq",
  });
  const payload = await fetchJson(`/api/v1/market/bars?${query}`, { timeout: 45000, ...options });
  return {
    bars: normalizeBars(payload),
    meta: {
      source: payload?.source || "",
      latency_ms: numberOrNull(payload?.latency_ms),
      timestamp: payload?.timestamp || "",
      name: payload?.name || "",
      symbol: payload?.symbol || normalizeSymbol(params.symbol),
      period: payload?.period || params.period,
      requested_start: payload?.requested_start || params.startDate || params.start_date || "",
      requested_end: payload?.requested_end || params.endDate || params.end_date || "",
      actual_start: payload?.actual_start || "",
      actual_end: payload?.actual_end || "",
      bars_count: numberOrNull(payload?.bars_count),
      data_warning: payload?.data_warning || "",
    },
  };
}

export async function getMarketBars(params, options = {}) {
  const payload = await getMarketBarsPayload(params, options);
  return payload.bars;
}

export async function getQuote(symbol, options = {}) {
  const query = toQuery({ symbol: normalizeSymbol(symbol) });
  const payload = await fetchJson(`/api/v1/market/quote?${query}`, { timeout: 20000, ...options });
  return normalizeQuote(payload);
}
