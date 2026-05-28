<script setup>
import { Bookmark, FlaskConical, LogOut, UserCircle } from "lucide-vue-next";
import { computed } from "vue";
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/authStore";
import { useMarketStore } from "../stores/useMarketStore";

const auth = useAuthStore();
const store = useMarketStore();
const router = useRouter();
const userInitial = computed(() => (auth.state.user?.username || "访").slice(0, 1).toUpperCase());

async function logout() {
  await auth.logout();
  router.push("/login");
}

onMounted(() => {
  store.state.currentPage = "profile";
  store.stopRealtimePolling();
  auth.loadMe();
});
</script>

<template>
  <main class="terminal-page profile-page">
    <section class="panel profile-card">
      <div class="avatar">{{ userInitial }}</div>
      <h1>个人中心</h1>
      <template v-if="auth.state.user">
        <div class="profile-grid">
          <div><span>用户ID</span><strong>#{{ auth.state.user.id }}</strong></div>
          <div><span>昵称</span><strong>{{ auth.state.user.username }}</strong></div>
          <div><span>邮箱</span><strong>{{ auth.state.user.email }}</strong></div>
          <div><span>创建时间</span><strong>{{ auth.state.user.created_at }}</strong></div>
        </div>
        <div class="profile-stats">
          <div><Bookmark :size="15" /><span>本地策略</span><strong>{{ store.state.savedStrategies.length }}</strong></div>
          <div><FlaskConical :size="15" /><span>最近回测</span><strong>{{ store.state.lastBacktestAt ? "有记录" : "暂无" }}</strong></div>
        </div>
        <button class="terminal-button" @click="logout"><LogOut :size="15" /> 退出登录</button>
      </template>
      <template v-else>
        <p>当前未登录。</p>
        <RouterLink class="terminal-button primary" to="/login">去登录</RouterLink>
      </template>
    </section>
  </main>
</template>

<style scoped>
.profile-page {
  display: grid;
  place-items: center;
  overflow: auto;
}

.profile-card {
  display: grid;
  width: min(760px, 100%);
  gap: 16px;
  justify-items: center;
  padding: 28px;
}

.avatar {
  display: grid;
  place-items: center;
  width: 72px;
  height: 72px;
  border: 1px solid rgba(212, 175, 55, 0.34);
  border-radius: 50%;
  background: radial-gradient(circle at 40% 30%, rgba(212, 175, 55, 0.28), rgba(100, 210, 255, 0.1));
  color: var(--gold);
  font-size: 30px;
  font-weight: 900;
}

h1,
p {
  margin: 0;
}

p {
  color: var(--text-muted);
}

.profile-grid,
.profile-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  width: 100%;
}

.profile-grid div,
.profile-stats div {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  padding: 12px;
}

.profile-grid span,
.profile-stats span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.profile-grid strong,
.profile-stats strong {
  display: block;
  margin-top: 6px;
  color: var(--text-main);
  overflow-wrap: anywhere;
}

.profile-stats div {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 8px;
}

@media (max-width: 640px) {
  .profile-grid,
  .profile-stats {
    grid-template-columns: 1fr;
  }
}
</style>
