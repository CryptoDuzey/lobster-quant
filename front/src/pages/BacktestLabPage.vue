<script setup>
import { FileText, FlaskConical, Pencil, RefreshCcw, Trash2 } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import {
  deleteBacktestRun,
  getBacktestRun,
  listBacktestRuns,
  renameBacktestRun,
  validateBacktestResult,
} from "../api/backtestApi";
import ASharesLedger from "../components/ASharesLedger.vue";
import BacktestAiAnalysisPanel from "../components/backtest/BacktestAiAnalysisPanel.vue";
import BacktestDataSummary from "../components/backtest/BacktestDataSummary.vue";
import BacktestMetricGrid from "../components/backtest/BacktestMetricGrid.vue";
import BacktestTrustCard from "../components/backtest/BacktestTrustCard.vue";
import EquityCurveChart from "../components/backtest/EquityCurveChart.vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const runs = ref([]);
const loading = ref(false);

function isBrokenName(value) {
  const text = String(value || "").trim();
  if (!text) return true;
  const questionMarks = (text.match(/\?/g) || []).length;
  return questionMarks >= 3 || questionMarks / Math.max(text.length, 1) > 0.25 || text.includes("�");
}

function displayRunName(run) {
  const name = String(run?.strategy_name || "").trim();
  if (!isBrokenName(name)) return name;

  const haystack = JSON.stringify({
    raw: name,
    strategy_json: run?.strategy_json || {},
    time_range: run?.time_range || {},
    data_info: run?.data_info || {},
    id: run?.backtest_id || "",
  }).toLowerCase();

  if (haystack.includes("rsi")) return "RSI 策略回测";
  if (haystack.includes("boll") || haystack.includes("布林")) return "布林带策略回测";
  if (haystack.includes("factor") || String(run?.name || "").includes("股票池")) return "多因子选股策略";
  if (haystack.includes("5") && haystack.includes("20")) return "5日/20日均线策略";
  if (haystack.includes("10")) return "10日均线策略";
  return `${run?.name || run?.symbol || "A股"} 策略回测`;
}

async function loadRuns() {
  loading.value = true;
  try {
    runs.value = await listBacktestRuns(20);
  } finally {
    loading.value = false;
  }
}

async function openRun(run) {
  const result = await getBacktestRun(run.backtest_id);
  return applyRunResult(run, result, true);
}

function applyRunResult(run, result, shouldLogError = true) {
  try {
    validateBacktestResult(result);
  } catch (error) {
    if (!shouldLogError) return false;
    store.state.backtestResult = {
      success: false,
      message: error.message,
      backtest_id: run.backtest_id,
      trust_audit: result.trust_audit || { trust_level: "low", blocking_errors: [error.message] },
    };
    store.state.metrics = null;
    store.state.trades = [];
    store.pushLog("错误", error.message);
    return false;
  }
  store.state.backtestResult = result.raw || result;
  store.state.metrics = result.metrics;
  store.state.aiAudit = result.ai_audit || result.raw?.ai_audit || null;
  store.state.trades = result.trades || [];
  store.state.bars = result.bars || [];
  store.state.symbol = result.symbol || store.state.symbol;
  store.state.stockName = result.name || store.state.stockName;
  store.state.period = result.period || store.state.period;
  return true;
}

async function openFirstValidRun() {
  for (const run of runs.value) {
    const result = await getBacktestRun(run.backtest_id);
    if (applyRunResult(run, result, false)) return;
  }
  if (runs.value[0]) await openRun(runs.value[0]);
}

async function renameRun(run) {
  const currentName = displayRunName(run);
  const nextName = window.prompt("重命名回测记录", currentName);
  if (!nextName || nextName.trim() === currentName) return;
  const cleanName = nextName.trim();
  const result = await renameBacktestRun(run.backtest_id, cleanName);
  if (result?.success === false) {
    window.alert(result.message || "重命名失败");
    return;
  }
  run.strategy_name = cleanName;
  if (store.state.backtestResult?.backtest_id === run.backtest_id) {
    store.state.backtestResult.strategy_name = cleanName;
  }
}

async function removeRun(run) {
  const ok = window.confirm(`确定删除「${displayRunName(run)}」这条回测记录吗？`);
  if (!ok) return;
  const result = await deleteBacktestRun(run.backtest_id);
  if (result?.success === false) {
    window.alert(result.message || "删除失败");
    return;
  }
  const wasSelected = store.state.backtestResult?.backtest_id === run.backtest_id;
  runs.value = runs.value.filter((item) => item.backtest_id !== run.backtest_id);
  if (wasSelected) {
    store.state.backtestResult = null;
    store.state.metrics = null;
    store.state.aiAudit = null;
    store.state.trades = [];
    store.state.bars = [];
    if (runs.value[0]) await openFirstValidRun();
  }
}

onMounted(async () => {
  store.state.currentPage = "backtest-lab";
  store.stopRealtimePolling();
  await loadRuns();
  if (runs.value[0]) await openFirstValidRun();
});
</script>

