<script setup>
import { ListChecks } from "lucide-vue-next";
import { computed } from "vue";
import { useMarketStore } from "../stores/useMarketStore";

const store = useMarketStore();

const tradeRows = computed(() => {
  let position = 0;
  let averageCost = 0;
  let realizedPnl = 0;

  return (store.state.trades || []).map((trade, index) => {
    const direction = String(trade.direction || "").toUpperCase();
    const price = Number(trade.price || 0);
    const quantity = Number(trade.quantity || 0);
    const amount = Number(trade.amount || price * quantity || 0);
    const fee = Number(trade.fee || 0);
    let rowPnl = null;
    let cashFlow = 0;

    if (direction === "BUY") {
      const newPosition = position + quantity;
      if (newPosition > 0) {
        averageCost = (averageCost * position + amount + fee) / newPosition;
      }
      position = newPosition;
      cashFlow = -(amount + fee);
    } else if (direction === "SELL") {
      const sellQuantity = Math.min(quantity, position || quantity);
      rowPnl = (price - averageCost) * sellQuantity - fee;
      realizedPnl += rowPnl;
      position = Math.max(0, position - quantity);
      cashFlow = amount - fee;
      if (position === 0) averageCost = 0;
    }

    return {
      ...trade,
      id: trade.id || `${trade.time || "trade"}-${index}`,
      direction,
      amount,
      fee,
      cashFlow,
      position,
      averageCost,
      rowPnl,
      realizedPnl,
    };
  });
});

const summary = computed(() => {
  const rows = tradeRows.value;
  const last = rows[rows.length - 1];
  return {
    count: rows.length,
    position: last?.position || 0,
    realizedPnl: last?.realizedPnl || 0,
  };
});

function formatMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatSignedMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function executionLabel(trade) {
  const model = store.state.backtestResult?.engine_info?.execution_model || {};
  if (trade.execution_label) return trade.execution_label;
  if (model.label) return model.label;
  return (trade.execution_precision === "intraday" || trade.is_precise_intraday) ? "分钟撮合" : "日线估算";
}

function executionNote(trade) {
  const model = store.state.backtestResult?.engine_info?.execution_model || {};
  if (trade.execution_precision === "daily_estimated" || model.precision === "daily_estimated" || store.state.backtestResult?.period === "day") {
    return "非分钟级真实成交";
  }
  if (trade.is_precise_intraday) return "分钟线撮合";
  return trade.time_note || "--";
}
</script>

