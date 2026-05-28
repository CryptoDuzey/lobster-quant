<script setup>
import { BrainCircuit, CircleDollarSign, TrendingDown, TrendingUp } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();

const returnClass = computed(() => {
  const value = Number(store.state.metrics?.total_return || 0);
  return value >= 0 ? "bull" : "bear";
});
</script>

<template>
  <section class="panel flash-panel">
    <header class="panel-header">
      <h2 class="panel-title"><BrainCircuit :size="15" /> 策略指标卡</h2>
      <span class="terminal-chip">{{ store.periodLabel(store.state.period) }}</span>
    </header>

    <div class="flash-body">
      <div class="metric-card hero">
        <div class="metric-label"><TrendingUp :size="14" /> 总收益率</div>
        <div class="metric-value" :class="returnClass">
          {{ store.formatPercent(store.state.metrics?.total_return) }}
        </div>
      </div>

      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label"><CircleDollarSign :size="14" /> 最新价格</div>
          <div class="metric-value">{{ store.formatPrice(store.state.quote?.price) }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">夏普率</div>
          <div class="metric-value">{{ store.formatNumber(store.state.metrics?.sharpe) }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label"><TrendingDown :size="14" /> 最大回撤</div>
          <div class="metric-value warning">
            {{ store.formatDrawdown(store.state.metrics?.max_drawdown) }}
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-label">当前股票</div>
          <div class="metric-value small">{{ store.state.stockName }} {{ store.state.symbol }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">年化收益率</div>
          <div class="metric-value small">{{ store.formatPercent(store.state.metrics?.annual_return) }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Alpha / Beta</div>
          <div class="metric-value small">{{ store.formatNumber(store.state.metrics?.alpha) }} / {{ store.formatNumber(store.state.metrics?.beta) }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">胜率</div>
          <div class="metric-value small">{{ store.formatPercent(store.state.metrics?.win_rate) }}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">交易次数</div>
          <div class="metric-value small">{{ store.state.metrics?.trade_count ?? store.state.trades.length }}</div>
        </div>
      </div>

      <div class="audit-card">
        <div class="metric-label">策略审计摘要</div>
        <p v-if="store.state.loadingAI" class="muted mono">DeepSeek 正在审计策略...</p>
        <p v-else>{{ store.state.aiAudit?.summary || "等待回测后生成策略审计" }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.flash-panel {
  flex: 1;
}

.flash-body {
  display: flex;
  height: calc(100% - 45px);
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 14px;
}

.metric-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.metric-card,
.audit-card {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 12px;
}

.metric-card.hero {
  min-height: 112px;
  display: grid;
  align-content: center;
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

.metric-value {
  margin-top: 8px;
  color: var(--text-main);
  font-family: var(--font-mono);
  font-size: 24px;
  font-weight: 900;
  line-height: 1;
  overflow-wrap: anywhere;
}

.metric-card.hero .metric-value {
  font-size: 42px;
}

.metric-value.small {
  font-size: 14px;
}

.warning {
  color: #ffd60a;
}

.audit-card p {
  margin: 9px 0 0;
  color: var(--text-main);
  font-size: 13px;
  line-height: 1.55;
}
</style>
