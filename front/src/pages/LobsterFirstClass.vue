<script setup>
import { Bookmark, Eye, MessageSquare, Play, RefreshCcw, Rocket, Search, Star } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { addStrategyComment, listStrategyComments } from "../api/communityApi";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const router = useRouter();

const selected = ref(null);
const keyword = ref("");
const filter = ref("全部");
const sortBy = ref("发布时间");
const comments = ref([]);
const commentText = ref("");
const loadingComments = ref(false);

const filters = ["全部", "趋势跟随", "均值回归", "波动突破", "多因子", "高股息", "低回撤", "热门", "最新"];
const sortOptions = ["发布时间", "累计收益", "年化收益", "最大回撤", "夏普率", "热度", "浏览量", "收藏数"];

const strategies = computed(() => {
  let rows = [...(store.state.communityStrategies || [])];
  const key = keyword.value.trim().toLowerCase();
  if (key) {
    rows = rows.filter((item) =>
      [item.name, item.description, item.symbol, item.category, item.author]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(key)),
    );
  }
  if (filter.value === "热门") rows = rows.sort((a, b) => Number(b.favorites || 0) - Number(a.favorites || 0));
  else if (filter.value === "最新") rows = rows.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  else if (filter.value !== "全部") rows = rows.filter((item) => String(item.category || "").includes(filter.value));

  const sorters = {
    发布时间: (a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")),
    累计收益: (a, b) => Number(b.total_return ?? -Infinity) - Number(a.total_return ?? -Infinity),
    年化收益: (a, b) => Number(b.annual_return ?? -Infinity) - Number(a.annual_return ?? -Infinity),
    最大回撤: (a, b) => Math.abs(Number(a.max_drawdown ?? Infinity)) - Math.abs(Number(b.max_drawdown ?? Infinity)),
    夏普率: (a, b) => Number(b.sharpe ?? -Infinity) - Number(a.sharpe ?? -Infinity),
    热度: (a, b) => Number(b.favorites || 0) + Number(b.forks || 0) - Number(a.favorites || 0) - Number(a.forks || 0),
    浏览量: (a, b) => Number(b.views || 0) - Number(a.views || 0),
    收藏数: (a, b) => Number(b.favorites || 0) - Number(a.favorites || 0),
  };
  return rows.sort(sorters[sortBy.value] || sorters.发布时间);
});

async function reload() {
  await store.loadCommunityStrategies();
  selected.value = strategies.value[0] || null;
}

async function loadComments(strategyId) {
  if (!strategyId) {
    comments.value = [];
    return;
  }
  loadingComments.value = true;
  try {
    comments.value = await listStrategyComments(strategyId);
  } catch (error) {
    store.pushLog("错误", `评论加载失败：${error.message}`);
    comments.value = [];
  } finally {
    loadingComments.value = false;
  }
}

function quoteStrategy(strategy) {
  store.loadSavedStrategy(strategy);
  store.pushLog("完成", `已引用策略：${strategy.name}`);
  router.push("/workshop");
}

async function rerun(strategy) {
  store.loadSavedStrategy(strategy);
  await store.loadMarket({ keepBacktest: true });
  await store.runBacktest();
  router.push("/backtest-lab");
}

async function favorite(strategy) {
  await store.favoriteCommunity(strategy.id);
  selected.value = store.state.communityStrategies.find((item) => item.id === strategy.id) || selected.value;
}

async function fork(strategy) {
  await store.forkCommunity(strategy.id);
  quoteStrategy(strategy);
}

async function publishCurrent() {
  const published = await store.publishCurrentStrategy();
  if (published) {
    await reload();
    selected.value = store.state.communityStrategies.find((item) => item.id === published.id) || published;
  }
}

async function submitComment() {
  const content = commentText.value.trim();
  if (!selected.value || !content) return;
  try {
    await addStrategyComment(selected.value.id, content);
    commentText.value = "";
    await loadComments(selected.value.id);
    await store.loadCommunityStrategies();
  } catch (error) {
    store.pushLog("错误", `评论发布失败：${error.message}`);
  }
}

watch(
  () => selected.value?.id,
  (id) => loadComments(id),
);

