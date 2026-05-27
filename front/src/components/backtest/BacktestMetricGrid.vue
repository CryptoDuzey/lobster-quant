<script setup>
import { BarChart3, Percent, TrendingDown, TrendingUp } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../../stores/useMarketStore";

const store = useMarketStore();

const metrics = computed(() => store.state.metrics || {});
const benchmark = computed(() => store.state.backtestResult?.benchmark || {});
const benchmarkCurve = computed(() => store.state.backtestResult?.curves?.benchmark_curve || []);

const benchmarkReturn = computed(() => {
  const last = benchmarkCurve.value[benchmarkCurve.value.length - 1];
  const value = Number(last?.value);
  return Number.isFinite(value) ? value : null;
});

function directionKind(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number >= 0 ? "bull" : "bear";
}

const cards = computed(() => [
  {
    label: "基准收益",
    value: benchmarkReturn.value == null ? "--" : store.formatPercent(benchmarkReturn.value),
    kind: directionKind(benchmarkReturn.value),
    icon: Percent,
    tone: "benchmark",
  },
  {
    label: "累计收益",
    value: store.formatPercent(metrics.value.total_return),
    kind: directionKind(metrics.value.total_return),
    icon: TrendingUp,
    tone: "primary",
  },
  { label: "Alpha", value: store.formatNumber(metrics.value.alpha), kind: directionKind(metrics.value.alpha), icon: BarChart3, tone: "agent" },
  { label: "Beta", value: store.formatNumber(metrics.value.beta), kind: "", icon: BarChart3, tone: "agent" },
  { label: "Sharpe", value: store.formatNumber(metrics.value.sharpe), kind: directionKind(metrics.value.sharpe), icon: BarChart3, tone: "agent" },
  { label: "最大回撤", value: store.formatDrawdown(metrics.value.max_drawdown), kind: "warning", icon: TrendingDown },
  {
    label: "年化收益",
    value: store.formatPercent(metrics.value.annual_return),
    kind: directionKind(metrics.value.annual_return),
    icon: Percent,
  },
]);
</script>

<template>
  <section class="panel metric-panel">
    <header class="panel-header">
      <h2 class="panel-title"><BarChart3 :size="15" /> 策略与基准核心指标</h2>
      <span class="terminal-chip">
        基准：{{ benchmark.name || benchmark.symbol || "未设置" }}
      </span>
    </header>

    <div v-if="!store.state.metrics" class="empty-state">
      等待回测结果。
    </div>
    <div v-else class="metric-grid">
      <article v-for="card in cards" :key="card.label" class="metric-card" :class="card.tone">
        <span class="metric-label"><component :is="card.icon" :size="13" /> {{ card.label }}</span>
        <strong :class="card.kind">{{ card.value }}</strong>
      </article>
    </div>
  </section>
</template>

<style scoped>
.metric-panel {
  min-height: 142px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 9px;
  padding: 11px;
}

.metric-card {
  min-height: 74px;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.024);
  padding: 10px;
}

.metric-card.primary {
  border-color: rgba(255, 69, 58, 0.28);
  background: linear-gradient(180deg, rgba(255, 69, 58, 0.09), rgba(255, 255, 255, 0.018));
}

.metric-card.benchmark {
  border-color: rgba(100, 210, 255, 0.24);
  background: linear-gradient(180deg, rgba(100, 210, 255, 0.075), rgba(255, 255, 255, 0.018));
}

.metric-card.agent {
  border-color: rgba(155, 124, 255, 0.22);
  background: linear-gradient(180deg, rgba(155, 124, 255, 0.075), rgba(255, 255, 255, 0.018));
}

.metric-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
}

strong {
  display: block;
  margin-top: 10px;
  color: var(--text-main);
  font-family: var(--font-mono);
  font-size: 21px;
  line-height: 1;
  overflow-wrap: anywhere;
}

.bull {
  color: var(--bull-red);
}

.bear {
  color: var(--bear-green);
}

.warning {
  color: #ffd60a;
}

@media (max-width: 1180px) {
  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
