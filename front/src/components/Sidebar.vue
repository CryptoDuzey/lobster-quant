<script setup>
import { Activity, BarChart3, BrainCircuit, Crown, DatabaseZap, Gauge, HelpCircle, LayoutDashboard, Settings, TerminalSquare, UserCircle } from "lucide-vue-next";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const items = [
  { to: "/dashboard", key: "dashboard", label: "总览", icon: LayoutDashboard },
  { to: "/radar", key: "radar", label: "行情", icon: Gauge },
  { to: "/ai-research", key: "ai-research", label: "投研", icon: BrainCircuit },
  { to: "/workshop", key: "workshop", label: "策略", icon: TerminalSquare },
  { to: "/backtest-lab", key: "backtest-lab", label: "回测", icon: BarChart3 },
  { to: "/strategy-cabin", key: "first-class", label: "广场", icon: Crown },
  { to: "/ai-center", key: "ai-center", label: "能力", icon: Activity },
  { to: "/data-sources", key: "data", label: "数据", icon: DatabaseZap },
  { to: "/profile", key: "profile", label: "我的", icon: UserCircle },
];

const activePath = computed(() => route.path);

function goWorkshop() {
  router.push("/workshop");
}

function goSettings() {
  router.push("/settings");
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand-lockup">
      <div class="brand-mark">L</div>
      <div class="brand-version">v3.0</div>
    </div>

    <nav class="nav-stack">
      <RouterLink
        v-for="item in items"
        :key="item.key"
        :to="item.to"
        class="nav-button"
        :class="{ active: activePath === item.to }"
        :title="item.label"
      >
        <component :is="item.icon" :size="21" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="sidebar-bottom">
      <button class="icon-button" title="设置" @click="goSettings">
        <Settings :size="20" />
      </button>
      <button class="icon-button" title="帮助">
        <HelpCircle :size="20" />
      </button>
      <button class="execute-button" @click="goWorkshop">
        <Activity :size="16" />
        工坊
      </button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  width: 82px;
  flex-shrink: 0;
  flex-direction: column;
  align-items: center;
  border-right: 1px solid var(--border-soft);
  background: rgba(6, 6, 8, 0.74);
  box-shadow: inset -1px 0 rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(20px);
  padding: 24px 10px;
}

.brand-lockup {
  display: grid;
  gap: 6px;
  place-items: center;
  margin-bottom: 28px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid rgba(212, 175, 55, 0.46);
  border-radius: 50%;
  background: radial-gradient(circle at 40% 30%, rgba(212, 175, 55, 0.35), rgba(255, 69, 58, 0.12));
  color: var(--gold);
  font-family: var(--font-display);
  font-size: 23px;
  font-weight: 900;
  box-shadow: 0 0 36px rgba(212, 175, 55, 0.18);
}

.brand-version {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 900;
}

.nav-stack {
  display: grid;
  width: 100%;
  gap: 12px;
}

.nav-button,
.icon-button,
.execute-button {
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.nav-button {
  display: grid;
  place-items: center;
  gap: 4px;
  min-height: 58px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--text-muted);
  text-decoration: none;
}

.nav-button span {
  font-size: 11px;
  font-weight: 800;
}

.nav-button:hover,
.nav-button.active {
  border-color: rgba(212, 175, 55, 0.28);
  background: rgba(212, 175, 55, 0.1);
  color: var(--gold);
  transform: translateY(-1px);
}

.sidebar-bottom {
  display: grid;
  width: 100%;
  gap: 10px;
  margin-top: auto;
}

.icon-button {
  display: grid;
  place-items: center;
  width: 100%;
  height: 42px;
  border: 1px solid rgba(212, 175, 55, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--gold);
}

.execute-button {
  display: grid;
  place-items: center;
  gap: 4px;
  min-height: 54px;
  border: 1px solid rgba(255, 69, 58, 0.38);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(255, 69, 58, 0.2), rgba(255, 69, 58, 0.06));
  color: var(--bull-red);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 900;
}

@media (max-width: 760px) {
  .sidebar {
    position: fixed;
    right: 0;
    bottom: 0;
    left: 0;
    z-index: 40;
    display: block;
    width: 100%;
    border-top: 1px solid var(--border-soft);
    border-right: 0;
    padding: 7px 8px calc(7px + env(safe-area-inset-bottom));
  }

  .brand-lockup,
  .sidebar-bottom {
    display: none;
  }

  .nav-stack {
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 6px;
    overflow-x: auto;
  }

  .nav-button {
    min-width: 62px;
    min-height: 48px;
  }
}
</style>
