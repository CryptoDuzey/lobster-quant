<script setup>
import { Bot, BrainCircuit, Send, X } from "lucide-vue-next";
import { computed, nextTick, ref, watch } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const scroller = ref(null);

const agentChips = [
  { label: "技术面", tag: "@技术面", hint: "K线、均线、支撑压力" },
  { label: "消息面", tag: "@消息面", hint: "新闻、来源、情绪" },
  { label: "风控", tag: "@风控", hint: "波动、回撤、风险" },
  { label: "量化", tag: "@量化", hint: "回测、收益、交易" },
  { label: "策略", tag: "@策略", hint: "规则、参数、工坊" },
];

const isRadarPage = computed(() => store.state.currentPage === "radar");
const isMarketMode = computed(() => store.state.activeAssistantMode === "market");

const modeText = computed(() => {
  if (isMarketMode.value) {
    if (!store.state.agentCommittee) return "等待提问";
    return store.state.agentCommittee.provider_configured ? "当前模型 + 行情Agent" : "模型 API Key 未配置";
  }
  if (!store.state.financialAgentResult) return "金融Agent待命";
  return store.state.financialAgentResult.provider_configured ? "当前模型 + 金融Agent" : "模型 API Key 未配置";
});

const basisText = computed(() => {
  if (!isMarketMode.value) {
    const basis = store.state.financialAgentResult?.basis;
    if (!basis) return `当前页面：${pageLabel.value}`;
    return `${pageLabel.value} / 市场上下文：${basis.has_market_context ? "有" : "无"} / 回测：${basis.has_backtest_result ? "有" : "无"}`;
  }
  const basis = store.state.agentCommittee?.basis;
  if (!basis) return "等待真实行情上下文";
  return `${basis.bars_count || 0} 根K线 / ${basis.news_count || 0} 条消息 / ${basis.data_source || "未知数据源"}`;
});

const pageLabel = computed(() => {
  const map = {
    radar: "行情",
    workshop: "工坊",
    backtest: "回测",
    "backtest-lab": "回测",
    square: "广场",
    "first-class": "广场",
    "strategy-cabin": "广场",
    "ai-center": "能力中心",
  };
  return map[store.state.currentPage] || "当前页面";
});

const drawerTitle = computed(() => (isMarketMode.value ? "AI 行情助手" : "金融 Agent"));
const drawerSubtitle = computed(() => (
  isMarketMode.value
    ? `${store.state.stockName} · ${store.state.symbol} · ${modeText.value}`
    : `${pageLabel.value} · ${modeText.value}`
));
const activeMessages = computed(() => (isMarketMode.value ? store.state.committeeMessages : store.state.financialAgentMessages));
const inputModel = computed({
  get: () => (isMarketMode.value ? store.state.aiStockQuestion : store.state.financialAgentQuestion),
  set: (value) => {
    if (isMarketMode.value) store.state.aiStockQuestion = value;
    else store.state.financialAgentQuestion = value;
  },
});
const placeholderText = computed(() => (
  isMarketMode.value
    ? "问当前股票，也可以 @技术面 / @消息面 / @风控 / @量化 / @策略"
    : "自由问市场、金融人物、投资框架、策略、回测或风险；不会编造数据"
));

watch(
  () => activeMessages.value.length,
  async () => {
    await nextTick();
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  },
);

function mentionAgent(chip) {
  if (!isMarketMode.value) return;
  const text = store.state.aiStockQuestion.trim();
  if (text.includes(chip.tag)) return;
  store.state.aiStockQuestion = text ? `${chip.tag} ${text}` : `${chip.tag} `;
}

async function send() {
  const text = inputModel.value.trim();
  if (!text || store.state.loadingAIAnalysis) return;
  if (isMarketMode.value) {
    await store.runStockAnalysis(text);
    store.state.aiStockQuestion = "";
  } else {
    await store.runFinancialAgentChat(text);
    store.state.financialAgentQuestion = "";
  }
}

function handleComposerKeydown(event) {
  if (event.key !== "Enter") return;
  if (event.shiftKey) return;
  event.preventDefault();
  send();
}

function analyzeChart() {
  const context = store.state.selectedChartContext;
  const timeText = context?.time ? `，重点看 ${context.time} 附近` : "";
  store.state.aiStockQuestion = `@技术面 请分析当前 ${store.state.stockName} 的 ${store.periodLabel(store.state.period)} 走势${timeText}，结合技术结构、消息面和风险。`;
  send();
}
</script>

