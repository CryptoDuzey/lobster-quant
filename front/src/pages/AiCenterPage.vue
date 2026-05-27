<script setup>
import { Bot, BrainCircuit, Cpu, Github, Save, ShieldCheck, Trash2, Wrench } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { createGatewayToken, listGatewayTokens, listGatewayTools } from "../api/agentGatewayApi";
import { deleteSkill, disableSkill, enableSkill, importGithubSkill, listImportedSkills } from "../api/aiCenterApi";
import { listAgentAuditLogs, listAgentTools } from "../api/agentsApi";
import { listModelProviders, saveModelProvider, testModelProvider } from "../api/settingsApi";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const loading = ref(false);
const toolsPayload = ref({ tools: [], providers: [], security: {} });
const providerPayload = ref({ items: [], purposes: [] });
const auditLogs = ref([]);
const importedSkills = ref([]);
const githubUrl = ref("");
const githubMessage = ref("");
const gatewayTools = ref({ scopes: [], security: {} });
const gatewayTokens = ref([]);
const tokenName = ref("本地 Agent Token");
const newToken = ref(null);
const tokenMessage = ref("");
const selectedSkill = ref(null);
const selectedAgent = ref(null);
const providerMessage = ref("");
const providerForm = ref({
  provider: "deepseek",
  model: "deepseek-chat",
  api_key: "",
  is_active: true,
  purposes: ["strategy_generation", "strategy_debug", "backtest_audit", "stock_analysis", "news_summary"],
});

const agents = ref([
  { name: "行情盯盘 Agent", scene: "围绕当前股票、K线和消息面做个股问答", enabled: true },
  { name: "技术面 Agent", scene: "分析均线、ATR、RSI、布林带、趋势和关键价位", enabled: true },
  { name: "消息面 Agent", scene: "摘要真实消息源，判断偏利好、偏利空或中性", enabled: true },
  { name: "风控 Agent", scene: "评估回撤、波动、交易次数和过拟合风险", enabled: true },
  { name: "策略生成 Agent", scene: "把自然语言想法整理成 rqalpha 可回测策略", enabled: true },
  { name: "策略 Debug Agent", scene: "回测代码失败时，解释原因并给出修复", enabled: true },
  { name: "回测审计 Agent", scene: "基于真实指标和交易记录输出复盘分析", enabled: true },
]);

const skills = computed(() => toolsPayload.value.tools || []);
const providers = computed(() => providerPayload.value.items || []);
const selectedProvider = computed(() => providers.value.find((item) => item.provider === providerForm.value.provider));
const disabledScopes = computed(() => toolsPayload.value.security?.disabled_scopes || ["LIVE_TRADE_DISABLED"]);

function pickAgent(agent) {
  selectedAgent.value = agent;
  selectedSkill.value = null;
}

function toggleAgent(agent) {
  agent.enabled = !agent.enabled;
  selectedAgent.value = agent;
}

function pickProvider(provider) {
  providerForm.value.provider = provider.provider;
  providerForm.value.model = provider.purposes?.[0]?.model || provider.default_model || "";
  providerForm.value.is_active = provider.purposes?.some((item) => item.is_active) ?? true;
}

async function loadCapabilities() {
  loading.value = true;
  try {
    const [tools, logs, gateway, tokens, modelProviders, imported] = await Promise.all([
      listAgentTools(),
      listAgentAuditLogs(20),
      listGatewayTools().catch(() => ({ scopes: [], security: {} })),
      listGatewayTokens().catch(() => ({ items: [] })),
      listModelProviders().catch(() => ({ items: [], purposes: [] })),
      listImportedSkills().catch(() => ({ items: [] })),
    ]);
    toolsPayload.value = tools || { tools: [], providers: [], security: {} };
    auditLogs.value = logs.items || logs.logs || [];
    gatewayTools.value = gateway || { scopes: [], security: {} };
    gatewayTokens.value = tokens.items || [];
    providerPayload.value = modelProviders || { items: [], purposes: [] };
    importedSkills.value = imported.items || [];
    if (!selectedAgent.value) selectedAgent.value = agents.value[0];
    store.pushLog("AI", "能力中心状态已刷新");
  } catch (error) {
    store.setError(`能力中心加载失败：${error.message}`);
  } finally {
    loading.value = false;
  }
}

