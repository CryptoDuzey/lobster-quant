<script setup>
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
} from "lightweight-charts";
import { Activity, BarChart3, BrainCircuit, Star } from "lucide-vue-next";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const chartHost = ref(null);
const chartReady = ref(false);

let chart = null;
let candleSeries = null;
let ma20Series = null;
let atrUpperSeries = null;
let atrLowerSeries = null;
let volumeSeries = null;
let markersApi = null;
let resizeObserver = null;
let lastRowsCount = 0;

const latestBar = computed(() => store.state.bars[store.state.bars.length - 1] || null);
const marketRangeText = computed(() => {
  if (!store.state.marketActualStart || !store.state.marketActualEnd) return "";
  return `${store.state.marketActualStart} 至 ${store.state.marketActualEnd} · ${store.state.marketBarsCount || store.state.bars.length} 根`;
});
const periods = [
  { value: "1m", label: "1分" },
  { value: "5m", label: "5分" },
  { value: "15m", label: "15分" },
  { value: "30m", label: "30分" },
  { value: "60m", label: "60分" },
  { value: "day", label: "日线" },
];

function toChartTime(value) {
  const text = String(value || "");
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const date = new Date(text.replace(" ", "T"));
  return Math.floor(date.getTime() / 1000);
}

function chartTimeToText(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number") return new Date(value * 1000).toISOString().slice(0, 19).replace("T", " ");
  if (value.year && value.month && value.day) {
    return `${value.year}-${String(value.month).padStart(2, "0")}-${String(value.day).padStart(2, "0")}`;
  }
  return String(value);
}

function toTradeMarkerTime(trade) {
  if (store.state.period === "day") {
    const day = trade.date || String(trade.time || "").slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : toChartTime(trade.time);
  }
  return toChartTime(trade.time || trade.date);
}

function usableBars() {
  return store.state.bars
    .map((bar) => ({
      ...bar,
      chartTime: toChartTime(bar.time),
    }))
    .filter((bar) => bar.chartTime && Number.isFinite(Number(bar.open)) && Number.isFinite(Number(bar.close)));
}

function initChart() {
  if (!chartHost.value || chart) return;
  chart = createChart(chartHost.value, {
    layout: {
      background: { color: "#060608" },
      textColor: "#A9A0A0",
      fontFamily: "JetBrains Mono, Consolas, monospace",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: "rgba(212,175,55,0.055)" },
      horzLines: { color: "rgba(212,175,55,0.055)" },
    },
    rightPriceScale: {
      borderColor: "rgba(212,175,55,0.2)",
      scaleMargins: { top: 0.1, bottom: 0.24 },
    },
    timeScale: {
      borderColor: "rgba(212,175,55,0.2)",
      timeVisible: store.state.period !== "day",
      secondsVisible: false,
    },
    crosshair: {
      mode: 0,
      vertLine: { color: "rgba(212,175,55,0.28)" },
      horzLine: { color: "rgba(212,175,55,0.28)" },
    },
  });

  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: "#FF453A",
    downColor: "#32D74B",
    wickUpColor: "#FF453A",
    wickDownColor: "#32D74B",
    borderVisible: false,
  });
  ma20Series = chart.addSeries(LineSeries, {
    color: "#D4AF37",
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
  });
  atrUpperSeries = chart.addSeries(LineSeries, {
    color: "rgba(100,210,255,0.72)",
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
  });
  atrLowerSeries = chart.addSeries(LineSeries, {
    color: "rgba(100,210,255,0.42)",
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
  });
  volumeSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
    color: "rgba(212,175,55,0.2)",
    priceLineVisible: false,
    lastValueVisible: false,
  });
  chart.priceScale("volume").applyOptions({
    scaleMargins: { top: 0.82, bottom: 0 },
  });
  markersApi = createSeriesMarkers(candleSeries, []);
  chart.subscribeClick((param) => {
    if (!param?.time) return;
    const time = chartTimeToText(param.time);
    store.openAiAssistant(`请结合真实行情和消息面，分析 ${time} 附近这段K线为什么这样走。`, {
      type: "chart_point",
      time,
      symbol: store.state.symbol,
      period: store.state.period,
    });
  });

  resizeObserver = new ResizeObserver(resizeChart);
  resizeObserver.observe(chartHost.value);
  chartReady.value = true;
  resizeChart();
}

