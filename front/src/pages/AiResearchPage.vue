<script setup>
import { Bot, BrainCircuit, RefreshCcw, Send } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { runMarketWatchCommittee } from "../api/agentsApi";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const question = ref("请从技术面、消息面和风险角度分析当前股票。");
const loading = ref(false);

async function runResearch() {
  loading.value = true;
  try {
    const result = await runMarketWatchCommittee({
      symbol: store.state.symbol,
      name: store.state.stockName,
      question: question.value,
      period: store.state.period,
      quote: store.state.quote || {},
      bars: store.state.bars || [],
      news: store.state.news || [],
    });
    store.state.agentCommittee = result;
    store.pushLog("AI", "AI 投研委员会已完成个股分析");
  } catch (error) {
    store.pushLog("错误", `AI 投研失败：${error.message}`);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  store.state.currentPage = "ai-research";
  store.stopRealtimePolling();
  if (!store.state.bars.length) await store.loadMarket({ keepBacktest: true });
});
</script>

<template>
  <main class="terminal-page research-page">
    <section class="panel research-hero">
      <div>
        <div class="terminal-label">AI Analysis</div>
        <h1><BrainCircuit :size="26" /> AI 投研</h1>
        <p>面向 A 股的投研委员会：技术面、消息面、风控、多头、空头和综合结论都基于当前股票上下文生成。</p>
      </div>
      <button class="terminal-button primary" :disabled="loading" @click="runResearch">
        <RefreshCcw :class="{ spin: loading }" :size="15" /> 生成分析
      </button>
    </section>

    <section class="research-grid">
      <article class="panel prompt-panel">
        <header class="panel-header">
          <h2 class="panel-title"><Send :size="15" /> 投研问题</h2>
          <span class="terminal-chip">{{ store.state.stockName }} {{ store.state.symbol }}</span>
        </header>
        <div class="prompt-body">
          <textarea v-model="question" class="terminal-textarea" />
          <button class="terminal-button primary" :disabled="loading" @click="runResearch">
            <Bot :size="15" /> AI 分析
          </button>
        </div>
      </article>

      <article class="panel committee-panel">
        <header class="panel-header">
          <h2 class="panel-title"><BrainCircuit :size="15" /> AI 投研委员会</h2>
          <span class="terminal-chip">只做分析，不给确定性买卖指令</span>
        </header>
        <div v-if="!store.state.agentCommittee" class="empty-state">等待生成投研分析。</div>
        <div v-else class="committee-grid">
          <div><span>技术面</span><p>{{ store.state.agentCommittee.technical_view }}</p></div>
          <div><span>消息面</span><p>{{ store.state.agentCommittee.news_view }}</p></div>
          <div><span>风险面</span><p>{{ store.state.agentCommittee.risk_view }}</p></div>
          <div><span>多头理由</span><p>{{ store.state.agentCommittee.bull_case }}</p></div>
          <div><span>空头理由</span><p>{{ store.state.agentCommittee.bear_case }}</p></div>
          <div class="final"><span>综合判断</span><p>{{ store.state.agentCommittee.final_summary }}</p><strong>置信度 {{ store.formatNumber(store.state.agentCommittee.confidence, 2) }}</strong></div>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.research-page {
  display: grid;
  gap: 12px;
}

.research-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 20px;
  background:
    linear-gradient(135deg, rgba(172, 142, 255, 0.14), transparent 42%),
    linear-gradient(160deg, rgba(212, 175, 55, 0.08), rgba(18, 17, 21, 0.92));
}

.research-hero h1 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0;
}

.research-hero p {
  color: var(--text-muted);
  line-height: 1.7;
}

.research-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.42fr) minmax(0, 1fr);
  gap: 12px;
}

.prompt-body {
  display: grid;
  gap: 10px;
  padding: 14px;
}

.prompt-body textarea {
  min-height: 180px;
}

.committee-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 14px;
}

.committee-grid div {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 12px;
}

.committee-grid .final {
  grid-column: 1 / -1;
  border-color: rgba(212, 175, 55, 0.28);
  background: rgba(212, 175, 55, 0.08);
}

.committee-grid span {
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 900;
}

.committee-grid p {
  color: var(--text-main);
  line-height: 1.65;
}

.committee-grid strong {
  color: var(--engine-cyan);
}

@media (max-width: 900px) {
  .research-grid,
  .committee-grid {
    grid-template-columns: 1fr;
  }

  .research-hero {
    flex-direction: column;
  }
}
</style>
