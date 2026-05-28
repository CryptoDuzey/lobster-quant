<script setup>
import { Code2, Mic, MicOff, Pencil, Save, Send, Trash2, Wrench, Zap } from "lucide-vue-next";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { listAgentTools, strategyChat } from "../api/agentsApi";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();
const router = useRouter();

const loadingParse = ref(false);
const loadingTemplate = ref("");
const codeExpanded = ref(true);
const chatInput = ref("");
const chatScroller = ref(null);
const chatSlots = ref({});
const agentInfo = ref({ providers: [] });
const sessions = ref(readSessions());
const activeSessionId = ref(sessions.value[0]?.id || createSession().id);
const isListening = ref(false);
const speechError = ref("");
let recognition = null;
const chatMessages = ref([
  {
    role: "assistant",
    content: "直接说你的策略想法就行。我会先判断信息是否完整；不完整就追问，完整后生成策略代码并执行真实回测。",
  },
]);

const templates = [
  {
    name: "5日 / 20日均线交叉策略",
    type: "趋势策略",
    idea: "用平安银行，最近两年，日线，5日均线上穿20日均线买入，5日均线下穿20日均线卖出，满仓，回撤超过8%止损。",
    rules: {
      buy_rules: [{ id: "buy_ma_cross", description: "5日均线强于20日均线", expression: "ma5 > ma20" }],
      sell_rules: [{ id: "sell_ma_cross", description: "5日均线弱于20日均线", expression: "ma5 < ma20" }],
      risk_rules: [{ id: "risk_drawdown", description: "回撤超过8%止损", expression: "drawdown > 0.08" }],
    },
  },
  {
    name: "RSI超跌反转策略",
    type: "均值回归",
    idea: "用平安银行，最近两年，日线，RSI低于30买入，RSI回升到55以上卖出，满仓，回撤超过8%止损。",
    rules: {
      buy_rules: [{ id: "buy_rsi", description: "RSI低于30进入超跌区间", expression: "rsi < 30" }],
      sell_rules: [{ id: "sell_rsi", description: "RSI回升到55以上退出", expression: "rsi > 55" }],
      risk_rules: [{ id: "risk_rsi", description: "回撤超过8%止损", expression: "drawdown > 0.08" }],
    },
  },
  {
    name: "布林带均值回归策略",
    type: "均值回归",
    idea: "用平安银行，最近两年，日线，收盘价跌破布林带下轨买入，回到布林带中轨卖出，满仓，回撤超过6%止损。",
    rules: {
      buy_rules: [{ id: "buy_boll", description: "收盘价跌破布林带下轨", expression: "close < bb_lower" }],
      sell_rules: [{ id: "sell_boll", description: "收盘价回到布林带中轨", expression: "close > bb_mid" }],
      risk_rules: [{ id: "risk_boll", description: "回撤超过6%止损", expression: "drawdown > 0.06" }],
    },
  },
  {
    name: "ATR-RSI波动动量策略",
    type: "波动动量",
    idea: "用平安银行，最近两年，日线，价格站上MA20、ATR放大且RSI强于50时买入，跌破MA20或RSI转弱退出，满仓，回撤超过8%止损。",
    rules: {
      buy_rules: [{ id: "buy_momentum", description: "趋势、波动和相对强弱确认", expression: "close > ma20 and atr > atr_ma20 and rsi > 50" }],
      sell_rules: [{ id: "sell_momentum", description: "动量转弱", expression: "close < ma20 or rsi < 45" }],
      risk_rules: [{ id: "risk_momentum", description: "回撤超过8%止损", expression: "drawdown > 0.08" }],
    },
  },
];

const deepseek = computed(() => (agentInfo.value.providers || []).find((item) => item.name === "deepseek"));
const agentReady = computed(() => Boolean(deepseek.value?.enabled));
const agentStatusText = computed(() => (agentReady.value ? "DeepSeek 已连接" : "DeepSeek 未配置，请先在能力中心或设置里保存 API Key"));
const hasStarted = computed(() => chatMessages.value.length > 1 || Boolean(store.state.strategyJson) || Boolean(store.state.generatedCode));

const activeStrategyName = computed(() => store.state.strategyJson?.strategy_name || "等待生成策略");
const buyRules = computed(() => store.state.strategyJson?.rules?.buy_rules || []);
const sellRules = computed(() => store.state.strategyJson?.rules?.sell_rules || []);
const riskRules = computed(() => store.state.strategyJson?.rules?.risk_rules || []);

