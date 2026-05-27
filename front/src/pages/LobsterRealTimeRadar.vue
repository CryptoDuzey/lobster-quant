<script setup>
import { onBeforeUnmount, onMounted } from "vue";
import AiStockAssistant from "../components/AiStockAssistant.vue";
import KLineChart from "../components/KLineChart.vue";
import MarketLivePanel from "../components/MarketLivePanel.vue";
import NewsFeedPanel from "../components/NewsFeedPanel.vue";
import RealtimeSnapshot from "../components/RealtimeSnapshot.vue";
import StockPoolMonitor from "../components/StockPoolMonitor.vue";
import StockSearchBox from "../components/StockSearchBox.vue";
import TickNewsFlow from "../components/TickNewsFlow.vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();

onMounted(async () => {
  store.state.currentPage = "radar";
  await store.loadMarket();
  store.startRealtimePolling();
});

onBeforeUnmount(() => {
  store.stopRealtimePolling();
});
</script>

<template>
  <main class="terminal-page radar-page">
    <div class="terminal-grid radar-grid">
      <div class="terminal-column">
        <StockPoolMonitor />
        <TickNewsFlow />
      </div>

      <div class="terminal-column">
        <section class="panel radar-search-panel">
          <StockSearchBox />
        </section>
        <KLineChart />
        <div class="radar-bottom-strip">
          <RealtimeSnapshot />
          <MarketLivePanel />
        </div>
      </div>

      <div class="terminal-column">
        <NewsFeedPanel />
        <AiStockAssistant />
      </div>
    </div>
  </main>
</template>

<style scoped>
.radar-grid {
  grid-template-columns: 210px minmax(520px, 1fr) 300px;
  align-items: stretch;
  min-height: 0;
  height: calc(100dvh - 78px);
  overflow: hidden;
}

.radar-grid .terminal-column {
  min-height: 0;
  overflow-y: auto;
}

.radar-grid .terminal-column:nth-child(2) {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) 136px;
  min-height: 0;
  overflow: visible;
}

.radar-bottom-strip {
  display: grid;
  grid-template-columns: minmax(0, 0.82fr) minmax(0, 1.18fr);
  gap: 10px;
  min-height: 0;
}

.radar-page :deep(.chart-panel) {
  min-height: 0;
  height: 100%;
}

.radar-page :deep(.chart-wrap) {
  min-height: 0;
  height: calc(100% - 77px);
}

.radar-search-panel {
  position: relative;
  z-index: 2;
  overflow: visible;
  padding: 10px;
  background:
    linear-gradient(135deg, rgba(100, 210, 255, 0.08), transparent 45%),
    linear-gradient(145deg, rgba(18, 17, 21, 0.96), rgba(6, 6, 8, 0.84));
}

.radar-page :deep(.pool-panel) {
  flex: 0 0 320px;
}

.radar-page :deep(.news-panel) {
  flex: 1 1 auto;
  min-height: 220px;
}

.radar-page :deep(.pool-body),
.radar-page :deep(.news-list),
.radar-page :deep(.market-news-list) {
  padding: 8px;
}

.radar-page :deep(.stock-row) {
  grid-template-columns: minmax(64px, 1fr) 72px 44px 22px;
  gap: 5px;
  padding: 6px;
}

.radar-page :deep(.stock-row span:nth-child(4)),
.radar-page :deep(.stock-row span:nth-child(5)) {
  display: none;
}

.radar-page :deep(.news-row) {
  grid-template-columns: 52px 44px minmax(0, 1fr);
  gap: 5px;
  padding: 6px;
}

.radar-page :deep(.news-time),
.radar-page :deep(.news-badge),
.radar-page :deep(.news-text) {
  font-size: 10px;
}

.radar-page :deep(.snapshot-panel),
.radar-page :deep(.market-live-panel) {
  min-height: 0;
  height: 100%;
}

.radar-page :deep(.snapshot-grid) {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  padding: 8px;
}

.radar-page :deep(.hero-price) {
  grid-column: span 3;
}

.radar-page :deep(.hero-price strong) {
  font-size: 20px;
}

@media (max-width: 1180px) {
  .radar-grid {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }

  .radar-grid .terminal-column,
  .radar-grid .terminal-column:nth-child(2) {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: visible;
  }

  .radar-bottom-strip {
    grid-template-columns: 1fr;
  }

  .radar-grid .terminal-column:nth-child(2) {
    order: 1;
  }

  .radar-grid .terminal-column:nth-child(1) {
    order: 2;
  }

  .radar-grid .terminal-column:nth-child(3) {
    order: 3;
  }

  .radar-grid .terminal-column :deep(.panel) {
    flex: none;
  }

  .radar-grid .terminal-column:nth-child(1) :deep(.pool-panel),
  .radar-grid .terminal-column:nth-child(1) :deep(.news-panel),
  .radar-grid .terminal-column:nth-child(1) :deep(.system-status-panel) {
    max-height: 340px;
  }

  .radar-grid .terminal-column:nth-child(1) :deep(.stock-list),
  .radar-grid .terminal-column:nth-child(1) :deep(.news-list) {
    max-height: 230px;
  }

  .radar-grid .terminal-column:nth-child(3) :deep(.panel) {
    max-height: 440px;
  }

  .radar-grid .terminal-column:nth-child(3) :deep(.news-list) {
    max-height: 320px;
  }

  .radar-page :deep(.chart-panel) {
    min-height: 500px;
    height: 500px;
  }
}

@media (max-width: 640px) {
  .radar-page :deep(.chart-panel) {
    min-height: 410px;
    height: 410px;
  }

  .radar-page :deep(.chart-wrap) {
    min-height: 340px;
  }
}
</style>
