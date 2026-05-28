<script setup>
import { Newspaper, RefreshCcw } from "lucide-vue-next";
import { computed, ref } from "vue";
import { getMarketNews } from "../api/newsApi";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const mode = ref("stock");
const marketItems = ref([]);
const loadingMarketNews = ref(false);
const visibleNews = computed(() => (mode.value === "market" ? marketItems.value : store.state.news));

async function refresh() {
  if (mode.value === "stock") {
    await store.refreshNews();
    return;
  }
  loadingMarketNews.value = true;
  try {
    const result = await getMarketNews("");
    marketItems.value = result.items || [];
    store.pushLog("消息", `${result.source || "市场消息"}返回 ${marketItems.value.length} 条市场消息`);
  } catch (error) {
    store.setError(`市场消息刷新失败：${error.message}`);
  } finally {
    loadingMarketNews.value = false;
  }
}
</script>

<template>
  <section class="panel market-news-panel">
    <header class="panel-header">
      <h2 class="panel-title"><Newspaper :size="15" /> 实时消息面</h2>
      <div class="news-actions">
        <button :class="{ active: mode === 'stock' }" @click="mode = 'stock'">个股</button>
        <button :class="{ active: mode === 'market' }" @click="mode = 'market'">市场</button>
        <button class="small-action" :disabled="store.state.loadingNews || loadingMarketNews" @click="refresh">
          <RefreshCcw :class="{ spin: store.state.loadingNews || loadingMarketNews }" :size="14" /> 刷新
        </button>
      </div>
    </header>

    <div class="market-news-list">
      <article v-for="item in visibleNews" :key="`${item.title}-${item.time}`" class="news-card">
        <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">{{ item.title }}</a>
        <strong v-else>{{ item.title }}</strong>
        <p>{{ item.summary }}</p>
        <div class="news-meta">
          <span>{{ item.source }}</span>
          <span>{{ item.time || "刚刚" }}</span>
        </div>
      </article>
      <div v-if="!(store.state.loadingNews || loadingMarketNews) && !visibleNews.length" class="empty-state">
        暂无相关消息
      </div>
      <div v-if="(store.state.loadingNews || loadingMarketNews) && !visibleNews.length" class="empty-state">
        正在刷新消息面
      </div>
    </div>
  </section>
</template>

<style scoped>
.market-news-panel {
  flex: 1.05;
}

.news-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.news-actions > button:not(.small-action),
.small-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--gold);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 0 8px;
}

.news-actions > button:not(.small-action).active {
  border-color: rgba(212, 175, 55, 0.44);
  background: rgba(212, 175, 55, 0.12);
  color: var(--gold);
}

.market-news-list {
  display: grid;
  align-content: start;
  gap: 9px;
  height: calc(100% - 45px);
  overflow-y: auto;
  padding: 12px;
}

.news-card {
  border: 1px solid rgba(212, 175, 55, 0.11);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.025);
  padding: 11px;
}

.news-card a,
.news-card strong {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
  text-decoration: none;
}

.news-card a:hover {
  color: var(--gold);
}

.news-card p {
  display: -webkit-box;
  margin: 8px 0 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.news-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-top: 9px;
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
}
</style>