onMounted(async () => {
  store.state.currentPage = "first-class";
  store.stopRealtimePolling();
  await reload();
});
</script>

<template>
  <main class="terminal-page square-page">
    <section class="panel square-panel">
      <header class="panel-header">
        <h2 class="panel-title"><Rocket :size="15" /> 策略广场</h2>
        <div class="square-actions">
          <button class="terminal-button" :disabled="store.state.loadingCommunity" @click="reload">
            <RefreshCcw :class="{ spin: store.state.loadingCommunity }" :size="14" /> 刷新
          </button>
          <button class="terminal-button primary" @click="publishCurrent">发布当前策略</button>
        </div>
      </header>

      <div class="square-toolbar">
        <label class="search-box">
          <Search :size="15" />
          <input v-model="keyword" placeholder="搜索策略、作者、标的或说明" />
        </label>
        <select v-model="sortBy">
          <option v-for="item in sortOptions" :key="item" :value="item">{{ item }}</option>
        </select>
      </div>

      <div class="filter-bar">
        <button v-for="item in filters" :key="item" :class="{ active: filter === item }" @click="filter = item">
          {{ item }}
        </button>
      </div>

      <div class="square-body">
        <div class="strategy-feed">
          <article
            v-for="strategy in strategies"
            :key="strategy.id"
            class="community-card"
            :class="{ active: selected?.id === strategy.id }"
            @click="selected = strategy"
          >
            <div class="card-head">
              <strong>{{ strategy.name }}</strong>
              <span class="official-badge" v-if="String(strategy.author || '').includes('官方') || String(strategy.category || '').includes('模板')">官方模板</span>
              <span v-else>{{ strategy.category || "用户策略" }}</span>
            </div>
            <p>{{ strategy.description || "暂无策略说明" }}</p>
            <div class="metric-strip">
              <span :class="Number(strategy.total_return || 0) >= 0 ? 'bull' : 'bear'">
                累计收益 {{ store.formatPercent(strategy.total_return) }}
              </span>
              <span>最大回撤 {{ store.formatDrawdown(strategy.max_drawdown) }}</span>
              <span>Sharpe {{ store.formatNumber(strategy.sharpe) }}</span>
            </div>
            <div class="meta-strip">
              <span>作者：{{ strategy.author || "本地用户" }}</span>
              <span>风险：{{ strategy.risk_level || "待评估" }}</span>
              <span><Eye :size="12" /> {{ strategy.views || 0 }}</span>
              <span><Star :size="12" /> {{ strategy.favorites || 0 }}</span>
              <span><Bookmark :size="12" /> {{ strategy.forks || 0 }}</span>
            </div>
          </article>
          <div v-if="!strategies.length" class="empty-state">暂无策略，换个筛选条件试试</div>
        </div>

        <aside class="detail-panel">
          <template v-if="selected">
            <div class="detail-head">
              <div>
                <div class="terminal-label">策略详情</div>
                <h3>{{ selected.name }}</h3>
                <p>{{ selected.description || "暂无策略介绍" }}</p>
              </div>
              <span class="risk-badge">{{ selected.risk_level || "待评估" }}</span>
            </div>

            <div class="detail-grid">
              <div><span>作者</span><strong>{{ selected.author || "本地用户" }}</strong></div>
              <div><span>类型</span><strong>{{ selected.category || "用户策略" }}</strong></div>
              <div><span>周期</span><strong>{{ selected.period || "日线" }}</strong></div>
              <div><span>标的</span><strong>{{ selected.name_cn || selected.symbol || "--" }}</strong></div>
              <div><span>累计收益</span><strong :class="Number(selected.total_return || 0) >= 0 ? 'bull' : 'bear'">{{ store.formatPercent(selected.total_return) }}</strong></div>
              <div><span>年化收益</span><strong>{{ store.formatPercent(selected.annual_return) }}</strong></div>
              <div><span>最大回撤</span><strong>{{ store.formatDrawdown(selected.max_drawdown) }}</strong></div>
              <div><span>夏普率</span><strong>{{ store.formatNumber(selected.sharpe) }}</strong></div>
            </div>

            <div class="rule-box backtest-preview">
              <span class="terminal-label">回测结果分析</span>
              <p v-if="selected.ai_audit?.summary">{{ selected.ai_audit.summary }}</p>
              <p v-else>该策略尚未保存 AI 回测分析。引用到工坊并重新回测后，可以生成真实分析。</p>
            </div>

            <div class="rule-box backtest-preview">
              <span class="terminal-label">收益曲线 / 交易日志 / 持仓流水</span>
              <p v-if="selected.curves?.strategy_curve?.length">已保存收益曲线：{{ selected.curves.strategy_curve.length }} 个点。</p>
              <p v-else>暂无保存的收益曲线。</p>
              <p v-if="selected.trades?.length">已保存交易记录：{{ selected.trades.length }} 条。</p>
              <p v-else>暂无保存的交易日志。点击“重新回测”可生成真实交易记录。</p>
            </div>

            <div class="rule-box">
              <span class="terminal-label">策略逻辑</span>
              <p v-for="rule in selected.rules?.buy_rules || []" :key="`b-${rule.expression}`">买入：{{ rule.description }} / {{ rule.expression }}</p>
              <p v-for="rule in selected.rules?.sell_rules || []" :key="`s-${rule.expression}`">卖出：{{ rule.description }} / {{ rule.expression }}</p>
              <p v-for="rule in selected.rules?.risk_rules || []" :key="`r-${rule.expression}`">风控：{{ rule.description }} / {{ rule.expression }}</p>
              <p v-if="!selected.rules">暂无结构化规则，建议引用后在工坊重新生成。</p>
            </div>

            <div class="rule-box warning">
              <span class="terminal-label">风险提示</span>
              <p>策略广场只用于研究、复盘和复用，不构成投资建议。引用前请重新回测，并检查样本区间、交易成本、最大回撤和数据来源。</p>
            </div>

            <div class="detail-actions">
              <button class="terminal-button primary" @click="quoteStrategy(selected)">
                <Eye :size="15" /> 引用到工坊
              </button>
              <button class="terminal-button green" :disabled="store.state.loadingBacktest" @click="rerun(selected)">
                <Play :size="15" /> 重新回测
              </button>
              <button class="terminal-button" @click="favorite(selected)">
                <Star :size="15" /> 收藏
              </button>
              <button class="terminal-button" @click="fork(selected)">
                <Bookmark :size="15" /> 复用
              </button>
            </div>

            <div class="comments-box">
              <div class="comments-head">
                <span class="terminal-label"><MessageSquare :size="14" /> 评论区</span>
                <small v-if="loadingComments">正在加载...</small>
              </div>
              <div class="comment-editor">
                <input v-model="commentText" placeholder="写下你的复盘、风险提醒或参数建议" @keydown.enter="submitComment" />
                <button class="terminal-button" @click="submitComment">发布</button>
              </div>
              <div class="comment-list">
                <article v-for="comment in comments" :key="comment.id" class="comment-card">
                  <strong>{{ comment.username || "本地用户" }}</strong>
                  <span>{{ comment.created_at }}</span>
                  <p>{{ comment.content }}</p>
                </article>
                <div v-if="!comments.length" class="empty-state compact">暂无评论</div>
              </div>
            </div>
          </template>
          <div v-else class="empty-state">请选择一个策略</div>
        </aside>
      </div>
    </section>
  </main>
