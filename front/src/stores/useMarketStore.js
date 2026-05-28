import { reactive } from "vue";
import {
  agentBacktestAudit,
  agentStrategyDebug,
  agentStrategyGenerate,
  runFinancialAgent,
  runMarketWatchCommittee,
} from "../api/agentsApi";
import { aiStockSearch } from "../api/aiApi";
import { runBacktest as requestBacktest } from "../api/backtestApi";
import {
  favoriteCommunityStrategy,
  forkCommunityStrategy,
  listCommunityStrategies,
  publishCommunityStrategy,
} from "../api/communityApi";
import { getMarketBarsPayload, getQuote, normalizeSymbol, searchStocks } from "../api/marketApi";
import { getStockNews } from "../api/newsApi";
import { generateStrategyCode } from "../api/strategyApi";

const STORAGE_KEY = "lobster_quant_saved_strategies";
const WATCHLIST_KEY = "lobster_quant_watchlist";
const QUOTE_INTERVAL = 3000;
const BAR_INTERVAL = 5000;
const NEWS_INTERVAL = 30000;

const DEFAULT_POOLS = [
  {
    id: "watchlist",
    name: "自选股",
    description: "高频盯盘股票",
    items: [
      { symbol: "000001.XSHE", code: "000001", name: "平安银行", exchange: "深交所", change_pct: 0, price: null, heat: 72 },
      { symbol: "601318.XSHG", code: "601318", name: "中国平安", exchange: "上交所", change_pct: 0, price: null, heat: 78 },
      { symbol: "600036.XSHG", code: "600036", name: "招商银行", exchange: "上交所", change_pct: 0, price: null, heat: 66 },
    ],
  },
  {
    id: "central",
    name: "中字头央企",
    description: "央企与中特估观察池",
    items: [
      { symbol: "601398.XSHG", code: "601398", name: "工商银行", exchange: "上交所", change_pct: 0, price: null, heat: 82 },
      { symbol: "601857.XSHG", code: "601857", name: "中国石油", exchange: "上交所", change_pct: 0, price: null, heat: 76 },
      { symbol: "600028.XSHG", code: "600028", name: "中国石化", exchange: "上交所", change_pct: 0, price: null, heat: 70 },
      { symbol: "601888.XSHG", code: "601888", name: "中国中免", exchange: "上交所", change_pct: 0, price: null, heat: 64 },
    ],
  },
  {
    id: "semiconductor",
    name: "半导体",
    description: "芯片国产替代方向",
    items: [
      { symbol: "688981.XSHG", code: "688981", name: "中芯国际", exchange: "上交所", change_pct: 0, price: null, heat: 84 },
      { symbol: "603986.XSHG", code: "603986", name: "兆易创新", exchange: "上交所", change_pct: 0, price: null, heat: 69 },
      { symbol: "002371.XSHE", code: "002371", name: "北方华创", exchange: "深交所", change_pct: 0, price: null, heat: 80 },
    ],
  },
  {
    id: "new-energy",
    name: "新能源",
    description: "电池、整车与光伏",
    items: [
      { symbol: "300750.XSHE", code: "300750", name: "宁德时代", exchange: "深交所", change_pct: 0, price: null, heat: 88 },
      { symbol: "002594.XSHE", code: "002594", name: "比亚迪", exchange: "深交所", change_pct: 0, price: null, heat: 86 },
      { symbol: "601012.XSHG", code: "601012", name: "隆基绿能", exchange: "上交所", change_pct: 0, price: null, heat: 62 },
    ],
  },
  {
    id: "robot",
    name: "机器人",
    description: "自动化与机器人链",
    items: [
      { symbol: "300124.XSHE", code: "300124", name: "汇川技术", exchange: "深交所", change_pct: 0, price: null, heat: 82 },
      { symbol: "002230.XSHE", code: "002230", name: "科大讯飞", exchange: "深交所", change_pct: 0, price: null, heat: 74 },
      { symbol: "002747.XSHE", code: "002747", name: "埃斯顿", exchange: "深交所", change_pct: 0, price: null, heat: 68 },
    ],
  },
];

