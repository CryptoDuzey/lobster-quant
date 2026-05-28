<script setup>
import { Activity, DatabaseZap, Radio } from "lucide-vue-next";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
</script>

<template>
  <section class="panel system-status-panel">
    <header class="panel-header">
      <h2 class="panel-title"><Activity :size="15" /> 系统状态</h2>
      <span class="terminal-chip">{{ store.state.pollingActive ? "轮询中" : "待机" }}</span>
    </header>

    <div class="status-grid">
      <div>
        <Radio :size="14" />
        <span>行情轮询</span>
        <strong>{{ store.state.pollingActive ? "运行中" : "已停止" }}</strong>
      </div>
      <div>
        <DatabaseZap :size="14" />
        <span>数据来源</span>
        <strong>{{ store.state.dataSource || "真实接口" }}</strong>
      </div>
      <div>
        <span>延迟</span>
        <strong>{{ store.state.latencyMs == null ? "--" : `${store.state.latencyMs}ms` }}</strong>
      </div>
      <div>
        <span>更新时间</span>
        <strong>{{ store.state.updatedAt ? store.state.updatedAt.slice(-8) : "--" }}</strong>
      </div>
    </div>
  </section>
</template>

<style scoped>
.system-status-panel {
  flex: 0.34;
  min-height: 160px;
}

.status-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
  height: calc(100% - 45px);
  padding: 12px;
}

.status-grid > div {
  display: grid;
  align-content: center;
  gap: 5px;
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 9px;
}

.status-grid strong {
  color: var(--gold);
  font-size: 12px;
  overflow-wrap: anywhere;
}
</style>
