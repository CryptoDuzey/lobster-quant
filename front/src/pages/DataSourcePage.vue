<script setup>
import { DatabaseZap, RefreshCcw } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { listDataSources } from "../api/dataSourceApi";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const items = ref([]);
const cache = ref({});
const loading = ref(false);

async function loadSources() {
  loading.value = true;
  try {
    const result = await listDataSources();
    items.value = result.items || [];
    cache.value = result.cache || {};
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  store.state.currentPage = "data";
  store.stopRealtimePolling();
  await loadSources();
});
</script>

<template>
  <main class="terminal-page data-page">
    <section class="panel data-hero">
      <div>
        <div class="terminal-label">Market Data Hub</div>
        <h1><DatabaseZap :size="26" /> 数据源管理</h1>
        <p>统一管理东方财富、akshare 和本地缓存。行情和基准数据都必须可溯源，不能用假数据冒充真实回测。</p>
      </div>
      <button class="terminal-button" :disabled="loading" @click="loadSources">
        <RefreshCcw :class="{ spin: loading }" :size="15" /> 刷新状态
      </button>
    </section>

    <section class="data-grid">
      <article class="panel source-panel">
        <header class="panel-header">
          <h2 class="panel-title">数据源列表</h2>
          <span class="terminal-chip">{{ items.length }} 个</span>
        </header>
        <div class="source-list">
          <div v-for="item in items" :key="item.source_name" class="source-card">
            <div>
              <strong>{{ item.display_name }}</strong>
              <span>{{ item.source_name }}</span>
            </div>
            <div>
              <span :class="item.is_enabled ? 'enabled' : 'disabled'">{{ item.is_enabled ? "已启用" : "已停用" }}</span>
              <small>优先级 {{ item.priority }} · {{ item.status }}</small>
            </div>
          </div>
        </div>
      </article>

      <article class="panel cache-panel">
        <header class="panel-header">
          <h2 class="panel-title">本地缓存</h2>
          <span class="terminal-chip">{{ cache.storage || "SQLite" }}</span>
        </header>
        <div class="cache-grid">
          <div><span>行情缓存条数</span><strong>{{ cache.market_bar_count ?? "--" }}</strong></div>
          <div><span>基准缓存条数</span><strong>{{ cache.benchmark_bar_count ?? "--" }}</strong></div>
          <div><span>缓存策略</span><strong>按需缓存</strong></div>
          <div><span>正式回测</span><strong>禁止 mock</strong></div>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.data-page {
  display: grid;
  gap: 12px;
}

.data-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 20px;
  background:
    linear-gradient(135deg, rgba(100, 210, 255, 0.14), transparent 44%),
    linear-gradient(160deg, rgba(212, 175, 55, 0.06), rgba(18, 17, 21, 0.92));
}

.data-hero h1 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0;
}

.data-hero p {
  color: var(--text-muted);
  line-height: 1.7;
}

.data-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.42fr);
  gap: 12px;
}

.source-list,
.cache-grid {
  display: grid;
  gap: 10px;
  padding: 14px;
}

.source-card,
.cache-grid div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 12px;
}

.source-card strong,
.cache-grid strong {
  display: block;
  color: var(--text-main);
}

.source-card span,
.source-card small,
.cache-grid span {
  color: var(--text-muted);
  font-size: 12px;
}

.enabled {
  color: var(--bull-red) !important;
}

.disabled {
  color: var(--bear-green) !important;
}

@media (max-width: 900px) {
  .data-grid {
    grid-template-columns: 1fr;
  }

  .data-hero {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