const factorRows = computed(() => [
  { key: "symbol", label: "标的", value: chatSlots.value.symbol || store.state.strategyJson?.symbol || "" },
  {
    key: "date",
    label: "时间",
    value: chatSlots.value.start_date && chatSlots.value.end_date
      ? `${chatSlots.value.start_date} 至 ${chatSlots.value.end_date}`
      : "",
  },
  { key: "period", label: "周期", value: chatSlots.value.period || store.state.strategyJson?.period || "" },
  { key: "initial_cash", label: "资金", value: chatSlots.value.initial_cash ? Number(chatSlots.value.initial_cash).toLocaleString() : "" },
  { key: "buy_condition", label: "买入", value: chatSlots.value.buy_condition || firstExpression(buyRules.value) },
  { key: "sell_condition", label: "卖出", value: chatSlots.value.sell_condition || firstExpression(sellRules.value) },
  { key: "stop_loss", label: "止损", value: chatSlots.value.stop_loss || firstExpression(riskRules.value) },
  { key: "position_rule", label: "仓位", value: chatSlots.value.position_rule || "" },
  { key: "benchmark", label: "基准", value: chatSlots.value.benchmark || store.state.strategyJson?.params?.benchmark || "" },
]);

const factorReadyCount = computed(() => factorRows.value.filter((item) => Boolean(item.value)).length);
const factorTotal = computed(() => factorRows.value.length);
const strategyReady = computed(() => Boolean(store.state.strategyJson && store.state.generatedCode));
const sessionRows = computed(() => {
  return sessions.value;
});

function readSessions() {
  try {
    const rows = JSON.parse(window.localStorage.getItem("lobster_strategy_sessions") || "[]");
    if (Array.isArray(rows) && rows.length) return rows;
  } catch {
    // ignore broken local cache
  }
  return [createSession()];
}

function writeSessions() {
  window.localStorage.setItem("lobster_strategy_sessions", JSON.stringify(sessions.value.slice(0, 30)));
}

