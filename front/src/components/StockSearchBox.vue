<script setup>
import { Search, Sparkles } from "lucide-vue-next";
import { ref, watch } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const keyword = ref(store.state.symbol);
const items = ref([]);
const open = ref(false);
const mode = ref("classic");
const noResult = ref(false);
let timer = null;

watch(
  () => store.state.symbol,
  (value) => {
    if (!open.value) keyword.value = value;
  },
);

watch([keyword, mode], ([value, currentMode]) => {
  window.clearTimeout(timer);
  noResult.value = false;
  if (!value || String(value).trim().length < 1) {
    items.value = [];
    open.value = false;
    return;
  }
  if (currentMode !== "classic") return;
  timer = window.setTimeout(async () => {
    items.value = await store.searchStock(value);
    noResult.value = !items.value.length;
    open.value = true;
  }, 300);
});

async function choose(item) {
  keyword.value = `${item.name || ""} ${item.symbol || item.code || ""}`.trim();
  open.value = false;
  await store.switchStock(item);
}

async function submit() {
  const value = keyword.value.trim();
  if (!value) return;

  if (mode.value === "ai") {
    items.value = await store.searchStockByAI(value);
    noResult.value = !items.value.length;
    open.value = true;
    return;
  }

  if (items.value[0]) {
    await choose(items.value[0]);
    return;
  }

  try {
    store.stopRealtimePolling();
    store.setSymbol(value);
    open.value = false;
    store.pushLog("数据", `按代码切换股票：${store.state.symbol}`);
    await store.loadMarket();
    if (store.state.currentPage === "radar") store.startRealtimePolling();
  } catch (error) {
    store.setError(error.message);
  }
}
</script>

<template>
  <div class="stock-search">
    <div class="search-top">
      <label class="terminal-label">股票搜索</label>
      <div class="mode-toggle">
        <button :class="{ active: mode === 'classic' }" @click="mode = 'classic'">传统</button>
        <button :class="{ active: mode === 'ai' }" @click="mode = 'ai'">AI</button>
      </div>
    </div>

    <div class="search-box">
      <Search v-if="mode === 'classic'" :size="16" />
      <Sparkles v-else :size="16" />
      <input
        v-model="keyword"
        class="stock-input"
        :placeholder="mode === 'classic' ? '输入代码、名称、拼音首字母' : '描述概念、行业、风格或股票特征'"
        :disabled="store.state.loadingMarket || store.state.loadingSearch"
        @focus="open = items.length > 0 || noResult"
        @keyup.enter="submit"
      />
      <button class="search-submit" :disabled="store.state.loadingSearch" @click="submit">
        {{ mode === "ai" ? "AI匹配" : "切换" }}
      </button>
    </div>

    <div v-if="open" class="search-menu">
      <button v-for="item in items" :key="item.symbol || item.code" type="button" @click="choose(item)">
        <span class="stock-name">{{ item.name || "未命名股票" }}</span>
        <span class="stock-code">{{ item.symbol || item.code }}</span>
        <span class="stock-meta">{{ item.exchange || "A股" }} · {{ item.type || "股票" }}</span>
        <span class="stock-reason">{{ item.match_reason || item.reason || "候选结果" }}</span>
      </button>
      <div v-if="noResult" class="no-result">
        未找到相关股票。传统搜索请输入代码或名称；AI搜索可输入“中字头央企”“高股息银行”等描述。
      </div>
    </div>
  </div>
</template>

<style scoped>
.stock-search {
  position: relative;
  display: grid;
  gap: 6px;
  z-index: 1;
}

.search-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mode-toggle {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.025);
}

.mode-toggle button,
.search-submit {
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 900;
}

.mode-toggle button {
  height: 26px;
  padding: 0 10px;
}

.mode-toggle button.active {
  background: rgba(212, 175, 55, 0.18);
  color: var(--gold);
}

.search-box {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 40px;
  border: 1px solid rgba(212, 175, 55, 0.2);
  border-radius: 9px;
  background: rgba(6, 6, 8, 0.82);
  color: var(--gold);
  padding: 0 8px 0 12px;
}

.stock-input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-main);
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 850;
}

.stock-input::placeholder {
  color: rgba(169, 160, 160, 0.62);
}

.search-submit {
  height: 28px;
  border: 1px solid rgba(212, 175, 55, 0.2);
  border-radius: 7px;
  padding: 0 10px;
}

.search-submit:hover:not(:disabled) {
  border-color: rgba(212, 175, 55, 0.55);
  color: var(--gold);
}

.search-menu {
  position: relative;
  z-index: 1;
  width: 100%;
  max-height: 136px;
  overflow-y: auto;
  border: 1px solid rgba(212, 175, 55, 0.32);
  border-radius: 10px;
  background: rgba(15, 14, 18, 0.985);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
}

.search-menu button {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 3px 10px;
  width: 100%;
  border-bottom: 1px solid rgba(212, 175, 55, 0.08);
  background: transparent;
  color: var(--text-main);
  cursor: pointer;
  padding: 8px 10px;
  text-align: left;
}

.search-menu button:hover {
  background: rgba(212, 175, 55, 0.1);
}

.stock-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 850;
}

.stock-code {
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 900;
  text-align: right;
  white-space: nowrap;
}

.stock-meta,
.stock-reason,
.no-result {
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.45;
}

.stock-reason {
  grid-column: 1 / -1;
  color: rgba(243, 231, 224, 0.76);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.no-result {
  padding: 15px;
}

@media (max-width: 720px) {
  .search-menu {
    max-height: 220px;
  }

  .search-menu button {
    grid-template-columns: 1fr;
  }

  .stock-code {
    text-align: left;
  }
}
</style>