</template>

<style scoped>
.square-page {
  overflow: visible;
}

.square-panel {
  min-height: 100%;
  background:
    linear-gradient(135deg, rgba(212, 175, 55, 0.06), transparent 34%),
    linear-gradient(160deg, rgba(63, 103, 173, 0.1), rgba(18, 17, 21, 0.84));
}

.square-actions,
.detail-actions,
.comments-head,
.square-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.square-actions {
  justify-content: flex-end;
}

.square-toolbar {
  justify-content: space-between;
  border-bottom: 1px solid rgba(212, 175, 55, 0.1);
  padding: 12px 14px;
}

.search-box {
  display: flex;
  align-items: center;
  min-width: min(460px, 100%);
  flex: 1;
  gap: 8px;
  border: 1px solid rgba(212, 175, 55, 0.16);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
  color: var(--gold);
  padding: 0 10px;
}

.search-box input,
.square-toolbar select,
.comment-editor input {
  width: 100%;
  height: 38px;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--text-main);
  font: inherit;
}

.square-toolbar select {
  width: 140px;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 8px;
  background: #141219;
  color: var(--text-main);
  padding: 0 10px;
}

.filter-bar {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  border-bottom: 1px solid rgba(212, 175, 55, 0.1);
  padding: 10px 14px;
}

