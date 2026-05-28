<script setup>
import { Play, Save, SlidersHorizontal } from "lucide-vue-next";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const periods = [
  ["1m", "1分"],
  ["5m", "5分"],
  ["15m", "15分"],
  ["30m", "30分"],
  ["60m", "60分"],
  ["day", "日线"],
];

async function switchPeriod(period) {
  if (period === store.state.period) return;
  store.setPeriod(period);
  await store.loadMarket();
}

function saveStrategy() {
  store.saveCurrentStrategy();
}
</script>

<template>
  <section class="panel research-panel">
    <header class="panel-header">
      <h2 class="panel-title"><SlidersHorizontal :size="15" /> 龙虾投研工坊</h2>
      <span class="terminal-chip">{{ store.state.symbol }}</span>
    </header>

    <div class="research-body">
      <div class="date-grid">
        <label>
          <span class="terminal-label">开始日期</span>
          <input v-model="store.state.startDate" class="terminal-input" type="date" />
        </label>
        <label>
          <span class="terminal-label">结束日期</span>
          <input v-model="store.state.endDate" class="terminal-input" type="date" />
        </label>
      </div>

      <div class="period-switch">
        <button
          v-for="[value, label] in periods"
          :key="value"
          class="period-button"
          :class="{ active: store.state.period === value }"
          :disabled="store.state.loadingMarket || store.state.loadingBacktest"
          @click="switchPeriod(value)"
        >
          {{ label }}
        </button>
      </div>

      <label>
        <span class="terminal-label">买入条件</span>
        <textarea v-model="store.state.buyIdea" class="terminal-textarea" />
      </label>

      <label>
        <span class="terminal-label">卖出条件</span>
        <textarea v-model="store.state.sellIdea" class="terminal-textarea" />
      </label>

      <label>
        <span class="terminal-label">风控条件</span>
        <textarea v-model="store.state.riskIdea" class="terminal-textarea risk-box" />
      </label>

      <div v-if="store.state.error" class="error-banner">
        {{ store.state.error }}
      </div>

      <div class="button-row">
        <button
          class="terminal-button primary"
          :disabled="store.state.loadingBacktest"
          @click="store.runBacktest"
        >
          <Play v-if="!store.state.loadingBacktest" :size="15" />
          <span v-else class="mini-spinner" />
          {{ store.state.loadingBacktest ? "回测中" : "开始回测" }}
        </button>
        <button class="terminal-button" @click="saveStrategy">
          <Save :size="15" />
          保存
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.research-panel {
  flex: 1.05;
}

.research-body {
  display: flex;
  height: calc(100% - 45px);
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 14px;
}

label {
  display: grid;
  gap: 6px;
}

.date-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.risk-box {
  min-height: 56px;
}

.button-row {
  display: grid;
  grid-template-columns: 1fr 92px;
  gap: 10px;
  margin-top: auto;
}

.mini-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: terminal-spin 0.8s linear infinite;
}
</style>
