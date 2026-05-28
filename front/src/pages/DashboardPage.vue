<script setup>
import { Activity, Bot, DatabaseZap, Gauge, LineChart, Settings, ShieldCheck, Users } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { listAgentTools } from "../api/agentsApi";
import { listBacktestRuns } from "../api/backtestApi";
import { listCommunityStrategies } from "../api/communityApi";
import { listDataSources } from "../api/dataSourceApi";
import { listModelProviders } from "../api/settingsApi";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const router = useRouter();
const backtests = ref([]);
const strategies = ref([]);
const dataSources = ref([]);
const providers = ref([]);
const tools = ref([]);
const loading = ref(false);

const configuredProvider = computed(() => providers.value.find((item) => item.configured));
const sourceSummary = computed(() => dataSources.value.map((item) => `${item.display_name}${item.is_enabled ? "" : "（停用）"}`).join(" / ") || "等待检测");

async function loadDashboard() {
  loading.value = true;
  try {
    const [runs, strategyRows, sourcePayload, providerPayload, toolPayload] = await Promise.all([
      listBacktestRuns(5),
      listCommunityStrategies(),
      listDataSources(),
      listModelProviders().catch(() => ({ items: [] })),
      listAgentTools().catch(() => ({ tools: [] })),
    ]);
    backtests.value = runs;
    strategies.value = strategyRows.slice(0, 5);
    dataSources.value = sourcePayload.items || [];
    providers.value = providerPayload.items || [];
    tools.value = toolPayload.tools || [];
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  store.state.currentPage = "dashboard";
  store.stopRealtimePolling();
  await loadDashboard();
});
</script>

<template>
  <main class="terminal-page dashboard-page">
    <section class="dashboard-hero panel">
      <div>
        <div class="terminal-label">A股 AI 量化工作站</div>
        <h1>总览 Dashboard</h1>
        <p>这里汇总系统健康、数据源、模型、最近回测和策略资产。龙虾量化现在按工作站结构组织，不再只是静态展示大屏。</p>
      </div>
      <div class="hero-actions">
        <button class="terminal-button primary" @click="router.push('/radar')"><Gauge :size="15" /> 打开行情雷达</button>
        <button class="terminal-button" @click="router.push('/backtest-lab')"><LineChart :size="15" /> 查看回测实验室</button>
      </div>
    </section>

    <section class="overview-grid">
      <article class="panel status-card">
        <ShieldCheck :size="20" />
        <span>后端状态</span>
        <strong>在线</strong>
        <p>FastAPI 已连接，/docs 可用。</p>
      </article>
      <article class="panel status-card blue">
        <DatabaseZap :size="20" />
        <span>数据源</span>
        <strong>{{ sourceSummary }}</strong>
        <p>行情优先真实接口，日线和基准数据启用 SQLite 缓存。</p>
      </article>
      <article class="panel status-card violet">
        <Bot :size="20" />
        <span>模型状态</span>
        <strong>{{ configuredProvider ? `${configuredProvider.label || configuredProvider.provider} 已配置` : "模型 API Key 未配置" }}</strong>
        <p>可在能力中心配置 DeepSeek、OpenAI、Claude、Kimi 等模型，密钥不在前端回显。</p>
      </article>
      <article class="panel status-card">
        <Activity :size="20" />
        <span>Agent / Skill</span>
        <strong>{{ tools.length }} 个技能</strong>
        <p>实盘交易默认禁用，所有 Agent 调用写入审计日志。</p>
      </article>
    </section>

    <section class="dashboard-grid">
      <article class="panel dashboard-list">
        <header class="panel-header">
          <h2 class="panel-title"><LineChart :size="15" /> 最近回测</h2>
          <button class="terminal-button" @click="router.push('/backtest-lab')">进入实验室</button>
        </header>
        <div class="list-body">
          <div v-for="run in backtests" :key="run.backtest_id" class="list-row">
            <div>
              <strong>{{ run.strategy_name || "未命名策略" }}</strong>
              <span>{{ run.name || run.symbol }} / {{ run.period }}</span>
            </div>
            <div>
              <strong :class="Number(run.metrics?.total_return || 0) >= 0 ? 'bull' : 'bear'">{{ store.formatPercent(run.metrics?.total_return) }}</strong>
              <span>{{ run.created_at }}</span>
            </div>
          </div>
          <div v-if="!backtests.length" class="empty-state">暂无回测记录</div>
        </div>
      </article>

      <article class="panel dashboard-list">
        <header class="panel-header">
          <h2 class="panel-title"><Users :size="15" /> 最近策略</h2>
          <button class="terminal-button" @click="router.push('/strategy-cabin')">策略广场</button>
        </header>
        <div class="list-body">
          <div v-for="strategy in strategies" :key="strategy.id" class="list-row">
            <div>
              <strong>{{ strategy.name }}</strong>
              <span>{{ strategy.category || "用户策略" }} / {{ strategy.author || "本地用户" }}</span>
            </div>
            <div>
              <strong>{{ store.formatNumber(strategy.sharpe) }}</strong>
              <span>收藏 {{ strategy.favorites || 0 }}</span>
            </div>
          </div>
          <div v-if="!strategies.length" class="empty-state">暂无策略</div>
        </div>
      </article>

      <article class="panel task-panel">
        <header class="panel-header">
          <h2 class="panel-title"><Settings :size="15" /> 工作站任务队列</h2>
          <span class="terminal-chip">SSE 预留</span>
        </header>
        <div class="task-list">
          <div class="task-item active">行情刷新轮询：按页面进入自动启停</div>
          <div class="task-item active">回测记录：已写入 SQLite</div>
          <div class="task-item active">Agent Gateway：已预留任务与进度流</div>
          <div class="task-item">纸交易与实盘交易：当前禁用</div>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.dashboard-page {
  display: grid;
  gap: 12px;
}

