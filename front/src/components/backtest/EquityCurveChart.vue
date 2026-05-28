<script setup>
import { AreaSeries, LineSeries, createChart } from "lightweight-charts";
import { LineChart } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useMarketStore } from "../../stores/useMarketStore";

const store = useMarketStore();
const returnHost = ref(null);
const drawdownHost = ref(null);

let returnChart = null;
let drawdownChart = null;
let strategySeries = null;
let benchmarkSeries = null;
let drawdownSeries = null;
let returnResizeObserver = null;
let drawdownResizeObserver = null;

const curves = computed(() => store.state.backtestResult?.curves || {});
const strategyCurve = computed(() => normalizeCurve(curves.value.strategy_curve));
const benchmarkCurve = computed(() => normalizeCurve(curves.value.benchmark_curve));
const drawdownCurve = computed(() => normalizeCurve(curves.value.drawdown_curve));
const validBenchmark = computed(() => isValidBenchmarkCurve(benchmarkCurve.value));
const hasCurve = computed(() => strategyCurve.value.length > 0 || drawdownCurve.value.length > 0);

function normalizeCurve(rows = []) {
  return Array.isArray(rows)
    ? rows
        .map((item) => ({ time: item.time, value: Number(item.value) * 100 }))
        .filter((item) => item.time && Number.isFinite(item.value))
    : [];
}

function isValidBenchmarkCurve(curve) {
  if (!Array.isArray(curve) || curve.length < 2) return false;
  const values = curve.map((item) => Number(item.value)).filter(Number.isFinite);
  if (values.length < 2) return false;
  return Math.abs(Math.max(...values) - Math.min(...values)) >= 1e-8;
}

function initReturnChart() {
  if (!returnHost.value || returnChart) return;
  returnChart = createChart(returnHost.value, chartOptions(0.12));
  strategySeries = returnChart.addSeries(LineSeries, {
    color: "#D4AF37",
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
  });
  benchmarkSeries = returnChart.addSeries(LineSeries, {
    color: "rgba(100,210,255,0.86)",
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
  });
  returnResizeObserver = new ResizeObserver(() => resizeChart(returnChart, returnHost.value));
  returnResizeObserver.observe(returnHost.value);
  resizeChart(returnChart, returnHost.value);
}

function initDrawdownChart() {
  if (!drawdownHost.value || drawdownChart) return;
  drawdownChart = createChart(drawdownHost.value, chartOptions(0.08));
  drawdownSeries = drawdownChart.addSeries(AreaSeries, {
    topColor: "rgba(50,215,75,0.08)",
    bottomColor: "rgba(50,215,75,0.28)",
    lineColor: "rgba(50,215,75,0.82)",
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
  });
  drawdownResizeObserver = new ResizeObserver(() => resizeChart(drawdownChart, drawdownHost.value));
  drawdownResizeObserver.observe(drawdownHost.value);
  resizeChart(drawdownChart, drawdownHost.value);
}

function resizeChart(targetChart, host) {
  if (!targetChart || !host) return;
  const rect = host.getBoundingClientRect();
  if (rect.width > 0 && rect.height > 0) {
    targetChart.resize(Math.floor(rect.width), Math.floor(rect.height));
    targetChart.timeScale().fitContent();
  }
}

function chartOptions(topMargin) {
  return {
    autoSize: true,
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
      borderColor: "rgba(212,175,55,0.18)",
      scaleMargins: { top: topMargin, bottom: 0.12 },
    },
    timeScale: {
      borderColor: "rgba(212,175,55,0.18)",
    },
  };
}

function updateCharts() {
  if (!returnChart || !drawdownChart) return;
  strategySeries?.setData(strategyCurve.value);
  benchmarkSeries?.setData(validBenchmark.value ? benchmarkCurve.value : []);
  drawdownSeries?.setData(drawdownCurve.value);
  resizeChart(returnChart, returnHost.value);
  resizeChart(drawdownChart, drawdownHost.value);
}

onMounted(() => {
  initReturnChart();
  initDrawdownChart();
  updateCharts();
});

onBeforeUnmount(() => {
  returnResizeObserver?.disconnect();
  drawdownResizeObserver?.disconnect();
  returnChart?.remove();
  drawdownChart?.remove();
  returnChart = null;
  drawdownChart = null;
});

watch(curves, updateCharts, { deep: true });
</script>

<template>
  <section class="panel curve-panel">
    <header class="panel-header">
      <h2 class="panel-title"><LineChart :size="15" /> 收益 / 回撤曲线</h2>
      <div class="legend">
        <span class="strategy">策略累计收益</span>
        <span v-if="validBenchmark" class="benchmark">基准累计收益</span>
        <span class="drawdown">策略回撤</span>
      </div>
    </header>

    <div v-if="!hasCurve" class="empty-state">
      等待回测生成收益曲线。
    </div>
    <div v-else class="curve-body">
      <div v-if="!validBenchmark" class="benchmark-warning">基准数据无效，暂不展示基准曲线。</div>
      <div ref="returnHost" class="return-host" />
      <div ref="drawdownHost" class="drawdown-host" />
    </div>
  </section>
</template>

<style scoped>
.curve-panel {
  min-height: 330px;
}

.legend {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.legend span::before {
  content: "";
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 5px;
  border-radius: 50%;
}

.strategy::before {
  background: var(--gold);
}

.benchmark::before {
  background: #64d2ff;
}

.drawdown::before {
  background: var(--bear-green);
}

.curve-body {
  display: grid;
  gap: 8px;
  padding: 10px;
}

.benchmark-warning {
  border: 1px solid rgba(255, 214, 10, 0.22);
  border-radius: 8px;
  background: rgba(255, 214, 10, 0.06);
  color: #ffd60a;
  font-size: 12px;
  padding: 9px 10px;
}

.return-host {
  height: 190px;
}

.drawdown-host {
  height: 82px;
}
</style>
