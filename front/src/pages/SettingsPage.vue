<script setup>
import { CheckCircle2, KeyRound, Save, ShieldAlert } from "lucide-vue-next";
import { onMounted, reactive, ref } from "vue";
import { getUserSettings, listModelProviders, saveModelProvider, saveUserSettings, testModelProvider } from "../api/settingsApi";
import { useAuthStore } from "../stores/authStore";
import { useMarketStore } from "../stores/useMarketStore";

const auth = useAuthStore();
const store = useMarketStore();
const loading = ref(false);
const message = ref("");
const providers = ref([]);
const purposes = ref([]);

const settings = reactive({
  theme: "black_gold",
  default_model_provider: "deepseek",
  default_symbol: "000001.XSHE",
  default_period: "day",
});

const providerForm = reactive({
  provider: "deepseek",
  model: "deepseek-chat",
  api_key: "",
  is_active: true,
  purposes: ["strategy_generation", "strategy_debug", "backtest_audit", "stock_analysis", "news_summary"],
});

async function load() {
  loading.value = true;
  message.value = "";
  try {
    if (auth.state.token) {
      const userSettings = await getUserSettings();
      Object.assign(settings, userSettings.settings || {});
    }
    const providerPayload = await listModelProviders();
    providers.value = providerPayload.items || [];
    purposes.value = providerPayload.purposes || [];
  } catch (error) {
    message.value = `加载设置失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function saveSettings() {
  loading.value = true;
  try {
    await saveUserSettings(settings);
    store.state.symbol = settings.default_symbol;
    store.state.period = settings.default_period;
    message.value = "设置已保存。";
  } catch (error) {
    message.value = `保存失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function saveProvider() {
  loading.value = true;
  try {
    await saveModelProvider(providerForm);
    providerForm.api_key = "";
    message.value = "模型供应商配置已保存，API Key 不会在前端回显。";
    await load();
  } catch (error) {
    message.value = `保存失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function testProvider() {
  loading.value = true;
  try {
    const result = await testModelProvider(providerForm);
    message.value = result.message || (result.success ? "连接正常。" : "连接失败。");
  } catch (error) {
    message.value = `测试失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  store.state.currentPage = "settings";
  store.stopRealtimePolling();
  load();
});
</script>

<template>
  <main class="terminal-page settings-page">
    <section class="panel settings-hero">
      <div>
        <span class="terminal-chip">配置可保存</span>
        <h1>设置中心</h1>
        <p>这里管理默认股票、默认周期、模型供应商和 API Key。密钥只在后端保存，前端只显示是否已配置。</p>
      </div>
      <div class="login-state">
        <CheckCircle2 v-if="auth.state.user" :size="18" />
        <ShieldAlert v-else :size="18" />
        {{ auth.state.user ? `已登录：${auth.state.user.username}` : "未登录：模型 Key 可保存，个人偏好需登录" }}
      </div>
    </section>

    <section class="settings-grid">
      <article class="panel">
        <header class="panel-header">
          <h2 class="panel-title"><Save :size="15" /> 用户默认配置</h2>
        </header>
        <div class="form-grid">
          <label>
            <span class="terminal-label">默认股票</span>
            <input v-model="settings.default_symbol" class="terminal-input" />
          </label>
          <label>
            <span class="terminal-label">默认周期</span>
            <select v-model="settings.default_period" class="terminal-select">
              <option value="day">日线</option>
              <option value="60m">60分钟</option>
              <option value="30m">30分钟</option>
              <option value="5m">5分钟</option>
            </select>
          </label>
          <label>
            <span class="terminal-label">默认模型供应商</span>
            <select v-model="settings.default_model_provider" class="terminal-select">
              <option value="deepseek">DeepSeek</option>
              <option value="openai">OpenAI / GPT</option>
              <option value="qwen">通义千问</option>
              <option value="kimi">Kimi</option>
            </select>
          </label>
          <label>
            <span class="terminal-label">主题</span>
            <select v-model="settings.theme" class="terminal-select">
              <option value="black_gold">黑金金融终端</option>
              <option value="blue_gold">蓝金投研风格</option>
            </select>
          </label>
          <button class="terminal-button primary" :disabled="loading || !auth.state.user" @click="saveSettings">
            <Save :size="15" /> 保存默认配置
          </button>
        </div>
      </article>

      <article class="panel">
        <header class="panel-header">
          <h2 class="panel-title"><KeyRound :size="15" /> 模型供应商配置</h2>
          <span class="terminal-chip">Key 不回显</span>
        </header>
        <div class="form-grid">
          <label>
            <span class="terminal-label">供应商</span>
            <select v-model="providerForm.provider" class="terminal-select">
              <option value="deepseek">DeepSeek</option>
              <option value="openai">OpenAI / GPT</option>
              <option value="qwen">通义千问</option>
              <option value="kimi">Kimi</option>
              <option value="claude">Claude</option>
              <option value="openrouter">OpenRouter</option>
              <option value="local">本地模型</option>
            </select>
          </label>
          <label>
            <span class="terminal-label">模型名称</span>
            <input v-model="providerForm.model" class="terminal-input" />
          </label>
          <label>
            <span class="terminal-label">API Key</span>
            <input v-model="providerForm.api_key" class="terminal-input" type="password" placeholder="保存后不会回显完整 Key" />
          </label>
          <div class="purpose-box">
            <span class="terminal-label">用途分配</span>
            <label v-for="purpose in purposes" :key="purpose" class="check-line">
              <input v-model="providerForm.purposes" type="checkbox" :value="purpose" />
              {{ purpose }}
            </label>
          </div>
          <div class="button-row">
            <button class="terminal-button" :disabled="loading" @click="testProvider">测试连接</button>
            <button class="terminal-button primary" :disabled="loading" @click="saveProvider">保存供应商</button>
          </div>
        </div>
      </article>
    </section>

    <section class="panel provider-list">
      <header class="panel-header">
        <h2 class="panel-title">供应商状态</h2>
      </header>
      <div class="provider-grid">
        <article v-for="provider in providers" :key="provider.provider">
          <strong>{{ provider.label }}</strong>
          <p>{{ provider.default_model || "待配置模型" }}</p>
          <span :class="provider.configured ? 'ok' : 'muted'">{{ provider.configured ? "已配置" : "未配置" }}</span>
        </article>
      </div>
    </section>

    <div v-if="message" class="error-banner">{{ message }}</div>
  </main>
</template>

<style scoped>
.settings-page {
  display: grid;
  gap: 10px;
  overflow: auto;
}

.settings-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
}

h1 {
  margin: 10px 0 6px;
  font-size: 30px;
}

p {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.6;
}

.login-state {
  align-self: start;
  border: 1px solid rgba(212, 175, 55, 0.16);
  border-radius: 999px;
  color: var(--gold);
  display: inline-flex;
  gap: 8px;
  padding: 9px 12px;
  font-size: 12px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(320px, 1fr));
  gap: 10px;
}

.form-grid {
  display: grid;
  gap: 12px;
  padding: 14px;
}

label {
  display: grid;
  gap: 7px;
}

.purpose-box {
  display: grid;
  gap: 8px;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  padding: 12px;
}

.check-line {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-main);
  font-size: 12px;
}

.button-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 10px;
  padding: 14px;
}

.provider-grid article {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 12px;
}

.provider-grid strong {
  color: var(--text-main);
}

.provider-grid span {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.provider-grid .ok {
  color: var(--success);
}

@media (max-width: 860px) {
  .settings-hero,
  .settings-grid,
  .provider-grid {
    display: grid;
    grid-template-columns: 1fr;
  }
}
</style>
