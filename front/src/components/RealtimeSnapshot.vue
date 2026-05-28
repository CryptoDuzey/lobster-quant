<script setup>
import { Gauge } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const quote = computed(() => store.state.quote || {});
const priceClass = computed(() => Number(quote.value.change_pct || 0) >= 0 ? "bull" : "bear");
</script>

<template>
  <section class="panel snapshot-panel">
    <header class="panel-header">
      <h2 class="panel-title"><Gauge :size="15" /> 实时行情快照</h2>
      <span class="terminal-chip">{{ store.state.symbol }}</span>
    </header>
    <div class="snapshot-grid">
      <div class="hero-price">
        <span>{{ store.state.stockName }}</span>
        <strong :class="priceClass">{{ store.formatPrice(quote.price) }}</strong>
        <em :class="priceClass">{{ quote.change_pct == null ? "--" : `${Number(quote.change_pct).toFixed(2)}%` }}</em>
      </div>
      <div><span>今开</span><strong>{{ store.formatPrice(quote.open) }}</strong></div>
      <div><span>最高</span><strong>{{ store.formatPrice(quote.high) }}</strong></div>
      <div><span>最低</span><strong>{{ store.formatPrice(quote.low) }}</strong></div>
      <div><span>成交量</span><strong>{{ store.formatAmount(quote.volume) }}</strong></div>
      <div><span>成交额</span><strong>{{ store.formatAmount(quote.amount) }}</strong></div>
    </div>
  </section>
</template>

<style scoped>
.snapshot-panel {
  flex: 0.34;
  min-height: 154px;
}

.snapshot-grid {
  display: grid;
  grid-template-columns: minmax(160px, 1.25fr) repeat(5, minmax(86px, 1fr));
  gap: 9px;
  height: calc(100% - 45px);
  padding: 12px;
}

.snapshot-grid > div {
  display: grid;
  align-content: center;
  gap: 6px;
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.025);
  padding: 10px;
}

.snapshot-grid span {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
}

.snapshot-grid strong {
  color: var(--text-main);
  font-family: var(--font-mono);
  font-size: 15px;
}

.hero-price strong {
  font-size: 30px;
}

.hero-price em {
  font-family: var(--font-mono);
  font-size: 12px;
  font-style: normal;
  font-weight: 900;
}

@media (max-width: 980px) {
  .snapshot-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
