<script setup>
import { BrainCircuit, RefreshCcw } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../../stores/useMarketStore";

const store = useMarketStore();

const audit = computed(() => store.state.aiAudit || store.state.backtestResult?.ai_audit || null);
const risks = computed(() => audit.value?.risks || []);
const suggestions = computed(() => audit.value?.suggestions || []);
const strengths = computed(() => audit.value?.strengths || []);

async function analyze() {
  if (!store.state.backtestResult || store.state.loadingAI) return;
  await store.runAudit();
}
</script>

<template>
  <section class="panel ai-backtest-panel">
    <header class="panel-header">
      <h2 class="panel-title"><BrainCircuit :size="15" /> AI 回测分析</h2>
      <button class="mini-button" :disabled="store.state.loadingAI || !store.state.backtestResult" @click="analyze">
        <RefreshCcw :class="{ spin: store.state.loadingAI }" :size="13" />
        {{ store.state.loadingAI ? "分析中" : "重新分析" }}
      </button>
    </header>

    <div v-if="!store.state.backtestResult" class="empty-state compact">
      暂无回测结果。
    </div>
    <div v-else-if="!audit" class="analysis-empty">
      <p>点击“重新分析”，让 AI 基于当前真实回测指标、交易记录和行情数据做一次复盘。</p>
      <button class="terminal-button primary" :disabled="store.state.loadingAI" @click="analyze">
        生成分析
      </button>
    </div>
    <div v-else class="analysis-body">
      <p class="summary">{{ audit.summary || "AI 已完成分析，但没有返回摘要。" }}</p>

      <div v-if="strengths.length" class="analysis-section">
        <strong>有效点</strong>
        <span v-for="item in strengths" :key="item">{{ item }}</span>
      </div>

      <div v-if="risks.length" class="analysis-section warning">
        <strong>风险点</strong>
        <span v-for="item in risks" :key="item">{{ item }}</span>
      </div>

      <div v-if="suggestions.length" class="analysis-section">
        <strong>优化建议</strong>
        <span v-for="item in suggestions" :key="item">{{ item }}</span>
      </div>

      <div v-if="audit.score != null" class="score-line">
        策略质量评分：<b>{{ audit.score }}</b>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ai-backtest-panel {
  min-height: 330px;
}

.mini-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  border: 1px solid rgba(100, 210, 255, 0.22);
  border-radius: 999px;
  background: rgba(100, 210, 255, 0.06);
  color: var(--engine-cyan);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 0 10px;
}

.analysis-empty,
.analysis-body {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.analysis-empty p,
.summary {
  margin: 0;
  color: var(--text-main);
  font-size: 13px;
  line-height: 1.65;
}

.analysis-section {
  display: grid;
  gap: 7px;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.022);
  padding: 10px;
}

.analysis-section.warning {
  border-color: rgba(255, 69, 58, 0.18);
  background: rgba(255, 69, 58, 0.045);
}

.analysis-section strong {
  color: var(--gold);
  font-size: 12px;
}

.analysis-section span {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.score-line {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.score-line b {
  color: var(--gold);
  font-size: 18px;
}
</style>
