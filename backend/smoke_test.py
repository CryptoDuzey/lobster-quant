# coding: utf-8
from app.api.v1.backtest import BacktestRequest, generate_strategy_code, validate_logic_expression


def main() -> None:
    request = BacktestRequest(
        stock_id="000001.XSHE",
        start_date="2024-01-01",
        end_date="2024-12-31",
        buy_logic="close > ma20 + 2 * atr",
        sell_logic="close < ma20 - 2 * atr",
    )
    strategy_code = generate_strategy_code(request)
    compile(strategy_code, "<generated_strategy>", "exec")
    validate_logic_expression("close > ma20 and atr > 0")

    try:
        validate_logic_expression("close > unknown_var")
    except ValueError:
        pass
    else:
        raise AssertionError("未知变量没有被拦截")

    print("自检通过：请求校验、策略生成和逻辑错误拦截均正常。")


if __name__ == "__main__":
    main()
