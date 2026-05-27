<script setup>
import { ShieldAlert, ShieldCheck } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../../stores/useMarketStore";

const store = useMarketStore();

const result = computed(() => store.state.backtestResult || null);
const dataInfo = computed(() => result.value?.data_info || {});
const trustAudit = computed(() => result.value?.trust_audit || {});

const rawWarnings = computed(() => [
  ...(result.value?.warnings || []),
  ...(trustAudit.value?.warnings || []),
  ...(trustAudit.value?.blocking_errors || []),
]);

const trustLabel = computed(() => {
  const level = trustAudit.value?.trust_level;
  if (dataInfo.value?.is_mock) return "包含演示数据";
  if (level === "high") return "可信";
  if (level === "medium") return "可参考";
  if (level === "low") return "需谨慎";
  if (level === "blocked") return "不可展示";
  return "等待回测";
});

const isBlocked = computed(() => ["blocked", "low"].includes(trustAudit.value?.trust_level) || dataInfo.value?.is_mock);

const friendlyWarnings = computed(() => {
  const seen = new Set();
  return rawWarnings.value
    .map((item) => explainWarning(item))
    .filter((item) => {
      if (!item || seen.has(item.title)) return false;
      seen.add(item.title);
      return true;
    });
});

function explainWarning(message = "") {
  const text = String(message);
  if (!text) return null;
  if (text.includes("卖出闭环") || text.includes("胜率")) {
    return {
      title: "胜率暂时不能算",
      body: "当前交易没有形成完整的“买入后卖出”闭环，所以无法判断这笔交易最后是赚还是亏。通常是卖出条件还没有被触发。",
    };
  }
  if (text.includes("交易次数较少") || text.includes("没有交易")) {
    return {
      title: "交易样本偏少",
      body: "这说明策略条件比较严格，或者回测区间内信号不多。交易少不是系统错误，但统计意义会弱一些。",
    };
  }
  if (text.includes("滑点")) {
    return {
      title: "成本口径说明",
      body: "当前回测已记录滑点参数，最终撮合仍按 rqalpha 可用的成本模型执行。这个提示不会影响行情和收益曲线的真实性。",
    };
  }
  if (text.includes("基准") || text.includes("Alpha") || text.includes("Beta")) {
    return {
      title: "基准数据说明",
      body: "Alpha 和 Beta 必须用真实基准收益序列计算；如果基准数据缺失或异常，系统不会用 0 或假曲线代替。",
    };
  }
  return {
    title: "回测提示",
    body: text,
  };
}

function shortHash(value) {
  const text = String(value || "");
  if (!text) return "--";
  if (text.length <= 18) return text;
  return `${text.slice(0, 12)}...${text.slice(-8)}`;
}
</script>

<template>
  <section class="panel trust-panel">
    <header class="panel-header">
      <h2 class="panel-title">
        <component :is="isBlocked ? ShieldAlert : ShieldCheck" :size="15" />
        回测风险说明
      </h2>
      <span class="terminal-chip" :class="{ danger: isBlocked }">{{ trustLabel }}</span>
    </header>

    <div v-if="!result" class="empty-state compact">
      等待执行回测。正式回测不会使用演示数据。
    </div>

    <div v-else-if="result.success === false" class="trust-error">
      <strong>{{ result.message || "本次回测失败" }}</strong>
      <p v-if="result.error_code">错误代码：{{ result.error_code }}</p>
    </div>

    <div v-else class="trust-body">
      <div class="trust-summary">
        <div>
          <span>回测编号</span>
          <strong>{{ result.backtest_id || "--" }}</strong>
        </div>
        <div>
          <span>策略指纹</span>
          <strong>{{ shortHash(result.strategy_hash) }}</strong>
        </div>
        <div>
          <span>代码指纹</span>
          <strong>{{ shortHash(result.code_hash || result.strategy_code_hash) }}</strong>
        </div>
        <div>
          <span>数据指纹</span>
          <strong>{{ shortHash(result.data_hash) }}</strong>
        </div>
      </div>

      <div v-if="dataInfo.is_mock" class="mock-warning">
        警告：当前结果包含演示数据，禁止作为正式回测结果展示。
      </div>

      <div v-if="friendlyWarnings.length" class="warning-list">
        <article v-for="item in friendlyWarnings" :key="item.title">
          <strong>{{ item.title }}</strong>
          <p>{{ item.body }}</p>
        </article>
      </div>
      <div v-else class="safe-note">
        暂无影响展示的风险提示。
      </div>
    </div>
  </section>
</template>

<style scoped>
.trust-panel {
  min-height: 150px;
}

.terminal-chip.danger {
  border-color: rgba(255, 69, 58, 0.38);
  color: var(--danger);
}

.trust-body {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.trust-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.trust-summary div,
.warning-list article,
.safe-note,
.trust-error,
.mock-warning {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 10px;
}

.trust-summary span {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
}

.trust-summary strong {
  display: block;
  margin-top: 6px;
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.warning-list {
  display: grid;
  gap: 8px;
}

.warning-list article {
  border-color: rgba(255, 214, 10, 0.24);
  background: rgba(255, 214, 10, 0.055);
}

.warning-list strong {
  color: #ffd60a;
  font-size: 13px;
}

.warning-list p,
.safe-note,
.trust-error p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.55;
}

.trust-error,
.mock-warning {
  margin: 12px;
  border-color: rgba(255, 69, 58, 0.35);
  background: rgba(255, 69, 58, 0.08);
  color: var(--text-main);
}

.mock-warning {
  margin: 0;
  color: var(--danger);
  font-weight: 800;
}

.compact {
  min-height: 70px;
}

@media (max-width: 900px) {
  .trust-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .trust-summary {
    grid-template-columns: 1fr;
  }
}
</style>
