<script setup>
import { Radio, Rss } from "lucide-vue-next";
import { nextTick, ref, watch } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const scroller = ref(null);

const levelClass = {
  完成: "sync",
  数据: "gold",
  图表: "gold",
  系统: "risk",
  风控: "risk",
  引擎: "engine",
  AI: "engine",
  错误: "error",
};

watch(
  () => store.state.logs.length,
  async () => {
    await nextTick();
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  },
);
</script>

<template>
  <section class="panel news-panel">
    <header class="panel-header">
      <h2 class="panel-title"><Rss :size="15" /> 实时日志流</h2>
      <span class="live-pill"><Radio :size="13" /> 实时</span>
    </header>

    <div ref="scroller" class="news-list">
      <div v-if="!store.state.logs.length" class="empty-state">
        等待行情信号
      </div>
      <div
        v-for="log in store.state.logs"
        :key="log.id"
        class="news-row"
        :class="levelClass[log.level] || 'gold'"
      >
        <span class="news-time">[{{ log.time }}]</span>
        <span class="news-badge">{{ log.level }}</span>
        <span class="news-text">{{ log.message }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.news-panel {
  flex: 1;
}

.live-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--bear-green);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
}

.news-list {
  display: flex;
  height: calc(100% - 45px);
  flex-direction: column;
  gap: 9px;
  overflow-y: auto;
  padding: 12px;
  scroll-behavior: smooth;
}

.news-row {
  display: grid;
  grid-template-columns: 78px 72px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  border-left: 2px solid var(--gold);
  background: rgba(255, 255, 255, 0.02);
  padding: 7px 8px;
  animation: row-in 0.2s ease-out;
}

.news-time,
.news-badge,
.news-text {
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.35;
}

.news-time {
  color: var(--text-muted);
}

.news-badge {
  display: inline-flex;
  justify-content: center;
  border-radius: 4px;
  padding: 1px 5px;
  color: #050505;
  font-weight: 900;
}

.news-text {
  min-width: 0;
  color: var(--text-main);
  overflow-wrap: anywhere;
}

.sync {
  border-color: var(--bear-green);
}

.sync .news-badge {
  background: var(--bear-green);
}

.result {
  border-color: var(--gold);
}

.result .news-badge,
.gold .news-badge {
  background: var(--gold);
}

.risk,
.error {
  border-color: var(--bull-red);
}

.risk .news-badge,
.error .news-badge {
  background: var(--bull-red);
  color: #fff;
}

.engine {
  border-color: var(--engine-cyan);
}

.engine .news-badge {
  background: var(--engine-cyan);
}

.error {
  box-shadow: inset 0 0 18px rgba(255, 69, 58, 0.08);
}

@keyframes row-in {
  from {
    opacity: 0;
    transform: translateY(5px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
