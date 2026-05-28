<script setup>
import { Bot, DatabaseZap, RefreshCcw, Satellite, ShieldCheck, UserCircle, Wifi } from "lucide-vue-next";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useMarketStore } from "../stores/useMarketStore";

const route = useRoute();
const router = useRouter();
const store = useMarketStore();

const navItems = [
  { to: "/radar", label: "行情" },
  { to: "/workshop", label: "工坊" },
  { to: "/backtest-lab", label: "回测" },
  { to: "/strategy-cabin", label: "广场" },
];

const pageName = computed(() => {
  if (route.name === "dashboard") return "总览 Dashboard";
  if (route.name === "radar") return "实时行情雷达";
  if (route.name === "ai-research") return "AI 投研";
  if (route.name === "workshop") return "AI 投研工坊";
  if (route.name === "backtest-lab") return "回测实验室";
  if (route.name === "first-class") return "策略广场";
  if (route.name === "ai-center") return "AI 能力中心";
  if (route.name === "data-sources") return "数据源管理";
  if (route.name === "settings") return "设置中心";
  if (route.name === "profile") return "个人中心";
  if (route.name === "login") return "登录";
  if (route.name === "register") return "注册";
  return "龙虾量化";
});

const priceClass = computed(() => {
  const pct = Number(store.state.quote?.change_pct ?? 0);
  return pct >= 0 ? "bull" : "bear";
});

async function refresh() {
  await store.loadMarket();
  if (store.state.currentPage === "radar") store.startRealtimePolling();
}
</script>

<template>
  <header class="topbar">
    <div class="topbar-row primary-row">
      <button class="brand-block" @click="router.push('/radar')">
        <span class="brand-mark">L</span>
        <span>
          <strong>龙虾量化</strong>
          <em>{{ pageName }}</em>
        </span>
      </button>

      <nav class="top-nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :class="{ active: route.path === item.to }"
        >
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="status-cluster">
        <div class="status-item">
          <ShieldCheck :size="16" />
          <span>后端在线</span>
        </div>
        <div class="status-item" :class="{ warn: !store.state.dataSource && store.state.error }">
          <DatabaseZap :size="16" />
          <span>{{ store.state.dataSource ? `数据源：${store.state.dataSource}` : "数据源：等待真实接口" }}</span>
        </div>
        <div class="status-item">
          <Satellite :size="16" />
          <span>{{ store.state.latencyMs == null ? "延迟：--" : `延迟：${store.state.latencyMs}ms` }}</span>
        </div>
      </div>

      <button class="icon-action wide-action" title="能力与设置" @click="router.push('/ai-center')">
        <Bot :size="18" />
        <span>能力/设置</span>
      </button>
      <button class="icon-action" title="用户" @click="router.push('/profile')">
        <UserCircle :size="18" />
      </button>

      <div class="quote-tape">
        <Wifi :size="15" />
        <span class="terminal-label">{{ store.state.quote?.name || store.state.stockName }}</span>
        <strong :class="priceClass">{{ store.formatPrice(store.state.quote?.price) }}</strong>
        <span :class="priceClass">{{ store.state.quote?.change_pct == null ? "--" : `${Number(store.state.quote.change_pct).toFixed(2)}%` }}</span>
      </div>
      <button class="icon-action" title="刷新行情" :disabled="store.state.loadingMarket" @click="refresh">
        <RefreshCcw :class="{ spin: store.state.loadingMarket }" :size="18" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 30;
  display: grid;
  border-bottom: 1px solid var(--border-soft);
  background:
    linear-gradient(180deg, rgba(18, 17, 21, 0.96), rgba(10, 10, 14, 0.9)),
    rgba(18, 17, 21, 0.92);
  padding: 10px 14px;
  backdrop-filter: blur(20px);
}

.topbar-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.primary-row {
  justify-content: space-between;
}

.brand-block {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 10px;
  min-width: 178px;
  border: 0;
  background: transparent;
  color: var(--text-main);
  cursor: pointer;
  padding: 0;
  text-align: left;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid rgba(212, 175, 55, 0.46);
  border-radius: 12px;
  background: radial-gradient(circle at 40% 30%, rgba(212, 175, 55, 0.34), rgba(255, 69, 58, 0.12));
  color: var(--gold);
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 900;
}

.brand-block strong {
  display: block;
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: 20px;
  line-height: 1;
}

.brand-block em {
  display: block;
  margin-top: 4px;
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
  font-style: normal;
  font-weight: 900;
}

.top-nav {
  display: flex;
  align-items: center;
  flex: 0 1 auto;
  gap: 10px;
  min-width: 0;
  overflow-x: auto;
}

.top-nav a {
  flex: 0 0 auto;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 900;
  min-height: 40px;
  min-width: 74px;
  padding: 11px 16px;
  text-decoration: none;
  text-align: center;
}

.top-nav a:hover,
.top-nav a.active {
  border-color: rgba(212, 175, 55, 0.32);
  background:
    linear-gradient(180deg, rgba(212, 175, 55, 0.16), rgba(212, 175, 55, 0.06));
  color: var(--gold);
  box-shadow: inset 0 1px rgba(255, 255, 255, 0.04);
}

.status-cluster {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: nowrap;
  gap: 8px;
  margin-left: auto;
  min-width: 0;
}

.status-item,
.quote-tape {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  border: 1px solid rgba(212, 175, 55, 0.16);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 0 10px;
  white-space: nowrap;
}

.status-item.warn {
  border-color: rgba(255, 69, 58, 0.42);
  color: var(--bull-red);
}

.quote-tape strong {
  font-size: 14px;
}

.icon-action {
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border: 1px solid rgba(212, 175, 55, 0.16);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(212, 175, 55, 0.08), rgba(255, 255, 255, 0.025));
  color: var(--gold);
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.wide-action {
  display: inline-flex;
  width: auto;
  min-width: 70px;
  gap: 6px;
  padding: 0 10px;
}

.wide-action span {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 900;
}

.icon-action:hover:not(:disabled) {
  border-color: rgba(212, 175, 55, 0.42);
  background: rgba(212, 175, 55, 0.1);
  transform: translateY(-1px);
}

@media (max-width: 980px) {
  .topbar {
    position: static;
  }

  .topbar-row {
    align-items: center;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .primary-row {
    gap: 8px;
  }

  .brand-block {
    flex: 1 1 auto;
    min-width: 170px;
    width: auto;
  }

  .top-nav {
    order: 10;
    flex-basis: 100%;
    width: 100%;
  }

  .status-cluster {
    justify-content: flex-start;
    overflow-x: auto;
    width: 100%;
  }
}

@media (max-width: 1320px) {
  .status-item {
    display: none;
  }
}
</style>