async function saveProviderConfig() {
  loading.value = true;
  providerMessage.value = "";
  try {
    await saveModelProvider(providerForm.value);
    providerMessage.value = "模型配置已保存。API Key 不会在前端回显。";
    providerPayload.value = await listModelProviders();
  } catch (error) {
    providerMessage.value = `保存失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function testProviderConfig() {
  loading.value = true;
  providerMessage.value = "";
  try {
    const result = await testModelProvider(providerForm.value);
    providerMessage.value = result.message || (result.success ? "连接正常" : "连接失败");
  } catch (error) {
    providerMessage.value = `测试失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function importSkill() {
  if (!githubUrl.value.trim()) return;
  loading.value = true;
  githubMessage.value = "";
  try {
    const result = await importGithubSkill({ url: githubUrl.value, permissions: ["READ_MARKET"] });
    githubMessage.value = result.message || "Skill 已保存为待启用。当前只解析说明，不执行外部代码。";
    githubUrl.value = "";
    importedSkills.value = (await listImportedSkills()).items || [];
  } catch (error) {
    githubMessage.value = `导入失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function toggleSkill(skill) {
  const result = skill.is_enabled ? await disableSkill(skill.id) : await enableSkill(skill.id);
  const updated = result.skill;
  importedSkills.value = importedSkills.value.map((item) => (item.id === updated.id ? updated : item));
  selectedSkill.value = updated;
}

async function removeSkill(skill) {
  await deleteSkill(skill.id);
  importedSkills.value = importedSkills.value.filter((item) => item.id !== skill.id);
  if (selectedSkill.value?.id === skill.id) selectedSkill.value = null;
}

async function issueGatewayToken() {
  loading.value = true;
  tokenMessage.value = "";
  try {
    const result = await createGatewayToken({ name: tokenName.value, scopes: ["R", "B"] });
    newToken.value = result;
    tokenMessage.value = "已生成 Agent Token。Token 只显示一次，用于让外部工具按权限调用龙虾量化。普通用户不需要配置。";
    gatewayTokens.value = (await listGatewayTokens()).items || [];
  } catch (error) {
    tokenMessage.value = `Token 生成失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  store.state.currentPage = "ai-center";
  store.stopRealtimePolling();
  loadCapabilities();
});
</script>

<template>
  <main class="terminal-page ai-center-page">
    <section class="panel hero-panel">
      <div>
        <span class="terminal-chip">能力与设置合并入口</span>
        <h1>AI 能力中心</h1>
        <p>这里统一管理模型 Key、Agent、Skill、GitHub Skill 和外部工具 Token。正常用户只需要先配置 DeepSeek，然后就可以在行情和工坊里对话。</p>
      </div>
      <button class="terminal-button primary" :disabled="loading" @click="loadCapabilities">
        <BrainCircuit v-if="!loading" :size="15" />
        <span v-else class="mini-spinner" />
        刷新状态
      </button>
    </section>

    <section class="center-grid">
      <article class="panel provider-panel">
        <header class="panel-header">
          <h2 class="panel-title"><Cpu :size="15" /> 模型配置</h2>
          <span class="terminal-chip">{{ selectedProvider?.configured ? "已配置" : "未配置" }}</span>
        </header>
        <div class="provider-list">
          <button
            v-for="provider in providers"
            :key="provider.provider"
            :class="{ active: providerForm.provider === provider.provider }"
            @click="pickProvider(provider)"
          >
            <strong>{{ provider.label }}</strong>
            <span>{{ provider.configured ? "已配置" : provider.implemented ? "可配置" : "预留" }}</span>
          </button>
        </div>
        <div class="provider-form">
          <label>
            模型名称
            <input v-model="providerForm.model" class="terminal-input" placeholder="deepseek-chat" />
          </label>
          <label>
            API Key
            <input v-model="providerForm.api_key" class="terminal-input" type="password" placeholder="只在保存时加密写入后端" />
          </label>
          <div class="provider-actions">
            <button class="terminal-button primary" :disabled="loading" @click="saveProviderConfig">
              <Save :size="14" /> 保存
            </button>
            <button class="terminal-button" :disabled="loading" @click="testProviderConfig">测试连接</button>
          </div>
          <p v-if="providerMessage" class="message-line">{{ providerMessage }}</p>
        </div>
      </article>

      <article class="panel agent-panel">
        <header class="panel-header">
          <h2 class="panel-title"><Bot :size="15" /> Agent</h2>
          <span class="terminal-chip">{{ agents.length }} 个</span>
        </header>
        <div class="card-list">
          <button v-for="agent in agents" :key="agent.name" class="cap-card" :class="{ active: selectedAgent?.name === agent.name }" @click="pickAgent(agent)">
            <strong>{{ agent.name }}</strong>
            <p>{{ agent.scene }}</p>
            <span :class="agent.enabled ? 'enabled' : 'disabled'">{{ agent.enabled ? "已启用" : "已禁用" }}</span>
          </button>
        </div>
      </article>

      <article class="panel detail-panel">
        <header class="panel-header">
          <h2 class="panel-title"><ShieldCheck :size="15" /> 能力详情</h2>
          <span class="terminal-chip danger">实盘禁用</span>
        </header>
        <div v-if="selectedAgent" class="detail-body">
          <h3>{{ selectedAgent.name }}</h3>
          <p>{{ selectedAgent.scene }}</p>
          <p>它只负责分析、生成、审计或建议，不会直接下单。</p>
          <button class="terminal-button" @click="toggleAgent(selectedAgent)">
            {{ selectedAgent.enabled ? "禁用这个 Agent" : "启用这个 Agent" }}
          </button>
        </div>
        <div v-else-if="selectedSkill" class="detail-body">
          <h3>{{ selectedSkill.name }}</h3>
          <p>{{ selectedSkill.description || "暂无说明" }}</p>
          <p>来源：{{ selectedSkill.source_url || selectedSkill.repo_full_name }}</p>
          <p>当前只解析说明，不执行外部代码。</p>
        </div>
        <div v-else class="detail-body">
          <h3>Agent Token 是什么？</h3>
          <p>它是给外部工具用的访问钥匙，例如未来让 Codex、Claude 或 MCP 工具按权限读取行情、运行回测。普通用户不需要它。</p>
        </div>
      </article>
    </section>

    <section class="center-grid secondary">
      <article class="panel">
        <header class="panel-header">
          <h2 class="panel-title"><Wrench :size="15" /> 系统 Skill</h2>
          <span class="terminal-chip">{{ skills.length }} 个</span>
        </header>
        <div class="card-list compact-list">
          <button v-for="skill in skills" :key="skill.name" class="cap-card" @click="selectedSkill = skill; selectedAgent = null">
            <strong>{{ skill.description || skill.name }}</strong>
            <p>{{ skill.name }}</p>
            <span>{{ (skill.permissions || []).join(" / ") || "只读" }}</span>
          </button>
        </div>
      </article>

      <article class="panel github-skill-panel">
        <header class="panel-header">
          <h2 class="panel-title"><Github :size="15" /> GitHub Skill 导入</h2>
          <span class="terminal-chip">只解析，不执行</span>
        </header>
        <div class="github-import">
          <input v-model="githubUrl" class="terminal-input" placeholder="https://github.com/owner/repo" />
          <button class="terminal-button primary" :disabled="loading || !githubUrl" @click="importSkill">解析 Skill</button>
        </div>
        <p v-if="githubMessage" class="message-line">{{ githubMessage }}</p>
        <div class="imported-skill-list">
          <article v-for="skill in importedSkills" :key="skill.id" class="cap-card">
            <strong>{{ skill.name }}</strong>
            <p>{{ skill.description || "暂无说明" }}</p>
            <span>{{ skill.repo_full_name || skill.source_url }}</span>
            <div class="skill-actions">
              <button class="terminal-button" @click="selectedSkill = skill; selectedAgent = null">查看</button>
              <button class="terminal-button" @click="toggleSkill(skill)">{{ skill.is_enabled ? "禁用" : "启用" }}</button>
              <button class="terminal-button" @click="removeSkill(skill)"><Trash2 :size="13" /> 删除</button>
            </div>
          </article>
          <div v-if="!importedSkills.length" class="empty-state">暂无外部 Skill。</div>
        </div>
      </article>

      <article class="panel gateway-panel">
        <header class="panel-header">
          <h2 class="panel-title"><ShieldCheck :size="15" /> Agent Token</h2>
          <span class="terminal-chip danger">外部工具用</span>
        </header>
        <div class="gateway-body">
          <p>Token 用来给外部工具有限权限，例如读取行情或运行回测。默认不包含交易权限。</p>
          <p>禁用权限：{{ disabledScopes.join(" / ") }}</p>
          <div class="github-import compact">
            <input v-model="tokenName" class="terminal-input" placeholder="Token 名称" />
            <button class="terminal-button primary" :disabled="loading" @click="issueGatewayToken">生成</button>
          </div>
          <p v-if="tokenMessage" class="message-line">{{ tokenMessage }}</p>
          <p v-if="newToken" class="token-once">{{ newToken.token }}</p>
          <p v-for="token in gatewayTokens" :key="token.id" class="token-row">
            {{ token.name }} · {{ token.token_preview }} · {{ (token.scopes || []).join("/") }}
          </p>
          <p v-for="scope in gatewayTools.scopes || []" :key="scope.scope" class="scope-row">
            {{ scope.scope }}：{{ scope.description }} · {{ scope.enabled ? "启用" : "禁用" }}
          </p>
        </div>
      </article>
    </section>

    <section class="panel audit-panel-wide">
      <header class="panel-header">
        <h2 class="panel-title">AI 调用审计日志</h2>
        <span class="terminal-chip">{{ auditLogs.length }} 条</span>
      </header>
      <div v-if="!auditLogs.length" class="empty-state">暂无审计日志。</div>
      <div v-else class="audit-log-list">
        <div v-for="item in auditLogs" :key="item.id || `${item.created_at}-${item.agent}`">
          <strong>{{ item.agent || item.agent_name || "Agent" }}</strong>
          <span>{{ item.task || item.action || "调用" }}</span>
          <em>{{ item.created_at || item.time || "--" }}</em>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.ai-center-page {
  display: grid;
  gap: 10px;
  overflow: auto;
}

.hero-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
}

h1 {
  margin: 10px 0 6px;
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: 30px;
}

.hero-panel p,
.gateway-body p,
.detail-body p {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.center-grid {
  display: grid;
  grid-template-columns: minmax(300px, 0.9fr) minmax(300px, 1fr) minmax(280px, 0.8fr);
  gap: 10px;
}

.secondary {
  grid-template-columns: minmax(260px, 0.75fr) minmax(360px, 1fr) minmax(300px, 0.8fr);
}

.provider-list,
.card-list {
  display: grid;
  gap: 8px;
  max-height: 430px;
  overflow: auto;
  padding: 12px;
}

.provider-list button,
.cap-card {
  display: grid;
  gap: 6px;
  width: 100%;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.024);
  color: var(--text-main);
  cursor: pointer;
  padding: 11px;
  text-align: left;
}

.provider-list button.active,
.cap-card.active,
.provider-list button:hover,
.cap-card:hover {
  border-color: rgba(212, 175, 55, 0.48);
  background: rgba(212, 175, 55, 0.08);
}

.cap-card strong,
.provider-list strong {
  color: var(--text-main);
  font-size: 13px;
}

.cap-card p {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
}

.cap-card span,
.provider-list span,
.audit-log-list span,
.audit-log-list em {
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
  font-style: normal;
}

.provider-form,
.detail-body,
.gateway-body {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.provider-form label {
  display: grid;
  gap: 6px;
  color: var(--text-muted);
  font-size: 12px;
}

.provider-actions,
.github-import,
.skill-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.github-import {
  padding: 12px;
}

.github-import.compact {
  padding: 0;
}

.github-import input {
  flex: 1;
}

.message-line {
  margin: 0 12px 12px;
  border: 1px solid rgba(212, 175, 55, 0.16);
  border-radius: 8px;
  color: var(--gold);
  padding: 9px 10px;
  font-size: 12px;
}

.imported-skill-list {
  display: grid;
  gap: 8px;
  padding: 0 12px 12px;
}

.enabled {
  color: var(--success) !important;
}

.disabled,
.terminal-chip.danger {
  color: var(--danger) !important;
}

.token-once {
  border: 1px solid rgba(255, 214, 10, 0.24);
  border-radius: 8px;
  background: rgba(255, 214, 10, 0.06);
  color: #ffd60a !important;
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
  padding: 10px;
}

.token-row,
.scope-row {
  font-family: var(--font-mono);
  font-size: 11px !important;
}

.audit-log-list {
  display: grid;
  gap: 8px;
  max-height: 220px;
  overflow: auto;
  padding: 12px;
}

.audit-log-list > div {
  display: grid;
  grid-template-columns: 1fr 1.4fr auto;
  gap: 12px;
  align-items: center;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.024);
  padding: 10px;
}

.mini-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: terminal-spin 0.8s linear infinite;
}

@media (max-width: 1180px) {
  .center-grid,
  .secondary {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .hero-panel,
  .provider-actions,
  .github-import,
  .skill-actions,
  .audit-log-list > div {
    align-items: stretch;
    flex-direction: column;
    grid-template-columns: 1fr;
  }
}
</style>
