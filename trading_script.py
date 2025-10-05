#!/usr/bin/env python3
"""
Grvt Bracket Limit Orders Bot (loop version)
Places two limit orders with filters:
  - BUY below best ask
  - SELL above best bid
Skips placement if any open orders exist.
Runs in loop with configurable wait and max attempts.
"""

import os
import time
import numpy as np
from collections import deque
from pysdk.grvt_ccxt import GrvtCcxt
from pysdk.grvt_ccxt_env import GrvtEnv
from dotenv import load_dotenv

load_dotenv()

# Rolling window for volatility
price_window = deque(maxlen=50)


def get_open_orders(api: GrvtCcxt, symbol: str) -> list[dict]:
    open_orders: list[dict] = api.fetch_open_orders(
        symbol=symbol,
        params={"kind": "PERPETUAL"},
    )
    print(f"open_orders: {open_orders}")
    return open_orders


def compute_orderbook_imbalance(bids, asks, depth=5):
    """Compute Order Book Imbalance (OBI)."""
    bid_vol = sum(float(b["size"]) for b in bids[:depth])
    ask_vol = sum(float(a["size"]) for a in asks[:depth])
    if bid_vol + ask_vol == 0:
        return 0.5
    return bid_vol / (bid_vol + ask_vol)


def place_bracket_limit_orders(
    api: GrvtCcxt,
    symbol: str,
    quantity: float,
    offset: float,
    min_spread: float,
    max_spread: float,
    obi_tolerance: float,
    max_volatility: float,
):
    instrument = api.markets[symbol]["instrument"]
    orderbook = api.fetch_order_book(instrument, limit=10)

    asks = orderbook.get("asks")
    bids = orderbook.get("bids")
    if not asks or not bids:
        raise RuntimeError("Orderbook missing asks or bids")

    best_ask = float(asks[0]["price"])
    best_bid = float(bids[0]["price"])
    spread = best_ask - best_bid
    mid = (best_ask + best_bid) / 2

    print(f"Best Bid: ${best_bid:.2f} | Best Ask: ${best_ask:.2f} | Spread: {spread:.2f}")

    # --- Spread filter ---
    if not (min_spread <= spread <= max_spread):
        print(f"⏸️ Spread out of range ({spread:.2f}), skipping order.")
        return None

    # --- OBI filter ---
    obi = compute_orderbook_imbalance(bids, asks)
    if obi < 0.5 - obi_tolerance or obi > 0.5 + obi_tolerance:
        print(f"⏸️ Orderbook imbalanced (OBI={obi:.2f}), skipping order.")
        return None

    # --- Volatility filter ---
    price_window.append(mid)
    if len(price_window) >= 10:
        log_returns = np.diff(np.log(price_window))
        vol = np.std(log_returns)
        if vol > max_volatility:
            print(f"⏸️ Volatility too high ({vol:.4f}), skipping order.")
            return None

    # BUY limit below best ask
    buy_price = best_ask - offset
    sell_price = best_bid + offset

    if buy_price <= 0 or sell_price <= 0:
        raise ValueError(f"Invalid price levels: buy={buy_price}, sell={sell_price}")

    print(f"Placing BUY limit @ ${buy_price:.2f}")
    buy_resp = api.create_order(
        symbol=symbol, order_type="limit", side="buy", amount=quantity, price=buy_price
    )
    buy_id = buy_resp["metadata"]["client_order_id"]

    print(f"Placing SELL limit @ ${sell_price:.2f}")
    sell_resp = api.create_order(
        symbol=symbol, order_type="limit", side="sell", amount=quantity, price=sell_price
    )
    sell_id = sell_resp["metadata"]["client_order_id"]

    return {
        "buy": {"order_id": buy_id, "price": buy_price},
        "sell": {"order_id": sell_id, "price": sell_price},
    }


def main():
    # --- Load environment ---
    api_key = os.getenv("GRVT_API_KEY")
    trading_account_id = os.getenv("GRVT_TRADING_ACCOUNT_ID")
    private_key = os.getenv("GRVT_PRIVATE_KEY")

    if not all([api_key, trading_account_id, private_key]):
        raise EnvironmentError("Missing required env vars: GRVT_API_KEY, GRVT_TRADING_ACCOUNT_ID, GRVT_PRIVATE_KEY")

    params = {
        "api_key": api_key,
        "trading_account_id": trading_account_id,
        "private_key": private_key,
    }

    env_name = os.getenv("GRVT_ENV", "testnet")
    env = GrvtEnv(env_name)
    api = GrvtCcxt(env, logger=None, parameters=params)

    # --- Trading parameters ---
    SYMBOL = os.getenv("GRVT_SYMBOL", "BTC_USDT_Perp")
    QUANTITY = float(os.getenv("GRVT_QUANTITY", "0.001"))
    OFFSET = float(os.getenv("GRVT_OFFSET", "100.0"))

    # --- Filters ---
    MIN_SPREAD = float(os.getenv("GRVT_MIN_SPREAD", "0.5"))
    MAX_SPREAD = float(os.getenv("GRVT_MAX_SPREAD", "50.0"))
    OBI_TOLERANCE = float(os.getenv("GRVT_OBI_TOLERANCE", "0.2"))
    MAX_VOLATILITY = float(os.getenv("GRVT_MAX_VOLATILITY", "0.002"))

    # --- Loop settings ---
    MAX_ATTEMPTS = int(os.getenv("GRVT_MAX_ATTEMPTS", "10"))
    WAIT_SECONDS = int(os.getenv("GRVT_WAIT_SECONDS", "60"))

    attempt = 0
    while attempt < MAX_ATTEMPTS:
        print(f"\n🔁 Attempt {attempt + 1}/{MAX_ATTEMPTS}")

        try:
            # 🔍 Skip if any open orders exist
            open_orders = get_open_orders(api, SYMBOL)
            if open_orders:
                print(f"⚠️ {len(open_orders)} open order(s) found. Skipping new orders.")
                time.sleep(WAIT_SECONDS)
                continue

            results = place_bracket_limit_orders(
                api, SYMBOL, QUANTITY, OFFSET,
                MIN_SPREAD, MAX_SPREAD, OBI_TOLERANCE, MAX_VOLATILITY
            )

            if results:
                print(f"✅ BUY {results['buy']['order_id']} @ {results['buy']['price']:.2f}")
                print(f"✅ SELL {results['sell']['order_id']} @ {results['sell']['price']:.2f}")
                attempt += 1
                time.sleep(WAIT_SECONDS)
            else:
                print("⚠️ Order skipped by filters. Retrying soon...")
                time.sleep(5)

        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()