<script setup>
import { Bot, BrainCircuit, MessageSquareText } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();

const modelState = computed(() => {
  if (!store.state.agentCommittee) return "等待调用";
  return store.state.agentCommittee.provider_configured ? "当前模型已连接" : "模型 API Key 未配置";
});

function openAssistant() {
  store.openAiAssistant(`请分析当前 ${store.state.stockName} 的走势、消息面和主要风险。`);
}
</script>

<template>
  <section class="panel ai-status-panel">
    <header class="panel-header">
      <h2 class="panel-title"><Bot :size="15" /> AI 能力概览</h2>
      <span class="terminal-chip">{{ modelState }}</span>
    </header>

    <div class="ai-status-body">
      <div class="agent-chip-row">
        <span>技术面 Agent</span>
        <span>消息面 Agent</span>
        <span>量化 Skill</span>
        <span>风控 Agent</span>
      </div>

      <div class="ai-summary">
        <strong>{{ store.state.agentCommittee?.final_summary || "AI 助手不会常驻占用主屏，点击按钮后基于当前股票、K线、消息面继续对话。" }}</strong>
        <p v-if="store.state.agentCommittee?.basis">
          依据：{{ store.state.agentCommittee.basis.bars_count || 0 }} 根K线 /
          {{ store.state.agentCommittee.basis.news_count || 0 }} 条消息
        </p>
      </div>

      <div class="ai-status-actions">
        <button class="terminal-button" @click="openAssistant">
          <MessageSquareText :size="14" /> 打开 AI 助手
        </button>
        <button class="terminal-button" @click="store.openAiAssistant(`请分析当前图表，并指出关键支撑、压力和风险。`)">
          <BrainCircuit :size="14" /> 分析图表
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ai-status-panel {
  flex: 0 0 210px;
}

.ai-status-body {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.agent-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.agent-chip-row span {
  border: 1px solid rgba(100, 210, 255, 0.18);
  border-radius: 999px;
  background: rgba(100, 210, 255, 0.055);
  color: var(--engine-cyan);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 5px 8px;
}

.ai-summary {
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 10px;
}

.ai-summary strong {
  display: block;
  color: var(--text-main);
  font-size: 12px;
  line-height: 1.55;
}

.ai-summary p {
  margin: 7px 0 0;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.ai-status-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
</style>