function resizeChart() {
  if (!chart || !chartHost.value) return;
  const { width, height } = chartHost.value.getBoundingClientRect();
  if (width > 0 && height > 0) {
    chart.resize(Math.floor(width), Math.floor(height));
    fitVisibleRange();
  }
}

function fitVisibleRange() {
  if (!chart) return;
  if (!lastRowsCount) {
    chart.timeScale().fitContent();
    return;
  }
  if (lastRowsCount <= 180) {
    const padding = Math.min(10, Math.max(4, Math.ceil(lastRowsCount * 0.06)));
    chart.timeScale().setVisibleLogicalRange({
      from: -padding,
      to: lastRowsCount - 1 + padding,
    });
    return;
  }
  chart.timeScale().fitContent();
}

function updateChartData() {
  if (!chart || !candleSeries) return;
  const rows = usableBars();
  if (!rows.length) {
    lastRowsCount = 0;
    candleSeries.setData([]);
    ma20Series.setData([]);
    atrUpperSeries.setData([]);
    atrLowerSeries.setData([]);
    volumeSeries.setData([]);
    markersApi?.setMarkers([]);
    return;
  }
  lastRowsCount = rows.length;
  candleSeries.setData(rows.map((bar) => ({
    time: bar.chartTime,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  })));
  ma20Series.setData(rows.filter((bar) => bar.ma20 != null).map((bar) => ({ time: bar.chartTime, value: bar.ma20 })));
  atrUpperSeries.setData(rows.filter((bar) => bar.atr_upper != null).map((bar) => ({ time: bar.chartTime, value: bar.atr_upper })));
  atrLowerSeries.setData(rows.filter((bar) => bar.atr_lower != null).map((bar) => ({ time: bar.chartTime, value: bar.atr_lower })));
  volumeSeries.setData(rows.map((bar) => ({
    time: bar.chartTime,
    value: bar.volume || 0,
    color: bar.close >= bar.open ? "rgba(255,69,58,0.2)" : "rgba(50,215,75,0.2)",
  })));
  updateTradeMarkers();
  resizeChart();
}

function updateTradeMarkers() {
  if (!markersApi) return;
  const markers = store.state.trades
    .filter((trade) => trade.time)
    .map((trade) => {
      const direction = String(trade.direction).toUpperCase();
      const buy = direction.includes("BUY");
      return {
        time: toTradeMarkerTime(trade),
        position: buy ? "belowBar" : "aboveBar",
        shape: buy ? "arrowUp" : "arrowDown",
        color: buy ? "#FF453A" : "#32D74B",
        text: buy ? "买" : "卖",
      };
    })
    .filter((marker) => marker.time)
    .sort((a, b) => String(a.time).localeCompare(String(b.time)));
  markersApi.setMarkers(markers);
}

onMounted(async () => {
  await nextTick();
  initChart();
  updateChartData();
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  chart?.remove();
  chart = null;
});

watch(
  () => [store.state.bars, store.state.period],
  () => {
    if (chart) {
      chart.applyOptions({
        timeScale: { timeVisible: store.state.period !== "day" },
      });
    }
    updateChartData();
  },
  { deep: true },
);

watch(
  () => store.state.trades,
  () => updateTradeMarkers(),
  { deep: true },
);

async function changePeriod(period) {
  if (period === store.state.period || store.state.loadingMarket) return;
  await store.switchPeriod(period);
}

function toggleCurrentWatchlist() {
  store.toggleWatchlist({
    symbol: store.state.symbol,
    name: store.state.stockName,
    price: store.state.quote?.price,
    change_pct: store.state.quote?.change_pct,
    amount: store.state.quote?.amount,
  });
}

function analyzeCurrentChart() {
  const latest = latestBar.value?.time || "";
  store.openAiAssistant(`请分析当前 ${store.state.stockName} 的${store.periodLabel(store.state.period)}走势，重点看技术面、消息面和风险。`, {
    type: "chart_current",
    time: latest,
    symbol: store.state.symbol,
    period: store.state.period,
  });
}
</script>