<template>
  <div class="floating-ai-stack" :class="{ dual: isRadarPage }">
    <button v-if="isRadarPage" class="floating-ai-button market" @click="store.openAiAssistant('', null, 'market')">
      <BrainCircuit :size="18" />
      <span>AI行情助手</span>
    </button>
    <button class="floating-ai-button finance" @click="store.openAiAssistant('', null, isRadarPage ? 'financial' : null)">
      <Bot :size="18" />
      <span>金融Agent</span>
    </button>
  </div>

  <Teleport to="body">
    <div v-if="store.state.aiAssistantOpen" class="ai-drawer-mask" @click.self="store.closeAiAssistant">
      <aside class="ai-drawer">
        <header class="drawer-head">
          <div>
            <h2><Bot :size="18" /> {{ drawerTitle }}</h2>
            <p>{{ drawerSubtitle }}</p>
          </div>
          <button class="drawer-close" @click="store.closeAiAssistant">
            <X :size="18" />
          </button>
        </header>

        <div class="drawer-context">
          <span>依据：{{ basisText }}</span>
          <button v-if="isMarketMode" @click="analyzeChart">分析当前图表</button>
        </div>

        <div v-if="isMarketMode" class="agent-chip-row">
          <button v-for="chip in agentChips" :key="chip.tag" :title="chip.hint" @click="mentionAgent(chip)">
            {{ chip.tag }}
          </button>
        </div>
        <div v-else class="agent-chip-row finance">
          <span>协调 Agent</span>
          <span>投研 Agent</span>
          <span>策略 Agent</span>
          <span>回测 Agent</span>
          <span>风控 Agent</span>
          <span>数据 Agent</span>
        </div>

        <div ref="scroller" class="drawer-chat">
          <div
            v-for="(message, index) in activeMessages"
            :key="index"
            :class="['drawer-bubble', message.role]"
          >
            <div v-if="message.agent_labels?.length" class="agent-labels">
              <span v-for="label in message.agent_labels" :key="label">{{ label }}</span>
            </div>
            <p>{{ message.content }}</p>
            <small v-if="message.basis">
              依据：{{ message.basis.bars_count || 0 }} 根K线 / {{ message.basis.news_count || 0 }} 条消息
            </small>
          </div>
        </div>

        <footer class="drawer-input">
          <textarea
            v-model="inputModel"
            :placeholder="placeholderText"
            @keydown="handleComposerKeydown"
          />
          <button :disabled="store.state.loadingAIAnalysis || !inputModel.trim()" @click="send">
            <Send v-if="!store.state.loadingAIAnalysis" :size="16" />
            <span v-else class="mini-spinner" />
            发送
          </button>
        </footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.floating-ai-stack {
  position: fixed;
  right: 18px;
  bottom: 22px;
  z-index: 36;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

.floating-ai-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  border: 1px solid rgba(100, 210, 255, 0.32);
  border-radius: 999px;
  background:
    linear-gradient(135deg, rgba(100, 210, 255, 0.2), rgba(155, 124, 255, 0.12)),
    rgba(12, 12, 18, 0.92);
  color: #dff6ff;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 900;
  padding: 0 15px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
}

.floating-ai-button.finance {
  border-color: rgba(155, 124, 255, 0.32);
  background:
    linear-gradient(135deg, rgba(155, 124, 255, 0.2), rgba(212, 175, 55, 0.1)),
    rgba(12, 12, 18, 0.92);
  color: #eee7ff;
}

.ai-drawer-mask {
  position: fixed;
  inset: 0;
  z-index: 45;
  display: flex;
  justify-content: flex-end;
  background: rgba(0, 0, 0, 0.38);
  backdrop-filter: blur(3px);
}

.ai-drawer {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr) auto;
  width: min(480px, 94vw);
  height: 100%;
  border-left: 1px solid rgba(100, 210, 255, 0.22);
  background:
    linear-gradient(140deg, rgba(100, 210, 255, 0.08), transparent 42%),
    #0b0b10;
  box-shadow: -28px 0 80px rgba(0, 0, 0, 0.52);
}

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px;
  border-bottom: 1px solid rgba(212, 175, 55, 0.1);
}

.drawer-head h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 17px;
}

.drawer-head p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.drawer-close {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid rgba(212, 175, 55, 0.16);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--gold);
  cursor: pointer;
}

.drawer-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 18px;
  border-bottom: 1px solid rgba(212, 175, 55, 0.08);
}

.drawer-context span {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.drawer-context button,
.drawer-input button,
.agent-chip-row button {
  border: 1px solid rgba(100, 210, 255, 0.24);
  border-radius: 8px;
  background: rgba(100, 210, 255, 0.08);
  color: var(--engine-cyan);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 900;
  padding: 8px 10px;
}

.agent-chip-row {
  display: flex;
  gap: 7px;
  overflow-x: auto;
  padding: 10px 18px;
  border-bottom: 1px solid rgba(212, 175, 55, 0.08);
}

.agent-chip-row button {
  flex: 0 0 auto;
  border-color: rgba(155, 124, 255, 0.24);
  background: rgba(155, 124, 255, 0.08);
  color: #d8ceff;
}

.agent-chip-row.finance span {
  flex: 0 0 auto;
  border: 1px solid rgba(155, 124, 255, 0.22);
  border-radius: 999px;
  background: rgba(155, 124, 255, 0.08);
  color: #d8ceff;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 800;
  padding: 7px 10px;
}

.drawer-chat {
  display: grid;
  align-content: start;
  gap: 10px;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px;
}

.drawer-bubble {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 12px;
  padding: 12px;
}

.drawer-bubble.user {
  justify-self: end;
  max-width: 88%;
  border-color: rgba(255, 69, 58, 0.24);
  background: rgba(255, 69, 58, 0.08);
}

.drawer-bubble.assistant {
  max-width: 94%;
  border-color: rgba(100, 210, 255, 0.22);
  background: rgba(100, 210, 255, 0.055);
}

.agent-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 8px;
}

.agent-labels span {
  border: 1px solid rgba(155, 124, 255, 0.25);
  border-radius: 999px;
  background: rgba(155, 124, 255, 0.08);
  color: #d8ceff;
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 3px 7px;
}

.drawer-bubble p {
  margin: 0;
  color: var(--text-main);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-line;
}

.drawer-bubble small {
  display: block;
  margin-top: 8px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.drawer-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 14px 18px 18px;
  border-top: 1px solid rgba(212, 175, 55, 0.1);
}

.drawer-input textarea {
  min-height: 64px;
  border: 1px solid rgba(212, 175, 55, 0.16);
  border-radius: 12px;
  outline: none;
  resize: none;
  background: rgba(6, 6, 8, 0.78);
  color: var(--text-main);
  padding: 12px;
  line-height: 1.45;
}

.drawer-input button {
  min-width: 76px;
}

.mini-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: terminal-spin 0.8s linear infinite;
}
</style>