function safeReadJson(key, fallback) {
  try {
    if (typeof window === "undefined") return fallback;
    const value = window.localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

function safeWriteJson(key, value) {
  try {
    if (typeof window !== "undefined") window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Local storage is a convenience cache only; failure should not break行情.
  }
}

function normalizedStockItem(item, fallbackName = "") {
  const symbol = normalizeSymbol(item?.symbol || item?.code || "000001.XSHE");
  return {
    symbol,
    code: item?.code || symbol.slice(0, 6),
    name: item?.name || item?.name_cn || fallbackName || symbol,
    exchange: item?.exchange || (symbol.endsWith(".XSHG") ? "上交所" : "深交所"),
    change_pct: item?.change_pct ?? 0,
    price: item?.price ?? null,
    amount: item?.amount ?? null,
    heat: item?.heat ?? 70,
  };
}

function initialStockPools() {
  const pools = DEFAULT_POOLS.map((pool) => ({
    ...pool,
    items: pool.items.map((item) => ({ ...item })),
  }));
  const savedWatchlist = safeReadJson(WATCHLIST_KEY, null);
  if (Array.isArray(savedWatchlist)) {
    pools[0] = {
      ...pools[0],
      items: savedWatchlist.map((item) => normalizedStockItem(item)),
    };
  }
  return pools;
}

const state = reactive({
  currentPage: "radar",

  symbol: "000001.XSHE",
  stockName: "平安银行",
  period: "day",
  startDate: "2025-01-01",
  endDate: "2026-05-23",

  quote: null,
  bars: [],
  trades: [],
  metrics: null,
  aiAudit: null,
  backtestResult: null,

  news: [],
  stockPools: initialStockPools(),
  selectedPoolId: "watchlist",
  aiSearchResults: [],
  recentStocks: [],
  dataSource: "",
  latencyMs: null,
  updatedAt: "",
  marketRequestedStart: "",
  marketRequestedEnd: "",
  marketActualStart: "",
  marketActualEnd: "",
  marketBarsCount: 0,
  marketDataWarning: "",

  logs: [],
  error: null,
  fallbackMode: false,

  aiStockQuestion: "这只股票最近走势怎么样？",
  aiStockAnalysis: null,
  agentCommittee: null,
  committeeMessages: [
    {
      role: "assistant",
      content: "可以直接问当前股票。投研委员会会结合真实行情、K线、消息面和风险信号回答；数据不足时会明确说明。",
    },
  ],
  financialAgentQuestion: "",
  financialAgentResult: null,
  financialAgentMessages: [
    {
      role: "assistant",
      content: "我是金融 Agent，可以自由聊市场、策略、回测、风险、金融人物和投资框架；涉及具体行情和数据时，我会说明依据和不确定性。",
    },
  ],
  aiAssistantOpen: false,
  activeAssistantMode: "market",
  selectedChartContext: null,

  strategyInput: "帮我创建一个均线突破策略，股价站上20日均线并且成交量放大时买入，跌破20日均线时卖出，最大亏损8%止损。",
  strategyJson: null,
  generatedCode: "",
  debugHistory: [],
  buyIdea: "close > ma20 and atr > atr_ma20",
  sellIdea: "close < ma20",
  riskIdea: "drawdown > 0.08",

  communityStrategies: [],
  savedStrategies: [],
  lastBacktestAt: null,

  loadingMarket: false,
  loadingBacktest: false,
  loadingAI: false,
  loadingSearch: false,
  loadingQuote: false,
  loadingBars: false,
  loadingNews: false,
  loadingAIAnalysis: false,
  loadingStrategyParse: false,
  loadingCode: false,
  loadingDebug: false,
  loadingCommunity: false,
  pollingActive: false,
});

let quoteTimer = null;
let barTimer = null;
let newsTimer = null;
let quoteController = null;
let barsController = null;
let newsController = null;

function nowTime() {
  const now = new Date();
  return [now.getHours(), now.getMinutes(), now.getSeconds()].map((item) => String(item).padStart(2, "0")).join(":");
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function pushLog(level, message) {
  state.logs.push({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    time: nowTime(),
    level,
    message,
  });
  if (state.logs.length > 140) state.logs.splice(0, state.logs.length - 140);
}

function translateError(message = "") {
  const text = String(message || "");
  if (text.includes("请求已取消")) return "";
  if (text.includes("Failed to fetch") || text.includes("NetworkError")) {
    return "后端服务未启动，请确认 FastAPI 已运行在 127.0.0.1:8000";
  }
  if (text.includes("missing") && text.includes("KEY")) {
    return "DeepSeek API Key 未配置，请检查后端 .env 文件";
  }
  if (text.includes("timeout") || text.includes("超时")) {
    return "网络请求超时，请稍后重试";
  }
  if (text.includes("No market bars") || text.includes("暂无行情")) {
    return "当前周期暂无行情数据，请切换到日线或更换股票";
  }
  if (text.includes("未找到相关股票")) {
    return "未找到相关股票，请尝试输入股票代码或完整股票名称";
  }
  if (text.includes("422")) {
    return "请求参数不完整，请检查股票、日期和策略规则";
  }
  return text || "系统发生未知错误";
}

function setError(message) {
  const normalized = translateError(message);
  if (!normalized) return;
  state.error = normalized;
  pushLog("错误", normalized);
}

function clearError() {
  state.error = null;
}

function setSymbol(symbol) {
  state.symbol = normalizeSymbol(symbol);
}

function addRecentStock(item) {
  const stock = {
    symbol: normalizeSymbol(item.symbol || item.code),
    code: item.code || normalizeSymbol(item.symbol || item.code).slice(0, 6),
    name: item.name || item.name_cn || state.stockName,
    exchange: item.exchange || (normalizeSymbol(item.symbol || item.code).endsWith(".XSHG") ? "上交所" : "深交所"),
  };
  state.recentStocks = [stock, ...state.recentStocks.filter((row) => row.symbol !== stock.symbol)].slice(0, 8);
}

function setStock(item) {
  state.symbol = normalizeSymbol(item.symbol || item.code);
  state.stockName = item.name || item.name_cn || state.stockName;
  addRecentStock(item);
}

function setPeriod(period) {
  state.period = period;
}

function periodLabel(period) {
  return {
    "1m": "1分钟",
    "5m": "5分钟",
    "15m": "15分钟",
    "30m": "30分钟",
    "60m": "60分钟",
    day: "日线",
  }[period] || period;
}

function deriveQuoteFromBars() {
  const latest = state.bars[state.bars.length - 1];
  if (!latest) return null;
  const previous = state.bars[state.bars.length - 2] || latest;
  const change = latest.close - previous.close;
  const changePct = previous.close ? (change / previous.close) * 100 : 0;
  return {
    symbol: state.symbol,
    name: state.stockName || state.quote?.name || state.symbol,
    price: latest.close,
    change,
    change_pct: changePct,
    open: latest.open,
    high: latest.high,
    low: latest.low,
    pre_close: previous.close,
    volume: latest.volume,
    amount: latest.amount,
    timestamp: latest.time,
    source: state.dataSource,
    latency_ms: state.latencyMs,
  };
}

const MINUTE_HISTORY_DAYS = {
  "1m": 365,
  "5m": 365,
  "15m": 365,
  "30m": 365,
  "60m": 365,
};

const MINUTE_REFRESH_DAYS = {
  "1m": 2,
  "5m": 3,
  "15m": 7,
  "30m": 10,
  "60m": 20,
};

function dateBeforeEnd(days) {
  const end = new Date(`${state.endDate || new Date().toISOString().slice(0, 10)}T00:00:00`);
  if (Number.isNaN(end.getTime())) return state.startDate;
  end.setDate(end.getDate() - days);
  const requestedStart = new Date(`${state.startDate || "2025-01-01"}T00:00:00`);
  if (!Number.isNaN(requestedStart.getTime()) && end < requestedStart) return state.startDate;
  return end.toISOString().slice(0, 10);
}

function marketStartDate({ refresh = false } = {}) {
  if (state.period === "day") return state.startDate;
  const days = refresh
    ? (MINUTE_REFRESH_DAYS[state.period] || 7)
    : (MINUTE_HISTORY_DAYS[state.period] || 60);
  return dateBeforeEnd(days);
}

function mergeBarsByTime(existing = [], incoming = []) {
  const map = new Map();
  [...existing, ...incoming].forEach((bar) => {
    if (bar?.time) map.set(String(bar.time), bar);
  });
  return Array.from(map.values()).sort((a, b) => String(a.time).localeCompare(String(b.time)));
}

function updateMarketMeta(meta = {}) {
  state.dataSource = meta.source || state.quote?.source || state.dataSource;
  state.latencyMs = meta.latency_ms ?? state.quote?.latency_ms ?? state.latencyMs;
  state.updatedAt = meta.timestamp || state.quote?.timestamp || state.updatedAt;
  state.marketRequestedStart = meta.requested_start || state.marketRequestedStart;
  state.marketRequestedEnd = meta.requested_end || state.marketRequestedEnd;
  state.marketActualStart = meta.actual_start || state.marketActualStart;
  state.marketActualEnd = meta.actual_end || state.marketActualEnd;
  state.marketBarsCount = meta.bars_count ?? state.marketBarsCount;
  state.marketDataWarning = meta.data_warning || "";
  if (meta.name) state.stockName = meta.name;
}

function selectedPool() {
  if (state.selectedPoolId === "ai-search") {
    return {
      id: "ai-search",
      name: "AI 搜索结果",
      description: "由语义搜索生成的候选股票池",
      items: state.aiSearchResults,
    };
  }
  if (state.selectedPoolId === "recent") {
    return {
      id: "recent",
      name: "最近查看",
      description: "最近切换过的股票",
      items: state.recentStocks,
    };
  }
  return state.stockPools.find((pool) => pool.id === state.selectedPoolId) || state.stockPools[0];
}

function watchlistPool() {
  return state.stockPools.find((pool) => pool.id === "watchlist");
}

function persistWatchlist() {
  const pool = watchlistPool();
  safeWriteJson(WATCHLIST_KEY, pool?.items || []);
}

function isInWatchlist(symbol = state.symbol) {
  const normalized = normalizeSymbol(symbol);
  return Boolean(watchlistPool()?.items?.some((item) => normalizeSymbol(item.symbol) === normalized));
}

function addToWatchlist(item = {}) {
  const pool = watchlistPool();
  if (!pool) return false;
  const stock = normalizedStockItem(
    {
      symbol: item.symbol || state.symbol,
      code: item.code,
      name: item.name || item.name_cn || state.stockName,
      exchange: item.exchange,
      change_pct: item.change_pct ?? state.quote?.change_pct,
      price: item.price ?? state.quote?.price,
      amount: item.amount ?? state.quote?.amount,
      heat: item.heat,
    },
    state.stockName,
  );
  if (pool.items.some((row) => normalizeSymbol(row.symbol) === stock.symbol)) return false;
  pool.items.unshift(stock);
  persistWatchlist();
  pushLog("系统", `已加入自选股：${stock.name}`);
  return true;
}

function removeFromWatchlist(symbol = state.symbol) {
  const pool = watchlistPool();
  if (!pool) return false;
  const normalized = normalizeSymbol(symbol);
  const before = pool.items.length;
  pool.items = pool.items.filter((item) => normalizeSymbol(item.symbol) !== normalized);
  if (pool.items.length === before) return false;
  persistWatchlist();
  pushLog("系统", `已从自选股移除：${normalized}`);
  return true;
}

function toggleWatchlist(item = {}) {
  const symbol = normalizeSymbol(item.symbol || state.symbol);
  if (isInWatchlist(symbol)) return removeFromWatchlist(symbol);
  return addToWatchlist(item);
}

function maskSecretText(text = "") {
  return String(text || "").replace(/sk-[A-Za-z0-9_-]{12,}/g, (value) => `${value.slice(0, 6)}****${value.slice(-4)}`);
}

function openAiAssistant(question = "", context = null, mode = null) {
  const targetMode = mode || (state.currentPage === "radar" ? "market" : "financial");
  state.activeAssistantMode = targetMode;
  if (context) state.selectedChartContext = context;
  if (question) {
    if (targetMode === "market") state.aiStockQuestion = question;
    else state.financialAgentQuestion = question;
  }
  state.aiAssistantOpen = true;
}

function closeAiAssistant() {
  state.aiAssistantOpen = false;
}

function selectPool(poolId) {
  state.selectedPoolId = poolId;
  pushLog("系统", `切换股票池：${selectedPool().name}`);
}

async function searchStock(keyword, options = {}) {
  state.loadingSearch = true;
  pushLog("数据", `正在搜索股票：${keyword}`);
  try {
    const items = await searchStocks(keyword, options);
    if (!items.length) throw new Error("未找到相关股票，请尝试输入股票代码或完整股票名称");
    return items;
  } catch (error) {
    setError(error.message);
    return [];
  } finally {
    state.loadingSearch = false;
  }
}

async function searchStockByAI(query) {
  state.loadingSearch = true;
  pushLog("AI", `正在进行 AI 股票搜索：${query}`);
  try {
    const result = await aiStockSearch({ query, limit: 20 });
    state.aiSearchResults = (result.items || []).map((item) => ({
      ...item,
      symbol: normalizeSymbol(item.symbol || item.code),
      change_pct: item.change_pct ?? 0,
      price: item.price ?? null,
      heat: item.heat ?? 70,
    }));
    state.selectedPoolId = "ai-search";
    pushLog("完成", `AI 搜索返回 ${state.aiSearchResults.length} 只候选股票`);
    if (result.notice) pushLog("系统", result.notice);
    return state.aiSearchResults;
  } catch (error) {
    setError(`AI 股票搜索失败：${error.message}`);
    return [];
  } finally {
    state.loadingSearch = false;
  }
}

async function refreshQuote() {
  quoteController?.abort();
  quoteController = new AbortController();
  state.loadingQuote = true;
  try {
    const quote = await getQuote(state.symbol, { signal: quoteController.signal, timeout: 12000 });
    if (quote) {
      state.quote = quote;
      state.stockName = quote.name || state.stockName;
      updateMarketMeta(quote);
      pushLog("行情", `最新价格更新为 ${formatPrice(quote.price)}`);
    }
  } catch (error) {
    if (!String(error.message).includes("请求已取消")) {
      pushLog("错误", `行情快照刷新失败：${translateError(error.message)}`);
    }
  } finally {
    state.loadingQuote = false;
  }
}

async function refreshLatestBar() {
  if (state.period === "day") return;
  barsController?.abort();
  barsController = new AbortController();
  state.loadingBars = true;
  try {
    const result = await getMarketBarsPayload({
      symbol: state.symbol,
      period: state.period,
      startDate: marketStartDate({ refresh: true }),
      endDate: state.endDate,
      adjust: "qfq",
    }, { signal: barsController.signal, timeout: 30000 });
    if (!result.bars.length) throw new Error(`当前周期暂无行情数据：${state.symbol}`);
    state.bars = mergeBarsByTime(state.bars, result.bars);
    updateMarketMeta(result.meta);
    if (result.meta?.data_warning) pushLog("数据", result.meta.data_warning);
    pushLog("数据", `正在刷新${state.stockName} ${periodLabel(state.period)}行情`);
    pushLog("图表", `分钟线已更新，共 ${state.bars.length} 根K线`);
  } catch (error) {
    if (!String(error.message).includes("请求已取消")) {
      pushLog("错误", `K线刷新失败：${translateError(error.message)}`);
    }
  } finally {
    state.loadingBars = false;
  }
}

async function refreshNews() {
  newsController?.abort();
  newsController = new AbortController();
  state.loadingNews = true;
  try {
    const result = await getStockNews(state.symbol, { signal: newsController.signal, timeout: 25000 });
    state.news = result.items || [];
    updateMarketMeta({ source: result.source || state.dataSource, latency_ms: result.latency_ms, timestamp: result.timestamp });
    pushLog("消息", `${result.source || "消息源"}返回 ${state.news.length} 条相关消息`);
  } catch (error) {
    if (!String(error.message).includes("请求已取消")) {
      pushLog("错误", `消息面刷新失败：${translateError(error.message)}`);
    }
  } finally {
    state.loadingNews = false;
  }
}

async function loadMarket({ keepBacktest = false } = {}) {
  state.loadingMarket = true;
  state.loadingBars = true;
  state.fallbackMode = false;
  clearError();
  pushLog("数据", `正在获取 ${state.stockName || state.symbol} 的真实行情，周期：${periodLabel(state.period)}`);
  try {
    const [barsResult, quoteResult] = await Promise.allSettled([
      getMarketBarsPayload({
        symbol: state.symbol,
        period: state.period,
        startDate: marketStartDate(),
        endDate: state.endDate,
        adjust: "qfq",
      }),
      getQuote(state.symbol),
    ]);

    if (barsResult.status === "rejected") throw barsResult.reason;
    state.bars = barsResult.value.bars;
    if (!state.bars.length) throw new Error(`当前周期暂无行情数据：${state.symbol}`);
    updateMarketMeta(barsResult.value.meta);
    if (barsResult.value.meta?.data_warning) pushLog("数据", barsResult.value.meta.data_warning);

    if (quoteResult.status === "fulfilled" && quoteResult.value) {
      state.quote = quoteResult.value;
      state.stockName = quoteResult.value.name || state.stockName;
      updateMarketMeta(quoteResult.value);
    } else {
      pushLog("错误", `行情快照暂不可用：${translateError(quoteResult.reason?.message || "未知错误")}`);
      state.quote = deriveQuoteFromBars();
    }

    if (!keepBacktest && !state.loadingBacktest && !state.metrics) {
      state.trades = [];
    }
    pushLog("图表", `K线数据重建完成，共 ${state.bars.length} 根`);
    pushLog("完成", `${state.stockName || state.symbol} 行情同步完成`);
    return true;
  } catch (error) {
    state.fallbackMode = false;
    pushLog("错误", state.bars.length ? "行情获取失败，已保留上一屏真实K线，未使用演示数据。" : "行情获取失败，已停止绘制K线，未使用演示数据。");
    setError(`行情请求失败：${error.message}`);
    return false;
  } finally {
    state.loadingMarket = false;
    state.loadingBars = false;
  }
}

function startRealtimePolling() {
  stopRealtimePolling();
  state.pollingActive = true;
  pushLog("系统", "实时盯盘轮询已启动");
  refreshQuote();
  refreshLatestBar();
  refreshNews();
  quoteTimer = window.setInterval(refreshQuote, QUOTE_INTERVAL);
  if (state.period !== "day") {
    barTimer = window.setInterval(refreshLatestBar, BAR_INTERVAL);
  }
  newsTimer = window.setInterval(refreshNews, NEWS_INTERVAL);
}

function stopRealtimePolling() {
  if (quoteTimer) window.clearInterval(quoteTimer);
  if (barTimer) window.clearInterval(barTimer);
  if (newsTimer) window.clearInterval(newsTimer);
  quoteTimer = null;
  barTimer = null;
  newsTimer = null;
  quoteController?.abort();
  barsController?.abort();
  newsController?.abort();
  state.pollingActive = false;
}

async function switchStock(item) {
  stopRealtimePolling();
  const previous = { symbol: state.symbol, stockName: state.stockName };
  setStock(item);
  state.metrics = null;
  state.trades = [];
  state.aiAudit = null;
  state.aiStockAnalysis = null;
  state.agentCommittee = null;
  pushLog("数据", `切换股票：${state.stockName}（${state.symbol}）`);
  const ok = await loadMarket();
  if (!ok) {
    state.symbol = previous.symbol;
    state.stockName = previous.stockName;
    pushLog("系统", `切换失败，已保留上一只股票：${state.stockName}`);
  }
  if (state.currentPage === "radar") startRealtimePolling();
}

async function switchPeriod(period) {
  stopRealtimePolling();
  const previousPeriod = state.period;
  setPeriod(period);
  state.trades = [];
  state.metrics = null;
  pushLog("数据", `切换周期：${periodLabel(period)}`);
  const ok = await loadMarket();
  if (!ok) {
    state.period = previousPeriod;
    pushLog("系统", `周期切换失败，已保留上一周期：${periodLabel(previousPeriod)}`);
  }
  if (state.currentPage === "radar") startRealtimePolling();
}

async function runStockAnalysis(question = state.aiStockQuestion) {
  state.loadingAIAnalysis = true;
  const content = String(question || state.aiStockQuestion || "").trim();
  state.aiStockQuestion = content;
  if (content) {
    state.committeeMessages.push({ role: "user", content: maskSecretText(content) });
  }
  pushLog("AI", "AI投研委员会正在分析当前股票");
  try {
    const result = await runMarketWatchCommittee({
      symbol: state.symbol,
      name: state.stockName,
      question: state.aiStockQuestion,
      period: state.period,
      quote: state.quote,
      bars: state.bars.slice(-120),
      news: state.news.slice(0, 12),
      metrics: state.metrics || {},
      trades: state.trades || [],
      data_source: state.dataSource,
      messages: state.committeeMessages.slice(-8).map((message) => ({
        role: message.role === "assistant" ? "assistant" : "user",
        content: String(message.content || ""),
      })),
    });
    if (result?.success === false) {
      throw new Error(result.message || "缺少真实数据，AI 暂无法分析。");
    }
    state.agentCommittee = result;
    state.committeeMessages.push({
      role: "assistant",
      content: result.answer || result.final_summary || "投研委员会已完成分析，但未返回可展示文本。",
      basis: result.basis,
      agent_labels: result.agent_labels || [],
      source: result.agent_mode || result.source || "AI投研委员会",
    });
    state.aiStockAnalysis = {
      summary: result.final_summary,
      basis: [result.technical_view, result.news_view].filter(Boolean),
      risks: [result.risk_view, result.bear_case].filter(Boolean),
      suggestions: [result.bull_case].filter(Boolean),
      source: "AI投研委员会",
    };
    pushLog("完成", "AI投研委员会分析完成");
  } catch (error) {
    state.committeeMessages.push({ role: "assistant", content: `投研委员会分析失败：${translateError(error.message)}` });
    setError(`AI投研委员会分析失败：${error.message}`);
  } finally {
    state.loadingAIAnalysis = false;
  }
}

async function runFinancialAgentChat(question = state.financialAgentQuestion) {
  state.loadingAIAnalysis = true;
  const content = String(question || state.financialAgentQuestion || "").trim();
  state.financialAgentQuestion = content;
  if (content) {
    state.financialAgentMessages.push({ role: "user", content: maskSecretText(content) });
  }
  pushLog("AI", "金融 Agent 正在处理当前页面问题");
  try {
    const result = await runFinancialAgent({
      query: content,
      page: state.currentPage,
      context: {
        page: state.currentPage,
        symbol: state.symbol,
        stock_name: state.stockName,
        period: state.period,
        strategy_json: state.strategyJson,
        generated_code: state.generatedCode ? "present" : "",
        backtest_id: state.backtestResult?.backtest_id || "",
        metrics: state.metrics || state.backtestResult?.metrics || null,
        trade_count: state.trades?.length || state.backtestResult?.trades?.length || 0,
        bars_count: state.bars?.length || 0,
        news_count: state.news?.length || 0,
        quote: state.quote || null,
        data_source: state.dataSource,
      },
      messages: state.financialAgentMessages.slice(-8).map((message) => ({
        role: message.role === "assistant" ? "assistant" : "user",
        content: String(message.content || ""),
      })),
    });
    if (result?.success === false && !result.answer) {
      throw new Error(result.message || "金融 Agent 暂无法回答。");
    }
    state.financialAgentResult = result;
    state.financialAgentMessages.push({
      role: "assistant",
      content: result.answer || result.final_summary || result.message || "金融 Agent 已完成，但没有返回可展示文本。",
      basis: result.basis,
      agent_labels: result.agent_labels || [],
      source: result.source || "金融 Agent",
    });
    pushLog("完成", "金融 Agent 已完成回答");
  } catch (error) {
    state.financialAgentMessages.push({ role: "assistant", content: `金融 Agent 调用失败：${translateError(error.message)}` });
    setError(`金融 Agent 调用失败：${error.message}`);
  } finally {
    state.loadingAIAnalysis = false;
  }
}

async function generateStrategyByAgent(payload = {}) {
  state.loadingStrategyParse = true;
  state.loadingCode = true;
  pushLog("AI", "策略生成 Agent 正在结构化策略并生成代码");
  try {
    const result = await agentStrategyGenerate({
      symbol: state.symbol,
      period: payload.period || state.period,
      startDate: payload.startDate || state.startDate,
      endDate: payload.endDate || state.endDate,
      idea: payload.idea || state.strategyInput,
      framework: payload.framework || {},
      buyIdea: state.buyIdea,
      sellIdea: state.sellIdea,
      riskIdea: state.riskIdea,
    });
    state.strategyJson = result.strategy_json;
    state.generatedCode = result.generated_code || "";
    const rules = state.strategyJson?.rules || {};
    state.buyIdea = (rules.buy_rules || []).map((rule) => rule.expression).filter(Boolean).join(" and ") || state.buyIdea;
    state.sellIdea = (rules.sell_rules || []).map((rule) => rule.expression).filter(Boolean).join(" and ") || state.sellIdea;
    state.riskIdea = (rules.risk_rules || []).map((rule) => rule.expression).filter(Boolean).join(" and ") || state.riskIdea;
    pushLog("完成", `策略生成 Agent 已完成：${result.strategy_name}`);
    return result;
  } catch (error) {
    setError(`策略生成 Agent 失败：${error.message}`);
    return null;
  } finally {
    state.loadingStrategyParse = false;
    state.loadingCode = false;
  }
}

async function streamBacktestLogs() {
  const steps = [
    ["系统", "校验 A 股 T+1 与 100 股整手交易约束"],
    ["数据", "正在获取真实前复权行情"],
    ["引擎", "正在生成 rqalpha 可执行策略"],
    ["引擎", "正在注入 rqalpha 撮合引擎"],
    ["风控", "正在计算最大回撤与夏普率"],
    ["完成", "正在生成 A 股交割单"],
  ];
  for (const [level, message] of steps) {
    pushLog(level, message);
    await sleep(180);
  }
}

async function runBacktest() {
  if (state.loadingBacktest) return null;
  state.loadingBacktest = true;
  state.loadingAI = false;
  state.error = null;
  state.fallbackMode = false;
  state.metrics = null;
  state.aiAudit = null;
  state.trades = [];
  pushLog("引擎", `提交 ${state.symbol} 单股回测任务`);
  const logPromise = streamBacktestLogs();
  try {
    const result = await requestBacktest({
      mode: state.strategyJson?.mode || state.strategyJson?.strategy_mode || state.strategyJson?.params?.strategy_mode || "single_stock",
      symbol: state.symbol,
      startDate: state.startDate,
      endDate: state.endDate,
      buyIdea: state.buyIdea,
      sellIdea: state.sellIdea,
      riskIdea: state.riskIdea,
      period: state.period,
      strategyName: state.strategyJson?.strategy_name,
      rules: state.strategyJson?.rules,
      params: {
        initial_cash: 1000000,
        commission: 0.0003,
        slippage: 0.0005,
        t_plus_one: true,
        round_lot: 100,
        stock_pool: state.strategyJson?.stock_pool,
        factors: state.strategyJson?.factors,
        ...(state.strategyJson?.params || {}),
      },
      execution_time: state.strategyJson?.params?.execution_time || state.strategyJson?.execution_time || null,
    });
    await logPromise;
    state.metrics = result.metrics;
    state.trades = result.trades;
    state.backtestResult = result;
    if (result.bars?.length) state.bars = result.bars;
    state.aiAudit = result.ai_audit || null;
    state.quote = deriveQuoteFromBars() || state.quote;
    state.lastBacktestAt = new Date().toISOString();
    pushLog("完成", `回测完成，总收益 ${formatPercent(state.metrics?.total_return)}，交割记录 ${state.trades.length} 条`);
    await runAudit();
    return result;
  } catch (error) {
    await logPromise;
    state.fallbackMode = false;
    state.metrics = null;
    state.trades = [];
    state.aiAudit = null;
    state.backtestResult = error.payload || {
      success: false,
      message: error.message,
    };
    pushLog("错误", `回测失败：${error.message}`);
    setError(`回测失败：${error.message}`);
    return null;
  } finally {
    state.loadingBacktest = false;
  }
}

async function runAudit() {
  state.loadingAI = true;
  pushLog("AI", "回测审计 Agent 正在分析策略质量");
  try {
    const audit = await agentBacktestAudit({
      symbol: state.symbol,
      name: state.stockName,
      strategyName: state.strategyJson?.strategy_name || "龙虾量化策略",
      period: state.period,
      strategyJson: state.strategyJson,
      metrics: state.metrics,
      trades: state.trades,
      bars: state.bars,
    });
    state.aiAudit = audit;
    pushLog("完成", "回测审计 Agent 已同步");
  } catch (error) {
    pushLog("错误", `回测审计 Agent 失败：${translateError(error.message)}`);
  } finally {
    state.loadingAI = false;
  }
}

async function generateCode() {
  state.loadingCode = true;
  pushLog("引擎", "正在生成 rqalpha 策略代码");
  try {
    const result = await generateStrategyCode({
      symbol: state.symbol,
      period: state.period,
      startDate: state.startDate,
      endDate: state.endDate,
      strategyName: state.strategyJson?.strategy_name || "龙虾量化策略",
      rules: state.strategyJson?.rules,
      params: state.strategyJson?.params,
      buyIdea: state.buyIdea,
      sellIdea: state.sellIdea,
      riskIdea: state.riskIdea,
    });
    state.generatedCode = result.code || "";
    pushLog("完成", "rqalpha 策略代码已生成");
    return result;
  } catch (error) {
    setError(`策略代码生成失败：${error.message}`);
    return null;
  } finally {
    state.loadingCode = false;
  }
}

async function debugGeneratedCode(errorMessage = "") {
  state.loadingDebug = true;
  pushLog("AI", "策略 Debug Agent 正在读取错误信息");
  try {
    const result = await agentStrategyDebug({
      strategyJson: state.strategyJson,
      generatedCode: state.generatedCode,
      errorMessage: errorMessage || state.error || "未提供错误信息",
      runtimeContext: {
        engine: "rqalpha",
        data_source: state.dataSource || "akshare",
        symbol: state.symbol,
        period: state.period,
      },
    });
    state.generatedCode = result.fixed_code || state.generatedCode;
    state.debugHistory.unshift({
      time: nowTime(),
      diagnosis: result.diagnosis,
      fix_summary: result.fix_summary,
      source: result.source,
    });
    pushLog("完成", "策略 Debug Agent 已完成");
    return result;
  } catch (error) {
    setError(`策略 Debug Agent 失败：${error.message}`);
    return null;
  } finally {
    state.loadingDebug = false;
  }
}

function readStrategies() {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function writeStrategies(strategies) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(strategies));
  state.savedStrategies = strategies;
}

function buildCurrentStrategy(name = state.strategyJson?.strategy_name || "龙虾量化策略") {
  const metrics = state.metrics || {};
  return {
    id: `strategy_${Date.now()}`,
    name,
    symbol: state.symbol,
    name_cn: state.stockName,
    period: state.period,
    total_return: metrics.total_return ?? 0,
    annual_return: metrics.annual_return ?? 0,
    max_drawdown: metrics.max_drawdown ?? 0,
    sharpe: metrics.sharpe ?? 0,
    buy_idea: state.buyIdea,
    sell_idea: state.sellIdea,
    risk_idea: state.riskIdea,
    rules: state.strategyJson?.rules || {},
    params: state.strategyJson?.params || {},
    created_at: new Date().toLocaleString("zh-CN", { hour12: false }),
  };
}

async function saveCurrentStrategy(name = state.strategyJson?.strategy_name || "龙虾量化策略") {
  const strategy = buildCurrentStrategy(name);
  const strategies = readStrategies();
  strategies.unshift(strategy);
  writeStrategies(strategies.slice(0, 60));
  try {
    const saved = await publishCommunityStrategy({
      ...strategy,
      author: "本地用户",
      category: state.strategyJson?.strategy_type || "本地保存",
      risk_level: state.backtestResult?.trust_audit?.trust_level === "low" ? "需复核" : "待评估",
      description: state.strategyJson?.explanation || "本地保存的策略，可在策略广场中复用。",
    });
    state.communityStrategies = [saved, ...state.communityStrategies.filter((item) => item.id !== saved.id)];
    pushLog("完成", `策略已保存到数据库：${saved.name}`);
    return saved;
  } catch (error) {
    pushLog("错误", `策略已保存到本地，但写入数据库失败：${translateError(error.message)}`);
  }
  pushLog("完成", `策略已保存到本地：${strategy.name}`);
  return strategy;
}

function loadSavedStrategy(strategy) {
  if (!strategy) return;
  state.symbol = normalizeSymbol(strategy.symbol);
  state.stockName = strategy.name_cn || strategy.name || state.stockName;
  state.period = strategy.period === "日线" ? "day" : strategy.period || "day";
  state.buyIdea = strategy.buy_idea || strategy.rules?.buy_rules?.[0]?.expression || state.buyIdea;
  state.sellIdea = strategy.sell_idea || strategy.rules?.sell_rules?.[0]?.expression || state.sellIdea;
  state.riskIdea = strategy.risk_idea || strategy.rules?.risk_rules?.[0]?.expression || state.riskIdea;
  state.strategyJson = {
    strategy_name: strategy.name,
    strategy_type: strategy.category || "社区策略",
    symbol: state.symbol,
    period: state.period,
    rules: strategy.rules || {},
    params: strategy.params || {},
  };
  state.metrics = {
    total_return: Number(strategy.total_return || 0),
    annual_return: Number(strategy.annual_return || 0),
    max_drawdown: Number(strategy.max_drawdown || 0),
    sharpe: Number(strategy.sharpe || 0),
  };
  pushLog("完成", `已加载策略：${strategy.name}`);
}

async function loadCommunityStrategies() {
  state.loadingCommunity = true;
  try {
    state.communityStrategies = await listCommunityStrategies();
    return state.communityStrategies;
  } catch (error) {
    setError(`策略社区加载失败：${error.message}`);
    state.communityStrategies = [];
    return [];
  } finally {
    state.loadingCommunity = false;
  }
}

async function publishCurrentStrategy() {
  const local = buildCurrentStrategy(state.strategyJson?.strategy_name || "龙虾量化策略");
  const strategies = readStrategies();
  strategies.unshift(local);
  writeStrategies(strategies.slice(0, 60));
  try {
    const published = await publishCommunityStrategy({
      ...local,
      author: "本地用户",
      category: state.strategyJson?.strategy_type || "用户发布",
      risk_level: "待评估",
      description: state.strategyJson?.explanation || "由 AI 投研工坊生成的策略。",
      favorites: 0,
      forks: 0,
    });
    state.communityStrategies.unshift(published);
    pushLog("完成", `策略已发布到头等舱：${published.name}`);
    return published;
  } catch (error) {
    setError(`发布策略失败：${error.message}`);
    return null;
  }
}

async function favoriteCommunity(id) {
  const result = await favoriteCommunityStrategy(id);
  await loadCommunityStrategies();
  return result;
}

async function forkCommunity(id) {
  const result = await forkCommunityStrategy(id);
  await loadCommunityStrategies();
  return result;
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${(number * 100).toFixed(2)}%`;
}

function formatDrawdown(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return `${Math.abs(number * 100).toFixed(2)}%`;
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "--";
}

function formatPrice(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "--";
}

function formatAmount(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  if (Math.abs(number) >= 100000000) return `${(number / 100000000).toFixed(2)}亿`;
  if (Math.abs(number) >= 10000) return `${(number / 10000).toFixed(2)}万`;
  return number.toFixed(0);
}

export function useMarketStore() {
  return {
    state,
    pushLog,
    setError,
    clearError,
    setSymbol,
    setStock,
    switchStock,
    setPeriod,
    switchPeriod,
    periodLabel,
    selectedPool,
    selectPool,
    isInWatchlist,
    addToWatchlist,
    removeFromWatchlist,
    toggleWatchlist,
    openAiAssistant,
    closeAiAssistant,
    searchStock,
    searchStockByAI,
    loadMarket,
    refreshQuote,
    refreshLatestBar,
    refreshNews,
    startRealtimePolling,
    stopRealtimePolling,
    runStockAnalysis,
    runFinancialAgentChat,
    generateStrategyByAgent,
    runBacktest,
    runAudit,
    generateCode,
    debugGeneratedCode,
    saveCurrentStrategy,
    loadSavedStrategy,
    readStrategies,
    writeStrategies,
    loadCommunityStrategies,
    publishCurrentStrategy,
    favoriteCommunity,
    forkCommunity,
    formatPercent,
    formatDrawdown,
    formatNumber,
    formatPrice,
    formatAmount,
    translateError,
  };
}
