<script setup>
import { LogIn } from "lucide-vue-next";
import { reactive } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/authStore";

const auth = useAuthStore();
const router = useRouter();
const form = reactive({ username_or_email: "", password: "" });

async function submit() {
  await auth.login(form);
  router.push("/radar");
}
</script>

<template>
  <main class="auth-page">
    <section class="panel auth-card">
      <div class="brand">龙虾量化</div>
      <h1>登录工作站</h1>
      <p>登录后可以保存模型配置、默认股票、策略和回测记录。</p>
      <label>
        <span class="terminal-label">账号或邮箱</span>
        <input v-model="form.username_or_email" class="terminal-input" />
      </label>
      <label>
        <span class="terminal-label">密码</span>
        <input v-model="form.password" class="terminal-input" type="password" />
      </label>
      <div v-if="auth.state.error" class="error-banner">{{ auth.state.error }}</div>
      <button class="terminal-button primary" :disabled="auth.state.loading" @click="submit">
        <LogIn :size="15" /> {{ auth.state.loading ? "登录中" : "登录" }}
      </button>
      <RouterLink to="/register" class="auth-link">还没有账号，去注册</RouterLink>
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