<template>
  <section class="panel ledger-panel">
    <header class="panel-header">
      <h2 class="panel-title"><ListChecks :size="15" /> 交易日志 / 持仓流水</h2>
      <span class="terminal-chip">
        {{ summary.count }} 笔交易 · 当前持仓 {{ Number(summary.position).toLocaleString() }} 股
      </span>
    </header>

    <div class="ledger-summary" v-if="tradeRows.length">
      <div>
        <span>交易笔数</span>
        <strong>{{ summary.count }}</strong>
      </div>
      <div>
        <span>当前持仓</span>
        <strong>{{ Number(summary.position).toLocaleString() }} 股</strong>
      </div>
      <div>
        <span>已实现盈亏</span>
        <strong :class="summary.realizedPnl >= 0 ? 'bull' : 'bear'">{{ formatSignedMoney(summary.realizedPnl) }}</strong>
      </div>
    </div>

    <div class="ledger-body">
      <div v-if="!tradeRows.length" class="empty-state">
        暂无交易信号。当前策略在该区间没有触发买卖条件。
      </div>
      <table v-else>
        <thead>
          <tr>
            <th>时间</th>
            <th>成交口径</th>
            <th>股票</th>
            <th>操作</th>
            <th>成交价</th>
            <th>数量</th>
            <th>成交金额</th>
            <th>持仓</th>
            <th>现金流</th>
            <th>单笔盈亏</th>
            <th>交易原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="trade in tradeRows" :key="trade.id">
            <td data-label="时间">{{ trade.time }}</td>
            <td data-label="成交口径" class="execution-cell">
              <span class="execution-chip" :class="{ estimated: trade.execution_precision === 'daily_estimated' }">
                {{ executionLabel(trade) }}
              </span>
              <small>{{ executionNote(trade) }}</small>
            </td>
            <td data-label="股票">{{ trade.name || trade.symbol }}</td>
            <td data-label="操作">
              <span class="dir-pill" :class="trade.direction === 'SELL' ? 'sell' : 'buy'">
                {{ trade.direction === "SELL" ? "卖" : "买" }}
              </span>
            </td>
            <td data-label="成交价">{{ store.formatPrice(trade.price) }}</td>
            <td data-label="数量">{{ Number(trade.quantity || 0).toLocaleString() }}</td>
            <td data-label="成交金额">{{ formatMoney(trade.amount) }}</td>
            <td data-label="持仓">{{ Number(trade.position || 0).toLocaleString() }}</td>
            <td data-label="现金流" :class="trade.cashFlow >= 0 ? 'bull' : 'bear'">{{ formatSignedMoney(trade.cashFlow) }}</td>
            <td data-label="单笔盈亏" :class="trade.rowPnl == null ? '' : trade.rowPnl >= 0 ? 'bull' : 'bear'">
              {{ trade.rowPnl == null ? "未平仓" : formatSignedMoney(trade.rowPnl) }}
            </td>
            <td data-label="交易原因" class="reason-cell">{{ trade.reason || trade.audit || "--" }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.ledger-panel {
  min-height: 260px;
}

.ledger-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 10px 12px 0;
}

.ledger-summary div {
  border: 1px solid rgba(212, 175, 55, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
  padding: 10px;
}

.ledger-summary span {
  display: block;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
}

.ledger-summary strong {
  display: block;
  margin-top: 6px;
  color: var(--text-main);
  font-family: var(--font-mono);
  font-size: 16px;
}

.ledger-body {
  max-height: 420px;
  overflow: auto;
  padding-top: 8px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: 11px;
}

th,
td {
  border-bottom: 1px solid rgba(212, 175, 55, 0.09);
  padding: 10px 12px;
  text-align: left;
  white-space: nowrap;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: rgba(18, 17, 21, 0.96);
  color: var(--text-muted);
  font-size: 10px;
}

td {
  color: var(--text-main);
}

.bull {
  color: var(--bull-red);
}

.bear {
  color: var(--bear-green);
}

.dir-pill {
  display: inline-grid;
  place-items: center;
  min-width: 28px;
  height: 22px;
  border-radius: 4px;
  color: #fff;
  font-weight: 900;
}

.dir-pill.buy {
  background: var(--bull-red);
}

.dir-pill.sell {
  background: var(--bear-green);
}

.reason-cell {
  max-width: 420px;
  color: var(--gold);
  overflow: hidden;
  text-overflow: ellipsis;
}

.execution-cell {
  min-width: 118px;
}

.execution-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgba(50, 215, 75, 0.32);
  border-radius: 999px;
  color: var(--bear-green);
  background: rgba(50, 215, 75, 0.08);
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 900;
}

.execution-chip.estimated {
  border-color: rgba(255, 214, 10, 0.32);
  color: #ffd60a;
  background: rgba(255, 214, 10, 0.08);
}

.execution-cell small {
  display: block;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.2;
}

@media (max-width: 720px) {
  .ledger-summary {
    grid-template-columns: 1fr;
  }

  table,
  thead,
  tbody,
  tr,
  th,
  td {
    display: block;
  }

  thead {
    display: none;
  }

  tr {
    margin: 10px;
    border: 1px solid rgba(212, 175, 55, 0.12);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.025);
    padding: 8px;
  }

  td {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 1px solid rgba(212, 175, 55, 0.08);
    white-space: normal;
  }

  td::before {
    content: attr(data-label);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 900;
  }

  .reason-cell {
    max-width: none;
    overflow: visible;
    text-overflow: clip;
  }
}
</style>
