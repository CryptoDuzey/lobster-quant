<script setup>
import { Layers3, Plus, Star, X } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();

const poolTabs = computed(() => [
  ...store.state.stockPools.map((pool) => ({ id: pool.id, name: pool.name })),
  { id: "ai-search", name: "AI 搜索" },
  { id: "recent", name: "最近查看" },
]);

const pool = computed(() => store.selectedPool());

async function chooseStock(item) {
  await store.switchStock(item);
}

function addCurrent() {
  store.addToWatchlist({
    symbol: store.state.symbol,
    name: store.state.stockName,
    price: store.state.quote?.price,
    change_pct: store.state.quote?.change_pct,
    amount: store.state.quote?.amount,
  });
}

function toggleRow(item) {
  store.toggleWatchlist(item);
}
</script>

<template>
  <section class="panel pool-panel">
    <header class="panel-header">
      <h2 class="panel-title"><Layers3 :size="15" /> 股票池与板块监控</h2>
      <div class="pool-actions">
        <button class="mini-icon add" title="加入当前股票到自选" @click="addCurrent">
          <Plus :size="13" />
        </button>
        <span class="terminal-chip">{{ pool.items.length }} 只</span>
      </div>
    </header>

    <div class="pool-body">
      <div class="pool-tabs">
        <button
          v-for="tab in poolTabs"
          :key="tab.id"
          :class="{ active: store.state.selectedPoolId === tab.id }"
          @click="store.selectPool(tab.id)"
        >
          {{ tab.name }}
        </button>
      </div>

      <div class="pool-title">
        <strong>{{ pool.name }}</strong>
        <span>{{ pool.description }}</span>
      </div>

      <div class="stock-list">
        <button
          v-for="item in pool.items"
          :key="item.symbol"
          class="stock-row"
          :class="{ active: item.symbol === store.state.symbol }"
          @click="chooseStock(item)"
        >
          <span class="stock-name">{{ item.name }}</span>
          <span class="stock-code">{{ item.symbol }}</span>
          <span :class="Number(item.change_pct || 0) >= 0 ? 'bull' : 'bear'">
            {{ item.change_pct == null ? "--" : `${Number(item.change_pct).toFixed(2)}%` }}
          </span>
          <span>{{ item.price == null ? "--" : store.formatPrice(item.price) }}</span>
          <span class="heat">热度 {{ item.heat ?? "--" }}</span>
          <span class="row-star" :class="{ active: store.isInWatchlist(item.symbol) }" @click.stop="toggleRow(item)">
            <X v-if="store.state.selectedPoolId === 'watchlist'" :size="13" />
            <Star v-else :size="13" />
          </span>
        </button>
        <div v-if="!pool.items.length" class="empty-state">
          暂无股票，请先使用顶部 AI 搜索生成候选池
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.pool-panel {
  flex: 1.05;
  min-height: 260px;
}

.pool-body {
  display: flex;
  height: calc(100% - 45px);
  min-height: 0;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
}

.pool-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.mini-icon {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 1px solid rgba(212, 175, 55, 0.24);
  border-radius: 999px;
  background: rgba(212, 175, 55, 0.08);
  color: var(--gold);
  cursor: pointer;
}

.mini-icon:hover {
  border-color: rgba(212, 175, 55, 0.58);
  background: rgba(212, 175, 55, 0.14);
}

.pool-tabs {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.pool-tabs button {
  flex: 0 0 auto;
  height: 28px;
  border: 1px solid rgba(212, 175, 55, 0.14);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-muted);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 0 9px;
}

.pool-tabs button.active,
.pool-tabs button:hover {
  border-color: rgba(212, 175, 55, 0.52);
  background: rgba(212, 175, 55, 0.12);
  color: var(--gold);
}

.pool-title {
  display: grid;
  gap: 4px;
}

.pool-title strong {
  font-family: var(--font-display);
  font-size: 18px;
}

.pool-title span {
  color: var(--text-muted);
  font-size: 12px;
}

.stock-list {
  display: grid;
  align-content: start;
  gap: 7px;
  min-height: 0;
  overflow-y: auto;
}

.stock-row {
  display: grid;
  grid-template-columns: minmax(70px, 1fr) 96px 54px 52px 54px 24px;
  align-items: center;
  gap: 7px;
  width: 100%;
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-main);
  cursor: pointer;
  padding: 9px;
  text-align: left;
}

.stock-row:hover,
.stock-row.active {
  border-color: rgba(255, 69, 58, 0.38);
  background: rgba(255, 69, 58, 0.08);
}

.stock-name {
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stock-code,
.stock-row span {
  font-family: var(--font-mono);
  font-size: 10px;
}

.stock-code,
.heat {
  color: var(--text-muted);
}

.row-star {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  color: var(--text-muted);
}

.row-star.active,
.row-star:hover {
  background: rgba(212, 175, 55, 0.12);
  color: var(--gold);
}

@media (max-width: 1180px) {
  .stock-row {
    grid-template-columns: minmax(90px, 1fr) 96px 54px;
  }

  .stock-row span:nth-last-child(-n + 3) {
    display: none;
  }
}
</style>
