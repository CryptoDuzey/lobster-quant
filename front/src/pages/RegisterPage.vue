<script setup>
import { UserPlus } from "lucide-vue-next";
import { reactive } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/authStore";

const auth = useAuthStore();
const router = useRouter();
const form = reactive({ username: "", email: "", password: "" });

async function submit() {
  await auth.register(form);
  router.push("/settings");
}
</script>

<template>
  <main class="auth-page">
    <section class="panel auth-card">
      <div class="brand">龙虾量化</div>
      <h1>创建账号</h1>
      <p>MVP 阶段使用本地账号体系，后续可迁移到团队和多用户权限。</p>
      <label>
        <span class="terminal-label">用户名</span>
        <input v-model="form.username" class="terminal-input" />
      </label>
      <label>
        <span class="terminal-label">邮箱</span>
        <input v-model="form.email" class="terminal-input" />
      </label>
      <label>
        <span class="terminal-label">密码</span>
        <input v-model="form.password" class="terminal-input" type="password" />
      </label>
      <div v-if="auth.state.error" class="error-banner">{{ auth.state.error }}</div>
      <button class="terminal-button primary" :disabled="auth.state.loading" @click="submit">
        <UserPlus :size="15" /> {{ auth.state.loading ? "注册中" : "注册并进入设置" }}
      </button>
      <RouterLink to="/login" class="auth-link">已有账号，去登录</RouterLink>
    </section>
  </main>
</template>

<style scoped>
.auth-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 22px;
}

.auth-card {
  display: grid;
  width: min(440px, 100%);
  gap: 14px;
  padding: 24px;
}

.brand {
  color: var(--bull-red);
  font-family: var(--font-display);
  font-size: 34px;
  font-weight: 900;
}

h1 {
  margin: 0;
  color: var(--text-main);
}

p {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.6;
}

label {
  display: grid;
  gap: 7px;
}

.auth-link {
  color: var(--gold);
  text-align: center;
  text-decoration: none;
  font-size: 13px;
}
</style>
