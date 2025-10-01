#!/usr/bin/env python3
"""
Grvt Bracket Limit Orders
Places two limit orders:
  - BUY below best ask
  - SELL above best bid
Configurable via .env file.
"""

import os
from pysdk.grvt_ccxt import GrvtCcxt
from pysdk.grvt_ccxt_env import GrvtEnv
from dotenv import load_dotenv

load_dotenv()

def place_bracket_limit_orders(
    api: GrvtCcxt,
    symbol: str,
    quantity: float,
    offset: float,
):

    instrument = api.markets[symbol]["instrument"]
    """Place buy and sell limit orders around the spread."""
    print(f"Fetching orderbook for {symbol}...")
    orderbook = api.fetch_order_book(instrument, limit=10)

    asks = orderbook.get("asks")
    bids = orderbook.get("bids")
    if not asks or not bids:
        raise RuntimeError("Orderbook missing asks or bids")

    best_ask = float(asks[0]["price"])
    best_bid = float(bids[0]["price"])

    print(f"Best Bid: ${best_bid:.2f} | Best Ask: ${best_ask:.2f}")

    # BUY limit below best ask
    buy_price = best_ask - offset
    if buy_price <= 0:
        raise ValueError(f"Invalid BUY price: {buy_price}")
    print(f"Placing BUY limit @ ${buy_price:.2f}")
    buy_resp = api.create_order(
        symbol=symbol,
        order_type="limit",
        side="buy",
        amount=quantity,
        price=buy_price,
    )
    buy_id = buy_resp["metadata"]["client_order_id"]
    print(f"✅ BUY Order ID: {buy_id}")

    # SELL limit above best bid
    sell_price = best_bid + offset
    if sell_price <= 0:
        raise ValueError(f"Invalid SELL price: {sell_price}")
    print(f"Placing SELL limit @ ${sell_price:.2f}")
    sell_resp = api.create_order(
        symbol=symbol,
        order_type="limit",
        side="sell",
        amount=quantity,
        price=sell_price,
    )
    sell_id = sell_resp["metadata"]["client_order_id"]
    print(f"✅ SELL Order ID: {sell_id}")

    return {
        "buy": {"order_id": buy_id, "price": buy_price},
        "sell": {"order_id": sell_id, "price": sell_price},
    }


def main():
    # Load environment variables
    api_key = os.getenv("GRVT_API_KEY")
    trading_account_id = os.getenv("GRVT_TRADING_ACCOUNT_ID")
    private_key = os.getenv("GRVT_PRIVATE_KEY")

    if not all([api_key, trading_account_id, private_key]):
        raise EnvironmentError(
            "Missing required env vars: GRVT_API_KEY, GRVT_TRADING_ACCOUNT_ID, GRVT_PRIVATE_KEY"
        )

    params = {
        "api_key": api_key,
        "trading_account_id": trading_account_id,
        "private_key": private_key,
    }

    env_name = os.getenv("GRVT_ENV", "testnet")
    env = GrvtEnv(env_name)

    # Initialize client
    api = GrvtCcxt(env, logger=None, parameters=params)

    # Load trading parameters
    SYMBOL = os.getenv("GRVT_SYMBOL", "BTC_USDT_Perp")
    try:
        QUANTITY = float(os.getenv("GRVT_QUANTITY", "0.001"))
        OFFSET = float(os.getenv("GRVT_OFFSET", "100.0"))
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid numeric value in .env: {e}")

    # Place orders
    try:
        results = place_bracket_limit_orders(api, SYMBOL, QUANTITY, OFFSET)
    except Exception as e:
        print(f"❌ Order placement failed: {e}")
        raise

    print("\nSummary:")
    print(f"BUY  → Price: ${results['buy']['price']:.2f}, ID: {results['buy']['order_id']}")
    print(f"SELL → Price: ${results['sell']['price']:.2f}, ID: {results['sell']['order_id']}")


if __name__ == "__main__":
    main()
