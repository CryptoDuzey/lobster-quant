<script setup>
import { MessagesSquare } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();

const risks = computed(() => store.state.aiAudit?.risks || []);
const suggestions = computed(() => store.state.aiAudit?.suggestions || []);
</script>

<template>
  <section class="panel debate-panel">
    <header class="panel-header">
      <h2 class="panel-title"><MessagesSquare :size="15" /> 策略审计</h2>
      <span class="terminal-chip">AI</span>
    </header>

    <div class="debate-body">
      <div class="agent-lane">
        <div class="agent-name risk">风险审计</div>
        <p v-if="!risks.length">等待模型风险审计</p>
        <p v-for="risk in risks" :key="risk">{{ risk }}</p>
      </div>
      <div class="agent-lane">
        <div class="agent-name">优化建议</div>
        <p v-if="!suggestions.length">等待参数优化建议</p>
        <p v-for="suggestion in suggestions" :key="suggestion">{{ suggestion }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.debate-panel {
  flex: 0.78;
  min-height: 230px;
}

.debate-body {
  display: grid;
  height: calc(100% - 45px);
  gap: 10px;
  overflow-y: auto;
  padding: 14px;
}

.agent-lane {
  border-left: 2px solid var(--gold);
  background: rgba(212, 175, 55, 0.045);
  padding: 10px 12px;
}

.agent-name {
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  margin-bottom: 8px;
}

.agent-name.risk {
  color: var(--bull-red);
}

p {
  margin: 0 0 8px;
  color: var(--text-main);
  font-size: 12px;
  line-height: 1.5;
}
</style>
