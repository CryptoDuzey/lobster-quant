<script setup>
import { RadioTower } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();

const latestBar = computed(() => store.state.bars[store.state.bars.length - 1] || null);
const previousBar = computed(() => store.state.bars[store.state.bars.length - 2] || null);

const amplitude = computed(() => {
  const bar = latestBar.value;
  if (!bar?.close) return null;
  return ((Number(bar.high) - Number(bar.low)) / Number(bar.close)) * 100;
});

const barChange = computed(() => {
  const latest = latestBar.value;
  const previous = previousBar.value;
  if (!latest || !previous?.close) return null;
  return ((Number(latest.close) - Number(previous.close)) / Number(previous.close)) * 100;
});

const rows = computed(() => [
  { label: "K线数量", value: `${store.state.bars.length || 0} 根` },
  { label: "最近时间", value: latestBar.value?.time || "--" },
  { label: "周期", value: store.periodLabel(store.state.period) },
  { label: "数据源", value: store.state.dataSource || "--" },
  { label: "单根涨跌", value: barChange.value == null ? "--" : `${barChange.value >= 0 ? "+" : ""}${barChange.value.toFixed(2)}%`, tone: barChange.value >= 0 ? "bull" : "bear" },
  { label: "振幅", value: amplitude.value == null ? "--" : `${amplitude.value.toFixed(2)}%` },
  { label: "成交量", value: store.formatAmount(latestBar.value?.volume) },
  { label: "成交额", value: store.formatAmount(latestBar.value?.amount || store.state.quote?.amount) },
]);
</script>

<template>
  <section class="panel market-live-panel">
    <header class="panel-header">
      <h2 class="panel-title"><RadioTower :size="15" /> 实时数据更新</h2>
      <span class="terminal-chip">{{ store.state.updatedAt || "等待刷新" }}</span>
    </header>
    <div class="live-grid">
      <div v-for="item in rows" :key="item.label">
        <span>{{ item.label }}</span>
        <strong :class="item.tone">{{ item.value }}</strong>
      </div>
    </div>
  </section>
</template>

<style scoped>
.market-live-panel {
  min-height: 0;
  height: 100%;
}

.live-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  height: calc(100% - 45px);
  padding: 9px;
}

.live-grid > div {
  display: grid;
  align-content: center;
  gap: 5px;
  min-width: 0;
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.025);
  padding: 8px;
}

.live-grid span {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
}

.live-grid strong {
  overflow: hidden;
  color: var(--text-main);
  font-family: var(--font-mono);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .live-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