.dashboard-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 170px;
  padding: 22px;
  background:
    linear-gradient(135deg, rgba(212, 175, 55, 0.12), transparent 40%),
    linear-gradient(160deg, rgba(100, 210, 255, 0.09), rgba(18, 17, 21, 0.92));
}

.dashboard-hero h1 {
  margin: 8px 0;
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: 32px;
}

.dashboard-hero p {
  max-width: 760px;
  color: var(--text-muted);
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.overview-grid,
.dashboard-grid {
  display: grid;
  gap: 12px;
}

.overview-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.dashboard-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.status-card {
  display: grid;
  gap: 8px;
  min-height: 150px;
  padding: 16px;
  border-color: rgba(212, 175, 55, 0.18);
}

.status-card.blue {
  border-color: rgba(100, 210, 255, 0.18);
  background: linear-gradient(145deg, rgba(100, 210, 255, 0.1), rgba(6, 6, 8, 0.78));
}

.status-card.violet {
  border-color: rgba(172, 142, 255, 0.2);
  background: linear-gradient(145deg, rgba(172, 142, 255, 0.09), rgba(6, 6, 8, 0.78));
}

.status-card svg {
  color: var(--gold);
}

.status-card span,
.status-card p,
.list-row span,
.task-item {
  color: var(--text-muted);
  font-size: 12px;
}

.status-card strong {
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: 18px;
}

.dashboard-list,
.task-panel {
  min-height: 320px;
}

.list-body,
.task-list {
  display: grid;
  gap: 9px;
  padding: 14px;
}

.list-row,
.task-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid rgba(212, 175, 55, 0.11);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 12px;
}

.list-row strong {
  display: block;
  color: var(--text-main);
  margin-bottom: 5px;
}

.task-item {
  display: block;
}

.task-item.active {
  border-color: rgba(212, 175, 55, 0.22);
  color: var(--text-main);
}

@media (max-width: 1120px) {
  .overview-grid,
  .dashboard-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .dashboard-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .overview-grid,
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
</style>