<template>
  <section class="panel chart-panel">
    <header class="panel-header chart-header">
      <div class="chart-title-group">
        <h2 class="panel-title"><BarChart3 :size="15" /> K线 / MA20 / ATR</h2>
        <button
          class="watch-star"
          :class="{ active: store.isInWatchlist(store.state.symbol) }"
          :title="store.isInWatchlist(store.state.symbol) ? '从自选股移除' : '加入自选股'"
          @click="toggleCurrentWatchlist"
        >
          <Star :size="15" />
          <span>{{ store.isInWatchlist(store.state.symbol) ? "已自选" : "加自选" }}</span>
        </button>
        <button class="watch-star ai" title="打开 AI 助手分析当前图表" @click="analyzeCurrentChart">
          <BrainCircuit :size="15" />
          <span>分析图表</span>
        </button>
      </div>
      <div class="mini-periods">
        <button
          v-for="item in periods"
          :key="item.value"
          :class="{ active: store.state.period === item.value }"
          :disabled="store.state.loadingMarket"
          @click="changePeriod(item.value)"
        >
          {{ item.label }}
        </button>
      </div>
      <div class="ohlc" v-if="latestBar">
        <span>O {{ store.formatPrice(latestBar.open) }}</span>
        <span>H {{ store.formatPrice(latestBar.high) }}</span>
        <span>L {{ store.formatPrice(latestBar.low) }}</span>
        <span>C {{ store.formatPrice(latestBar.close) }}</span>
      </div>
    </header>
    <div v-if="marketRangeText || store.state.marketDataWarning" class="market-range-strip">
      <span v-if="marketRangeText">真实范围：{{ marketRangeText }}</span>
      <span v-if="store.state.marketDataWarning" class="range-warning">{{ store.state.marketDataWarning }}</span>
    </div>
    <div class="chart-wrap">
      <div ref="chartHost" class="chart-host" />
      <div v-if="store.state.loadingMarket" class="chart-overlay">
        <Activity class="spin" :size="22" /> 正在加载真实行情
      </div>
      <div v-else-if="!store.state.bars.length" class="chart-overlay">
        暂无行情数据
      </div>
    </div>
  </section>
</template>

<style scoped>
.chart-panel {
  flex: 1;
  width: 100%;
  height: 100%;
  min-height: 420px;
}

.chart-header {
  display: grid;
  grid-template-columns: minmax(180px, auto) minmax(256px, 1fr) auto;
  align-items: center;
  min-height: 50px;
}

.chart-title-group {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.watch-star {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-muted);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 0 9px;
  white-space: nowrap;
}

.watch-star.active,
.watch-star:hover {
  border-color: rgba(212, 175, 55, 0.52);
  background: rgba(212, 175, 55, 0.12);
  color: var(--gold);
}

.watch-star.ai {
  border-color: rgba(100, 210, 255, 0.2);
  color: var(--engine-cyan);
}

.watch-star.ai:hover {
  border-color: rgba(100, 210, 255, 0.52);
  background: rgba(100, 210, 255, 0.1);
}

.ohlc {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
}

.mini-periods {
  display: grid;
  grid-template-columns: repeat(6, minmax(40px, 1fr));
  gap: 5px;
  min-width: 276px;
  max-width: 360px;
}

.mini-periods button {
  height: 26px;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-muted);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
}

.mini-periods button.active,
.mini-periods button:hover:not(:disabled) {
  border-color: rgba(212, 175, 55, 0.58);
  background: rgba(212, 175, 55, 0.13);
  color: var(--gold);
}

.chart-wrap {
  position: relative;
  height: calc(100% - 77px);
  min-height: 360px;
  overflow: hidden;
  background:
    linear-gradient(90deg, rgba(212, 175, 55, 0.028) 1px, transparent 1px),
    linear-gradient(0deg, rgba(212, 175, 55, 0.022) 1px, transparent 1px),
    #060608;
  background-size: 62px 62px, 62px 62px, auto;
}

.market-range-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 28px;
  padding: 0 12px;
  border-top: 1px solid rgba(212, 175, 55, 0.08);
  border-bottom: 1px solid rgba(212, 175, 55, 0.08);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 800;
  overflow: hidden;
  white-space: nowrap;
}

.range-warning {
  color: var(--gold);
  overflow: hidden;
  text-overflow: ellipsis;
}

.chart-host {
  position: absolute;
  inset: 0;
  min-width: 0;
  min-height: 0;
}

.chart-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(6, 6, 8, 0.62);
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0;
}

@media (max-width: 1180px) {
  .chart-panel {
    min-height: 520px;
  }

  .chart-header {
    grid-template-columns: 1fr;
  }

  .mini-periods {
    max-width: none;
    width: 100%;
  }
}
</style>