<template>
  <main class="terminal-page backtest-lab-page">
    <section class="panel lab-hero">
      <div>
        <div class="terminal-label">可信回测</div>
        <h1><FlaskConical :size="26" /> 回测实验室</h1>
        <p>集中查看策略与基准的真实对比：核心指标、收益曲线、数据摘要、交易日志和可信度检查。</p>
      </div>
      <button class="terminal-button" :disabled="loading" @click="loadRuns">
        <RefreshCcw :class="{ spin: loading }" :size="15" /> 刷新记录
      </button>
    </section>

    <section class="lab-layout">
      <aside class="panel run-list">
        <header class="panel-header">
          <h2 class="panel-title"><FileText :size="15" /> 回测运行记录</h2>
          <span class="terminal-chip">{{ runs.length }} 条</span>
        </header>
        <div class="run-list-body">
          <article
            v-for="run in runs"
            :key="run.backtest_id"
            class="run-card"
            :class="{ active: store.state.backtestResult?.backtest_id === run.backtest_id }"
            role="button"
            tabindex="0"
            @click="openRun(run)"
            @keyup.enter="openRun(run)"
          >
            <div class="run-card-top">
              <strong :title="isBrokenName(run.strategy_name) ? displayRunName(run) : run.strategy_name">{{ displayRunName(run) }}</strong>
              <div class="run-actions">
                <button title="重命名" @click.stop="renameRun(run)"><Pencil :size="12" /></button>
                <button title="删除" class="danger" @click.stop="removeRun(run)"><Trash2 :size="12" /></button>
              </div>
            </div>
            <span>{{ run.name || run.symbol }} / {{ run.period }}</span>
            <span :class="Number(run.metrics?.total_return || 0) >= 0 ? 'bull' : 'bear'">
              {{ store.formatPercent(run.metrics?.total_return) }} · {{ run.created_at }}
            </span>
          </article>
          <div v-if="!runs.length" class="empty-state">暂无回测记录，请先在策略工坊执行一次回测。</div>
        </div>
      </aside>

      <div class="lab-main">
        <BacktestMetricGrid />
        <div class="curve-analysis-row">
          <div class="curve-stack">
            <EquityCurveChart />
            <BacktestDataSummary />
          </div>
          <BacktestAiAnalysisPanel />
        </div>
        <ASharesLedger />
        <BacktestTrustCard />
      </div>
    </section>
  </main>
</template>

<style scoped>
.backtest-lab-page {
  display: grid;
  gap: 8px;
}

.lab-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 46px;
  padding: 8px 12px;
  background:
    linear-gradient(135deg, rgba(63, 103, 173, 0.16), transparent 42%),
    linear-gradient(160deg, rgba(212, 175, 55, 0.08), rgba(18, 17, 21, 0.92));
}

.lab-hero h1 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  color: var(--text-main);
  font-size: 16px;
}

.lab-hero p {
  max-width: 760px;
  margin: 0;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.lab-layout {
  display: grid;
  grid-template-columns: 224px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  min-height: 0;
}

.run-list {
  position: sticky;
  top: 10px;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 100px);
  min-height: 0;
  overflow: hidden;
}

.run-list-body,
.lab-main {
  display: grid;
  gap: 8px;
  padding: 10px;
}

.run-list-body {
  max-height: calc(100vh - 154px);
  min-height: 0;
  overflow-y: auto;
  padding-right: 8px;
  scrollbar-color: rgba(212, 175, 55, 0.45) rgba(255, 255, 255, 0.04);
  scrollbar-width: thin;
}

.run-list-body::-webkit-scrollbar {
  width: 6px;
}

.run-list-body::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(212, 175, 55, 0.48);
}

.lab-main {
  padding: 0;
}

.curve-analysis-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 8px;
  align-items: stretch;
}

.curve-stack {
  display: grid;
  grid-template-rows: auto auto;
  gap: 8px;
  min-width: 0;
  align-self: stretch;
}

.curve-stack :deep(.data-summary-panel) {
  min-height: 118px;
}

.run-card {
  display: grid;
  gap: 4px;
  width: 100%;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-muted);
  cursor: pointer;
  padding: 9px;
  text-align: left;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.run-card.active,
.run-card:hover {
  border-color: rgba(212, 175, 55, 0.48);
  background: rgba(212, 175, 55, 0.08);
}

.run-card-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.run-card strong {
  color: var(--text-main);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-card span {
  font-size: 10px;
}

.run-actions {
  display: inline-flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.16s ease;
}

.run-card:hover .run-actions,
.run-card.active .run-actions,
.run-actions:focus-within {
  opacity: 1;
}

.run-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 23px;
  height: 23px;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 6px;
  background: rgba(212, 175, 55, 0.06);
  color: var(--gold);
  cursor: pointer;
}

.run-actions button:hover {
  border-color: rgba(212, 175, 55, 0.55);
  background: rgba(212, 175, 55, 0.14);
}

.run-actions button.danger {
  border-color: rgba(255, 69, 58, 0.2);
  color: var(--bull-red);
}

.run-actions button.danger:hover {
  border-color: rgba(255, 69, 58, 0.58);
  background: rgba(255, 69, 58, 0.12);
}

@media (max-width: 1100px) {
  .lab-layout {
    grid-template-columns: 1fr;
  }

  .curve-analysis-row {
    grid-template-columns: 1fr;
  }

  .run-list {
    position: static;
    max-height: none;
  }
}

@media (max-width: 700px) {
  .lab-hero {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
