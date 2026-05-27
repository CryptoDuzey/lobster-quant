<script setup>
import { computed } from "vue";
import { useMarketStore } from "../../stores/useMarketStore";

const store = useMarketStore();

const result = computed(() => store.state.backtestResult || null);
const timeRange = computed(() => result.value?.time_range || {});
const dataInfo = computed(() => result.value?.data_info || {});
const benchmark = computed(() => result.value?.benchmark || {});
const engineInfo = computed(() => result.value?.engine_info || {});
const costModel = computed(() => engineInfo.value?.cost_model || {});
const executionModel = computed(() => engineInfo.value?.execution_model || {});

function valueOrDash(value) {
  return value === undefined || value === null || value === "" ? "--" : value;
}

function shortDate(value) {
  return value ? String(value).slice(0, 10) : "--";
}

function compactSource(value) {
  const raw = String(value || "--");
  return raw.replace("akshare-", "").replace("eastmoney", "东方财富").replace("sina", "新浪");
}

function executionLabel() {
  const precision = executionModel.value?.precision;
  const label = String(executionModel.value?.label || "");
  if (precision === "intraday" || label.includes("分钟")) return "分钟撮合";
  if (precision === "daily_estimated" || result.value?.period === "day" || label.includes("日线")) return "日线估算";
  return label || "标准撮合";
}

const cards = computed(() => [
  {
    label: "对象",
    value: result.value ? `${result.value.name || store.state.stockName}` : "--",
    sub: result.value?.symbol || store.state.symbol,
  },
  {
    label: "区间",
    value: `${shortDate(timeRange.value.actual_start)} 至 ${shortDate(timeRange.value.actual_end)}`,
    sub: `${valueOrDash(timeRange.value.bars_count)} 根行情`,
  },
  {
    label: "数据",
    value: dataInfo.value.is_mock ? "非正式" : "真实数据",
    sub: `${compactSource(dataInfo.value.data_source)} · ${valueOrDash(dataInfo.value.adjust)}`,
    warn: dataInfo.value.is_mock,
  },
  {
    label: "基准",
    value: benchmark.value.available ? benchmark.value.name || "沪深300" : "不可用",
    sub: benchmark.value.available ? `${valueOrDash(benchmark.value.bars_count)} 根` : "未展示基准线",
    warn: !benchmark.value.available,
  },
  {
    label: "成本",
    value: `佣金 ${valueOrDash(costModel.value.commission)}`,
    sub: `滑点 ${valueOrDash(costModel.value.slippage)} · T+1`,
  },
  {
    label: "成交",
    value: executionLabel(),
    sub: result.value?.period === "day" ? "日线信号近似" : "按周期撮合",
    warn: result.value?.period === "day",
  },
]);
</script>

<template>
  <section class="panel data-summary-panel">
    <header class="summary-head">
      <h2>回测数据摘要</h2>
      <span :class="['summary-pill', dataInfo.is_mock ? 'danger' : '']">
        {{ dataInfo.is_mock ? "非正式数据" : "真实数据" }}
      </span>
    </header>

    <div v-if="!result" class="empty-state compact">暂无回测结果</div>
    <div v-else-if="result.success === false" class="summary-error">
      <b>Error</b>
      <span>{{ result.message || "本次回测失败" }}</span>
    </div>
    <div v-else class="summary-strip">
      <div v-for="item in cards" :key="item.label" :class="{ warn: item.warn }" :title="`${item.label}: ${item.value} ${item.sub}`">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.sub }}</small>
      </div>
    </div>
  </section>
</template>

<style scoped>
.data-summary-panel {
  min-height: 118px;
  border-color: rgba(212, 175, 55, 0.14);
  background:
    radial-gradient(circle at 10% 0%, rgba(100, 210, 255, 0.09), transparent 32%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.055), rgba(255, 255, 255, 0.018)),
    rgba(12, 12, 15, 0.72);
  backdrop-filter: blur(18px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045), 0 18px 46px rgba(0, 0, 0, 0.22);
  overflow: hidden;
}

.summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid rgba(212, 175, 55, 0.09);
  padding: 10px 14px 8px;
}

.summary-head h2 {
  margin: 0;
  color: var(--text-main);
  font-size: 13px;
  font-weight: 900;
  letter-spacing: 0;
}

.summary-pill {
  border: 1px solid rgba(50, 215, 75, 0.22);
  border-radius: 999px;
  background: rgba(50, 215, 75, 0.075);
  color: var(--bear-green);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 5px 9px;
  white-space: nowrap;
}

.summary-pill.danger {
  border-color: rgba(255, 69, 58, 0.26);
  background: rgba(255, 69, 58, 0.08);
  color: var(--bull-red);
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  padding: 10px 12px 12px;
}

.summary-strip div {
  min-width: 0;
  min-height: 66px;
  border: 1px solid rgba(212, 175, 55, 0.11);
  border-radius: 10px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.052), rgba(255, 255, 255, 0.015)),
    rgba(10, 10, 12, 0.42);
  padding: 9px 10px;
}

.summary-strip div.warn {
  border-color: rgba(255, 214, 10, 0.28);
  background:
    linear-gradient(145deg, rgba(255, 214, 10, 0.08), rgba(255, 255, 255, 0.012)),
    rgba(10, 10, 12, 0.5);
}

.summary-strip span {
  display: block;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 800;
}

.summary-strip strong {
  display: block;
  margin-top: 6px;
  overflow: hidden;
  color: var(--text-main);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-strip small {
  display: block;
  margin-top: 5px;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-error {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 12px 12px;
  border: 1px solid rgba(255, 69, 58, 0.34);
  border-radius: 10px;
  background: rgba(255, 69, 58, 0.08);
  color: #ffd1ce;
  padding: 12px;
}

.summary-error b {
  color: var(--bull-red);
  font-family: var(--font-mono);
}

.compact {
  min-height: 60px;
}

@media (max-width: 1380px) {
  .summary-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