function createSession(title = "新建策略会话") {
  return {
    id: `session_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    title,
    updated_at: new Date().toLocaleString("zh-CN", { hour12: false }),
    messages: null,
    slots: {},
  };
}

function newSession() {
  const row = createSession();
  sessions.value.unshift(row);
  activeSessionId.value = row.id;
  writeSessions();
  resetChat(false);
}

function renameSession(row) {
  const next = window.prompt("重命名策略会话", row.title);
  if (!next?.trim()) return;
  row.title = next.trim();
  row.updated_at = new Date().toLocaleString("zh-CN", { hour12: false });
  writeSessions();
}

function saveActiveConversation() {
  const row = sessions.value.find((item) => item.id === activeSessionId.value);
  if (!row) return;
  row.messages = chatMessages.value.map((item) => ({
    role: item.role,
    content: String(item.content || ""),
  }));
  row.slots = { ...chatSlots.value };
  row.strategy_name = store.state.strategyJson?.strategy_name || "";
  row.updated_at = new Date().toLocaleString("zh-CN", { hour12: false });
  writeSessions();
}

function loadSession(row) {
  if (!row) return;
  saveActiveConversation();
  activeSessionId.value = row.id;
  chatMessages.value = Array.isArray(row.messages) && row.messages.length
    ? row.messages
    : [
      {
        role: "assistant",
        content: "直接说你的策略想法。我会先判断信息是否完整；不完整就追问，完整后生成代码并触发真实回测。",
      },
    ];
  chatSlots.value = { ...(row.slots || {}) };
  store.state.strategyJson = null;
  store.state.generatedCode = "";
  store.state.debugHistory = [];
  chatInput.value = "";
  scrollChatToBottom();
}

function deleteSession(row) {
  sessions.value = sessions.value.filter((item) => item.id !== row.id);
  if (!sessions.value.length) sessions.value = [createSession()];
  if (activeSessionId.value === row.id) {
    activeSessionId.value = sessions.value[0].id;
    resetChat(false);
  }
  writeSessions();
}

function touchSession(title) {
  const row = sessions.value.find((item) => item.id === activeSessionId.value);
  if (!row) return;
  if (title) row.title = title.length > 24 ? `${title.slice(0, 24)}...` : title;
  row.messages = chatMessages.value.map((item) => ({
    role: item.role,
    content: String(item.content || ""),
  }));
  row.slots = { ...chatSlots.value };
  row.strategy_name = store.state.strategyJson?.strategy_name || row.strategy_name || "";
  row.updated_at = new Date().toLocaleString("zh-CN", { hour12: false });
  sessions.value = [row, ...sessions.value.filter((item) => item.id !== row.id)];
  writeSessions();
}

const strategyCodeView = computed(() => {
  if (loadingParse.value || store.state.loadingCode) {
    return "正在调用后端 Agent 接口生成策略代码，请稍候...";
  }
  if (store.state.generatedCode) {
    return store.state.generatedCode;
  }
  if (!store.state.strategyJson) {
    return [
      "策略代码将在 AI 补全策略要素后显示。",
      "",
      "一个完整策略至少需要：",
      "标的、回测时间、交易周期、初始资金、买入条件、卖出条件、止损条件、仓位规则、交易成本、基准指数。",
    ].join("\n");
  }
  return "策略规则已生成，正在等待 rqalpha 代码。请点击右侧“生成代码”或重新发送策略请求。";
});

function formatRules(rules) {
  if (!rules.length) return ["- 暂无"];
  return rules.map((rule) => `- ${rule.description || "规则"}：${rule.expression || "未生成表达式"}`);
}

function firstExpression(rules) {
  return rules.map((rule) => rule.expression).filter(Boolean).join(" and ");
}

function maskSecretText(text = "") {
  return String(text || "").replace(/sk-[A-Za-z0-9_-]{12,}/g, (value) => `${value.slice(0, 6)}****${value.slice(-4)}`);
}

function sanitizedMessages(messages) {
  return messages.map((item) => ({
    role: item.role === "assistant" ? "assistant" : "user",
    content: String(item.content || ""),
  }));
}

function scrollChatToBottom() {
  nextTick(() => {
    const el = chatScroller.value;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  });
}

function applySlots(slots = {}) {
  if (slots.symbol) store.state.symbol = slots.symbol;
  if (slots.stock_name) store.state.stockName = slots.stock_name;
  if (slots.period) store.state.period = slots.period;
  if (slots.start_date) store.state.startDate = slots.start_date;
  if (slots.end_date) store.state.endDate = slots.end_date;
}

function applyStrategyJson(strategy) {
  store.state.strategyJson = strategy;
  if (strategy.symbol) store.state.symbol = strategy.symbol;
  if (strategy.period) store.state.period = strategy.period;
  const rules = strategy.rules || {};
  store.state.buyIdea = firstExpression(rules.buy_rules || []) || store.state.buyIdea;
  store.state.sellIdea = firstExpression(rules.sell_rules || []) || store.state.sellIdea;
  store.state.riskIdea = firstExpression(rules.risk_rules || []) || store.state.riskIdea;
}

function strategyFromTemplate(template) {
  return {
    strategy_name: template.name,
    strategy_type: template.type,
    symbol: store.state.symbol,
    period: store.state.period || "day",
    rules: template.rules,
    params: {
      initial_cash: 1000000,
      commission: 0.0003,
      slippage: 0.0005,
      t_plus_one: true,
      round_lot: 100,
      benchmark: "000300.XSHG",
    },
    explanation: "经典模板已转换为安全规则，点击后直接进入真实回测。",
  };
}

function resetChat(createNew = true) {
  if (createNew) newSession();
  chatSlots.value = {};
  store.state.strategyJson = null;
  store.state.generatedCode = "";
  store.state.debugHistory = [];
  chatMessages.value = [
    {
      role: "assistant",
      content: "直接说你的策略想法。我会先判断信息是否完整；不完整就追问，完整后生成代码并触发真实回测。",
    },
  ];
  chatInput.value = "";
  scrollChatToBottom();
}

async function runTemplate(template) {
  if (loadingTemplate.value) return;
  loadingTemplate.value = template.name;
  store.state.strategyInput = template.idea;
  store.state.generatedCode = "";
  store.pushLog("AI", `经典策略模板提交到策略 Agent：${template.name}`);
  try {
    await submitStrategyIdea(`使用模板：${template.name}\n${template.idea}`, { useDefaults: true, runAfterComplete: true });
  } finally {
    loadingTemplate.value = "";
  }
}

async function sendStrategyChat(useDefaults = false, runAfterComplete = false) {
  const content = chatInput.value.trim();
  return submitStrategyIdea(content, { useDefaults, runAfterComplete });
}

async function submitStrategyIdea(content, { useDefaults = false, runAfterComplete = false } = {}) {
  let requestMessages = sanitizedMessages(chatMessages.value);
  if (content) {
    const visibleContent = maskSecretText(content);
    chatMessages.value.push({ role: "user", content: visibleContent });
    scrollChatToBottom();
    requestMessages = [...sanitizedMessages(chatMessages.value.slice(0, -1)), { role: "user", content }];
    store.state.strategyInput = visibleContent;
    touchSession(visibleContent.includes("****") ? "配置 DeepSeek API Key" : visibleContent);
  } else if (!useDefaults) {
    chatMessages.value.push({ role: "assistant", content: "请先描述策略，或者点击“使用默认配置补全”。" });
    return null;
  }
  chatInput.value = "";
  loadingParse.value = true;
  try {
    const result = await strategyChat({
      messages: requestMessages,
      slots: chatSlots.value,
      useDefaults,
    });
    chatSlots.value = result.slots || {};
    applySlots(chatSlots.value);

    const sourceNote = result.provider_configured === false ? "\n当前未配置 DeepSeek，系统只做了本地规则补全；配置并测试 Key 后会先调用真实模型理解策略。" : "";
    chatMessages.value.push({
      role: "assistant",
      content: result.conversation_only
        ? result.message
        : result.complete
        ? `${result.message}代码已作为消息块显示，可以直接送去回测。${sourceNote}`
        : `${result.message}\n${(result.questions || []).join("\n")}`,
    });

    if (result.complete && result.strategy?.strategy_json) {
      applyStrategyJson(result.strategy.strategy_json);
      store.state.generatedCode = result.strategy.generated_code || "";
      if (runAfterComplete) await executeBacktest();
    }
    saveActiveConversation();
    scrollChatToBottom();
    return result;
  } catch (error) {
    chatMessages.value.push({ role: "assistant", content: `策略对话 Agent 失败：${error.message}` });
    saveActiveConversation();
    scrollChatToBottom();
    return null;
  } finally {
    loadingParse.value = false;
  }
}

async function generateAndRun() {
  if (!store.state.strategyJson) {
    const result = await sendStrategyChat(true, true);
    if (!result?.complete) return;
    return;
  }
  await executeBacktest();
}

function shouldDebugBacktestFailure() {
  const failure = store.state.backtestResult || {};
  const code = String(failure.error_code || "");
  const message = `${store.state.error || ""} ${failure.message || ""}`;
  if (/MINUTE_MARKET_DATA_UNAVAILABLE|EMPTY_MARKET_DATA|DATA_SOURCE_ERROR|MISSING_EQUITY_CURVE/.test(code)) return false;
  if (/分钟级行情不足|行情数据|数据源|基准数据|真实数据|收益曲线缺失/.test(message)) return false;
  return true;
}

async function executeBacktest() {
  if (!store.state.strategyJson) {
    await sendStrategyChat(true, true);
    return null;
  }
  if (!store.state.generatedCode) await store.generateCode();
  const result = await store.runBacktest();
  if (!result && store.state.generatedCode) {
    if (shouldDebugBacktestFailure()) {
      await store.debugGeneratedCode(store.state.error || "回测执行失败");
    } else {
      chatMessages.value.push({
        role: "assistant",
        content: store.state.backtestResult?.message || store.state.error || "本次回测没有拿到足够真实数据，已停止展示结果。",
      });
      saveActiveConversation();
      scrollChatToBottom();
    }
    return null;
  }
  if (result) router.push("/backtest-lab");
  return result;
}

async function saveStrategy() {
  await store.saveCurrentStrategy(store.state.strategyJson?.strategy_name || "龙虾量化策略");
}

function startVoiceInput() {
  speechError.value = "";
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    speechError.value = "当前浏览器不支持语音识别，请用文字输入。";
    chatMessages.value.push({ role: "assistant", content: speechError.value });
    saveActiveConversation();
    return;
  }
  if (isListening.value && recognition) {
    recognition.stop();
    return;
  }
  recognition = new SpeechRecognition();
  recognition.lang = "zh-CN";
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.onstart = () => {
    isListening.value = true;
  };
  recognition.onresult = (event) => {
    const transcript = Array.from(event.results)
      .map((result) => result[0]?.transcript || "")
      .join("");
    if (transcript) chatInput.value = transcript;
  };
  recognition.onerror = (event) => {
    speechError.value = `语音输入失败：${event.error || "未知错误"}`;
    chatMessages.value.push({ role: "assistant", content: speechError.value });
    saveActiveConversation();
  };
  recognition.onend = () => {
    isListening.value = false;
  };
  recognition.start();
}

onMounted(async () => {
  store.state.currentPage = "workshop";
  store.stopRealtimePolling();
  try {
    agentInfo.value = await listAgentTools();
  } catch {
    agentInfo.value = { providers: [] };
  }
  scrollChatToBottom();
});

onBeforeUnmount(() => {
  saveActiveConversation();
  recognition?.stop?.();
});

watch(() => chatMessages.value.length, scrollChatToBottom, { flush: "post" });
watch(() => store.state.generatedCode, scrollChatToBottom, { flush: "post" });
watch(hasStarted, scrollChatToBottom, { flush: "post" });
</script>

<template>
  <main class="terminal-page workshop-page">
    <div class="workshop-layout">
      <aside class="panel session-panel">
        <header class="session-head">
          <button class="new-session" @click="newSession">＋ 新建策略</button>
        </header>
        <div class="session-list">
          <div v-for="item in sessionRows" :key="item.id" class="session-row" :class="{ active: item.id === activeSessionId }">
            <button @click="loadSession(item)">
              <strong>{{ item.title }}</strong>
              <em v-if="item.strategy_name">{{ item.strategy_name }}</em>
              <span>{{ item.updated_at }}</span>
            </button>
            <div class="session-actions">
              <button title="重命名" @click.stop="renameSession(item)"><Pencil :size="12" /></button>
              <button title="删除" @click.stop="deleteSession(item)"><Trash2 :size="12" /></button>
            </div>
          </div>
        </div>
      </aside>

      <section class="workshop-main" :class="{ started: hasStarted }">
        <div class="workshop-hero">
          <h1>AI 策略生成工坊</h1>
          <p>像和大模型聊天一样描述策略。Agent 会先确认标的、时间、资金、买卖、止损和基准，再生成 rqalpha 代码并送去真实回测。</p>
          <span>{{ agentStatusText }}</span>
        </div>

        <div v-if="!hasStarted" class="landing-composer">
          <div class="landing-input">
            <input
              v-model="chatInput"
              class="terminal-input"
              placeholder="例如：用平安银行，2025.1.1 到 2026.4.30，日线，5 日均线上穿 20 日均线买入，下穿卖出"
              @keyup.enter="sendStrategyChat(false, false)"
            />
            <button class="terminal-button primary" :disabled="loadingParse" @click="sendStrategyChat(false, false)">
              <Send :size="14" /> 发送
            </button>
            <button class="terminal-button voice-button" :class="{ active: isListening }" @click="startVoiceInput">
              <MicOff v-if="isListening" :size="14" />
              <Mic v-else :size="14" />
              {{ isListening ? "停止" : "语音" }}
            </button>
          </div>
          <p>止盈止损不是强制项。你只要说明交易想法，Agent 会判断是否能转换成策略；信息不清楚时会继续追问。</p>
        </div>

        <div class="quick-template-row">
          <button
            v-for="template in templates"
            :key="template.name"
            :disabled="Boolean(loadingTemplate)"
            @click="runTemplate(template)"
          >
            {{ loadingTemplate === template.name ? "执行中..." : template.name }}
          </button>
        </div>

        <div class="workflow-strip">
          <span class="active">1 描述想法</span>
          <span :class="{ active: store.state.strategyJson }">2 生成规则</span>
          <span :class="{ active: store.state.generatedCode }">3 生成代码</span>
          <span :class="{ active: store.state.backtestResult }">4 真实回测</span>
        </div>

        <div v-if="false" class="factor-board compact">
          <div class="factor-board-title">
            <strong>策略要素 {{ factorReadyCount }} / {{ factorTotal }}</strong>
            <button class="mini-link" :disabled="loadingParse" @click="sendStrategyChat(true, false)">使用默认配置</button>
          </div>
          <div class="factor-grid">
            <span v-for="item in factorRows" :key="item.key" :class="{ ready: item.value }">
              <b>{{ item.label }}</b>
              <em>{{ item.value || "待补充" }}</em>
            </span>
          </div>
        </div>

        <div ref="chatScroller" class="chat-stream">
          <div v-for="(item, index) in chatMessages" :key="index" :class="['chat-bubble', item.role]">
            {{ item.content }}
          </div>

          <div v-if="store.state.generatedCode" class="chat-code-card">
            <div class="code-card-head">
              <div>
                <strong><Code2 :size="15" /> 生成的 rqalpha 策略代码</strong>
                <span>{{ activeStrategyName }}</span>
              </div>
              <button class="mini-link" @click="codeExpanded = !codeExpanded">
                {{ codeExpanded ? "收起代码" : "展开代码" }}
              </button>
            </div>
            <pre v-if="codeExpanded">{{ strategyCodeView }}</pre>
            <div class="code-actions">
              <button class="terminal-button primary" :disabled="!strategyReady || store.state.loadingBacktest" @click="executeBacktest">
                <Zap v-if="!store.state.loadingBacktest" :size="15" />
                <span v-else class="mini-spinner" />
                送去回测
              </button>
              <button class="terminal-button" :disabled="store.state.loadingDebug || !store.state.generatedCode" @click="store.debugGeneratedCode()">
                <Wrench :size="14" /> 修改代码
              </button>
              <button class="terminal-button" :disabled="!store.state.strategyJson" @click="saveStrategy">
                <Save :size="15" /> 保存
              </button>
              <button class="terminal-button" :disabled="!store.state.strategyJson" @click="store.publishCurrentStrategy">
                发布
              </button>
            </div>
          </div>

          <div v-if="store.state.debugHistory.length" class="debug-list inline">
            <div v-for="item in store.state.debugHistory" :key="`${item.time}-${item.fix_summary}`">
              <strong>[{{ item.time }}] {{ item.source }}</strong>
              <p>{{ item.diagnosis }}</p>
              <p>{{ item.fix_summary }}</p>
            </div>
          </div>
        </div>

        <div class="chat-input-row">
          <input
            v-model="chatInput"
            class="terminal-input"
            placeholder="例如：用平安银行，2025.1.1到2026.4.30，日线，5日均线上穿20日均线买入，下穿卖出"
            @keyup.enter="sendStrategyChat(false, false)"
          />
          <button class="terminal-button" :disabled="loadingParse" @click="sendStrategyChat(false, false)">
            <Send :size="14" /> 发送
          </button>
          <button class="terminal-button voice-button" :class="{ active: isListening }" @click="startVoiceInput">
            <MicOff v-if="isListening" :size="14" />
            <Mic v-else :size="14" />
            {{ isListening ? "停止" : "语音" }}
          </button>
        </div>
        <p v-if="speechError" class="speech-note">{{ speechError }}</p>
      </section>
    </div>
  </main>
</template>

<style scoped>
.workshop-page {
  height: calc(100dvh - 72px);
  min-height: 0;
  overflow: hidden;
}

.workshop-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 14px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.template-panel,
.command-panel,
.code-panel {
  min-height: 0;
}

.template-list {
  display: grid;
  align-content: start;
  gap: 9px;
  height: calc(100% - 45px);
  overflow-y: auto;
  padding: 12px;
}

.template-list button {
  display: grid;
  gap: 5px;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.012));
  color: var(--text-main);
  cursor: pointer;
  padding: 12px;
  text-align: left;
}

.template-list button:hover:not(:disabled) {
  border-color: rgba(212, 175, 55, 0.48);
  background: rgba(212, 175, 55, 0.08);
  transform: translateY(-1px);
}

.template-list strong {
  font-size: 12px;
  line-height: 1.35;
}

.template-list span,
.template-list small {
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
}

.template-list small {
  color: var(--text-muted);
}

.command-panel {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr) auto auto;
  min-width: 0;
  background:
    linear-gradient(135deg, rgba(100, 210, 255, 0.08), transparent 44%),
    linear-gradient(145deg, rgba(18, 17, 21, 0.96), rgba(6, 6, 8, 0.86));
}

.command-header {
  align-items: start;
}

.command-header p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.workflow-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 10px 12px 0;
}

.workflow-strip span {
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 8px 9px;
  text-align: center;
}

.workflow-strip span.active {
  border-color: rgba(212, 175, 55, 0.34);
  background: rgba(212, 175, 55, 0.1);
  color: var(--gold);
}

.factor-board {
  display: grid;
  gap: 8px;
  padding: 10px 12px 0;
}

.factor-board-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.factor-board-title strong {
  color: var(--text-main);
  font-size: 12px;
}

.mini-link {
  border: 1px solid rgba(212, 175, 55, 0.2);
  border-radius: 999px;
  background: rgba(212, 175, 55, 0.08);
  color: var(--gold);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  padding: 6px 10px;
}

.factor-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
}

.factor-grid span {
  min-height: 52px;
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  padding: 8px;
}

.factor-grid span.ready {
  border-color: rgba(50, 215, 75, 0.22);
  background: rgba(50, 215, 75, 0.045);
}

.factor-grid b,
.factor-grid em {
  display: block;
}

.factor-grid b {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.factor-grid em {
  margin-top: 5px;
  color: var(--text-main);
  font-size: 11px;
  font-style: normal;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-stream {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
  background:
    linear-gradient(90deg, rgba(100, 210, 255, 0.025) 1px, transparent 1px),
    linear-gradient(0deg, rgba(212, 175, 55, 0.018) 1px, transparent 1px);
  background-size: 52px 52px, 52px 52px;
}

.chat-bubble {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  padding: 10px;
  color: var(--text-main);
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-line;
}

.chat-bubble.user {
  border-color: rgba(255, 69, 58, 0.26);
  background: rgba(255, 69, 58, 0.095);
  justify-self: end;
  max-width: 86%;
}

.chat-bubble.assistant {
  border-color: rgba(100, 210, 255, 0.24);
  background: rgba(100, 210, 255, 0.06);
  max-width: 92%;
}

.chat-input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 8px;
  padding: 0 12px 12px;
}

.voice-button.active {
  border-color: rgba(100, 210, 255, 0.42);
  color: var(--engine-cyan);
}

.speech-note {
  margin: -6px 12px 12px;
  color: #ffd60a;
  font-size: 12px;
}

.code-panel {
  position: fixed;
  top: 76px;
  right: 16px;
  bottom: 16px;
  z-index: 26;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  width: min(510px, 34vw);
  min-width: 390px;
  max-width: 560px;
  background:
    linear-gradient(135deg, rgba(212, 175, 55, 0.08), transparent 44%),
    linear-gradient(145deg, rgba(18, 17, 21, 0.96), rgba(6, 6, 8, 0.88));
  box-shadow: -26px 0 70px rgba(0, 0, 0, 0.34), 0 0 0 1px rgba(212, 175, 55, 0.12);
}

.code-actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 12px 14px 0;
}

.code-panel pre {
  min-height: 0;
  margin: 0;
  overflow: auto;
  padding: 14px;
  color: #f0cf61;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.debug-list {
  display: grid;
  gap: 8px;
  max-height: 160px;
  overflow-y: auto;
  padding: 0 14px 14px;
}

.debug-list > div,
.debug-empty {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.025);
  padding: 10px;
}

.debug-empty {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.debug-list strong {
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 11px;
}

.debug-list p {
  margin: 7px 0 0;
  color: var(--text-main);
  font-size: 12px;
  line-height: 1.5;
}

.mini-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: terminal-spin 0.8s linear infinite;
}

.workshop-layout {
  grid-template-columns: 244px minmax(0, 1fr);
  gap: 18px;
}

.session-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  border-color: rgba(212, 175, 55, 0.09);
  background: rgba(13, 13, 17, 0.82);
}

.session-head {
  padding: 12px;
  border-bottom: 1px solid rgba(212, 175, 55, 0.08);
}

.new-session {
  width: 100%;
  height: 38px;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 10px;
  background: rgba(212, 175, 55, 0.08);
  color: var(--gold);
  cursor: pointer;
  font-weight: 900;
}

.session-list {
  display: grid;
  align-content: start;
  gap: 4px;
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
}

.session-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px;
  border-radius: 8px;
}

.session-row.active,
.session-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.session-row > button {
  display: grid;
  gap: 4px;
  width: 100%;
  border-radius: 8px;
  background: transparent;
  color: var(--text-main);
  cursor: pointer;
  padding: 10px;
  text-align: left;
}

.session-list strong {
  overflow: hidden;
  font-size: 13px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-list span {
  color: var(--text-muted);
  font-size: 11px;
}

.session-list em {
  overflow: hidden;
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-actions {
  display: flex;
  gap: 3px;
  padding-right: 6px;
}

.session-actions button {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.session-actions button:hover {
  background: rgba(212, 175, 55, 0.1);
  color: var(--gold);
}

.workshop-main {
  display: grid;
  grid-template-rows: auto auto auto minmax(420px, 1fr) auto auto;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  max-width: 1180px;
  margin: 0 auto;
  width: 100%;
}

.workshop-main:not(.started) {
  grid-template-rows: auto minmax(160px, 1fr) auto;
  align-content: center;
}

.workshop-main.started {
  grid-template-rows: auto minmax(0, 1fr) auto auto;
}

.workshop-main.started .workshop-hero {
  grid-template-columns: minmax(0, 1fr) auto;
  justify-items: start;
  gap: 3px 12px;
  max-width: 1040px;
  width: calc(100% - 32px);
  margin: 0 auto;
  padding: 6px 0 4px;
  text-align: left;
}

.workshop-main.started .workshop-hero h1 {
  font-size: 18px;
}

.workshop-main.started .workshop-hero p {
  display: none;
}

.workshop-main.started .workshop-hero span {
  justify-self: end;
  align-self: center;
}

.workshop-main.started .quick-template-row,
.workshop-main.started .workflow-strip {
  display: none;
}

.workshop-main:not(.started) .workflow-strip,
.workshop-main:not(.started) .chat-stream,
.workshop-main:not(.started) > .chat-input-row {
  display: none;
}

.workshop-hero {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 14px 16px 10px;
  text-align: center;
}

.workshop-hero h1 {
  margin: 0;
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: clamp(24px, 3vw, 34px);
  letter-spacing: 0;
}

.workshop-hero p {
  max-width: 720px;
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.workshop-hero span {
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 900;
}

.quick-template-row {
  display: flex;
  justify-content: center;
  gap: 10px;
  overflow-x: auto;
  padding: 0 16px 8px;
}

.workshop-main.started .quick-template-row {
  justify-content: flex-start;
  max-width: 980px;
  width: calc(100% - 32px);
  margin: 0 auto;
  padding: 0 0 6px;
}

.landing-composer {
  display: grid;
  align-content: center;
  gap: 12px;
  max-width: 760px;
  width: calc(100% - 32px);
  margin: 0 auto;
}

.landing-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(100, 210, 255, 0.06), transparent 54%),
    rgba(255, 255, 255, 0.03);
  padding: 12px;
  box-shadow: 0 22px 80px rgba(0, 0, 0, 0.26);
}

.landing-input .terminal-button,
.landing-input .terminal-input {
  height: 38px;
  min-height: 38px;
}

.landing-composer p {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

.quick-template-row button {
  flex: 0 0 auto;
  min-height: 36px;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.028);
  color: var(--text-main);
  cursor: pointer;
  font-size: 13px;
  padding: 0 14px;
}

.quick-template-row button:hover:not(:disabled) {
  border-color: rgba(212, 175, 55, 0.36);
  background: rgba(212, 175, 55, 0.09);
  color: var(--gold);
}

.factor-board.compact {
  max-width: 980px;
  width: calc(100% - 32px);
  margin: 0 auto 8px;
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.02);
  padding: 12px;
}

.factor-board.compact .factor-grid {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.factor-board.compact .factor-grid span {
  min-height: 46px;
  padding: 7px;
}

.workshop-main .workflow-strip {
  max-width: 980px;
  width: calc(100% - 32px);
  margin: 0 auto;
  padding: 0 0 10px;
}

.workshop-main .chat-stream {
  max-width: 1040px;
  width: calc(100% - 32px);
  margin: 0 auto;
  min-height: 0;
  height: 100%;
  overflow-y: auto;
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.018), transparent 52px),
    rgba(8, 8, 12, 0.72);
}

.chat-code-card {
  display: grid;
  gap: 10px;
  border: 1px solid rgba(212, 175, 55, 0.18);
  border-radius: 14px;
  background: rgba(212, 175, 55, 0.045);
  padding: 12px;
}

.code-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.code-card-head strong {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-main);
  font-size: 13px;
}

.code-card-head span {
  display: block;
  margin-top: 4px;
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 10px;
}

.chat-code-card pre {
  max-height: min(340px, 42dvh);
  margin: 0;
  overflow: auto;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.38);
  color: #f0cf61;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.62;
  padding: 14px;
  white-space: pre-wrap;
}

.debug-list.inline {
  max-height: none;
  padding: 0;
}

.workshop-main .chat-input-row {
  align-self: end;
  align-items: center;
  max-width: 760px;
  width: calc(100% - 32px);
  margin: 8px auto 12px;
  grid-template-columns: minmax(0, 1fr) 88px 88px;
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.025);
  padding: 8px;
  max-height: 58px;
  min-height: 54px;
}

.workshop-main .chat-input-row .terminal-input,
.workshop-main .chat-input-row .terminal-button {
  height: 38px;
  min-height: 38px;
}

.workshop-main .chat-input-row .terminal-button {
  padding: 0 14px;
  justify-content: center;
  white-space: nowrap;
}

.workshop-main .speech-note {
  max-width: 980px;
  width: calc(100% - 32px);
  margin: 8px auto 0;
}

@media (max-width: 1180px) {
  .workshop-page {
    height: auto;
    overflow: auto;
  }

  .workshop-layout {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }

  .workshop-main {
    height: auto;
    min-height: calc(100dvh - 88px);
    overflow: visible;
  }

  .code-panel {
    position: relative;
    top: auto;
    right: auto;
    bottom: auto;
    width: 100%;
    min-width: 0;
    max-width: none;
  }

  .template-panel,
  .command-panel,
  .code-panel {
    min-height: 420px;
  }

  .code-actions,
  .factor-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .chat-input-row,
  .code-actions,
  .workflow-strip,
  .factor-grid,
  .landing-input {
    grid-template-columns: 1fr;
  }
}
</style>