.filter-bar button {
  flex: 0 0 auto;
  height: 30px;
  border: 1px solid rgba(212, 175, 55, 0.14);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-muted);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 900;
  padding: 0 12px;
}

.filter-bar button.active,
.filter-bar button:hover {
  border-color: rgba(212, 175, 55, 0.56);
  background: rgba(212, 175, 55, 0.12);
  color: var(--gold);
}

.square-body {
  display: grid;
  grid-template-columns: minmax(520px, 820px) 380px;
  gap: 16px;
  max-width: 1280px;
  margin: 0 auto;
  padding: 14px;
}

.strategy-feed {
  display: grid;
  grid-template-columns: 1fr;
  align-content: start;
  max-height: calc(100vh - 230px);
  gap: 12px;
  overflow-y: auto;
}

.community-card,
.comment-card {
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.024);
  padding: 14px;
}

.community-card {
  cursor: pointer;
  transition: all 0.16s ease;
}

.community-card:hover,
.community-card.active {
  border-color: rgba(212, 175, 55, 0.5);
  background: rgba(212, 175, 55, 0.08);
}

.card-head,
.metric-strip,
.meta-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.metric-strip {
  justify-content: flex-start;
  gap: 18px;
  margin-top: 12px;
}

.meta-strip {
  justify-content: flex-start;
  gap: 14px;
  margin-top: 12px;
}

.card-head strong,
.detail-head h3 {
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: 15px;
}

.card-head span,
.official-badge,
.metric-strip,
.meta-strip,
.comment-card span {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.official-badge {
  border: 1px solid rgba(255, 69, 58, 0.22);
  border-radius: 999px;
  background: rgba(255, 69, 58, 0.08);
  color: var(--bull-red);
  padding: 4px 8px;
}

.community-card p,
.detail-head p,
.rule-box p,
.comment-card p {
  color: var(--text-muted);
  line-height: 1.48;
  margin: 8px 0 0;
}

.community-card p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font-size: 12px;
}

.detail-panel {
  display: grid;
  align-content: start;
  gap: 12px;
  max-height: calc(100vh - 230px);
  overflow-y: auto;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.14);
  padding: 12px;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.risk-badge {
  flex: 0 0 auto;
  border: 1px solid rgba(255, 69, 58, 0.28);
  border-radius: 999px;
  background: rgba(255, 69, 58, 0.1);
  color: var(--bull-red);
  font-size: 12px;
  font-weight: 900;
  padding: 6px 10px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.detail-grid div,
.rule-box,
.comments-box {
  border: 1px solid rgba(212, 175, 55, 0.11);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 12px;
}

.detail-grid span {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
  margin-bottom: 6px;
}

.detail-grid strong {
  color: var(--text-main);
}

.warning {
  border-color: rgba(255, 69, 58, 0.16);
  background: rgba(255, 69, 58, 0.05);
}

.comment-editor {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.comment-editor input {
  border: 1px solid rgba(212, 175, 55, 0.14);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.2);
  padding: 0 10px;
}

.comment-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.comment-card strong {
  color: var(--gold);
  margin-right: 10px;
}

.compact {
  min-height: 72px;
}

@media (max-width: 980px) {
  .square-body {
    grid-template-columns: 1fr;
  }

  .strategy-feed,
  .detail-panel {
    grid-template-columns: 1fr;
    max-height: none;
  }

  .detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .square-toolbar {
    align-items: stretch;
  }

  .square-toolbar select,
  .search-box {
    width: 100%;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .comment-editor {
    flex-direction: column;
  }
}
</style>
