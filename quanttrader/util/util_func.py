#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import pickle
from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

__all__ = [
    "read_ohlcv_csv",
    "read_fxmacrodata_ohlcv",
    "read_intraday_bar_pickle",
    "read_tick_data_txt",
    "save_one_run_results",
]

FXMACRODATA_API_ROOT = "https://api.fxmacrodata.com/v1"


def read_ohlcv_csv(
    filepath: str, adjust: bool = True, tz: str = "America/New_York"
) -> pd.DataFrame:

    df = pd.read_csv(filepath, header=0, parse_dates=True, sep=",", index_col=0)
    df.index = df.index + pd.DateOffset(hours=16)
    df.index = df.index.tz_localize(tz)  # US/Eastern, UTC
    # df.index = pd.to_datetime(df.index)
    if adjust:
        df["Open"] = df["Adj Close"] / df["Close"] * df["Open"]
        df["High"] = df["Adj Close"] / df["Close"] * df["High"]
        df["Low"] = df["Adj Close"] / df["Close"] * df["Low"]
        df["Volume"] = df["Adj Close"] / df["Close"] * df["Volume"]
        df["Close"] = df["Adj Close"]

    df = df[["Open", "High", "Low", "Close", "Volume"]]
    return df


def _split_fx_pair(pair: str) -> tuple[str, str]:
    pair = pair.upper().replace("/", "").replace("-", "").replace("_", "")
    if len(pair) != 6:
        raise ValueError("FX pair must be formatted like 'EURUSD' or 'EUR/USD'")
    return pair[:3], pair[3:]


def read_fxmacrodata_ohlcv(
    pair: str,
    start_date: str,
    end_date: str,
    api_key: str | None = None,
    api_root: str = FXMACRODATA_API_ROOT,
    tz: str = "UTC",
) -> pd.DataFrame:
    """Read FXMacroData daily FX reference rates as OHLCV bars.

    FXMacroData publishes one official reference value per currency pair and
    date. The value is mapped to Open, High, Low, and Close with zero Volume so
    the result can be passed to BacktestEngine.add_data.
    """
    base, quote = _split_fx_pair(pair)
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": 5000,
    }
    headers = {"X-API-Key": api_key} if api_key else {}

    url = "{}/forex/{}/{}?{}".format(
        api_root.rstrip("/"),
        base,
        quote,
        urlencode(params),
    )
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    records = []
    for row in payload.get("data", []):
        value = float(row["val"])
        records.append((row["date"], value, value, value, value, 0.0))

    df = pd.DataFrame.from_records(
        records,
        columns=["Date", "Open", "High", "Low", "Close", "Volume"],
    )
    if df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").set_index("Date")
    df.index = df.index.tz_localize(tz)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def read_intraday_bar_pickle(
    filepath: str, syms: list[str], tz: str = "America/New_York"
) -> dict[str, pd.DataFrame]:

    dict_hist_data = {}
    if os.path.isfile(filepath):
        with open(filepath, "rb") as f:
            dict_hist_data = pickle.load(f)
    dict_ret = {}
    for sym in syms:
        try:
            df = dict_hist_data[sym]
            df.index = df.index.tz_localize(tz)  # # US/Eastern, UTC
            dict_ret[sym] = df
        except Exception as e:
            print(f"An error occurred: {e}")
    return dict_ret


def read_tick_data_txt(
    filepath: str, remove_bo: bool = True, tz: str = "America/New_York"
) -> dict[str, pd.DataFrame]:
    """
    filename = yyyymmdd.txt
    """
    asofdate = filepath.split("/")[-1].split(".")[0]
    data = pd.read_csv(filepath, sep=",", header=None)
    data.columns = [
        "Time",
        "ProcessTime",
        "Ticker",
        "Type",
        "BidSize",
        "Bid",
        "Ask",
        "AskSize",
        "Price",
        "Size",
    ]
    data = data[
        [
            "Time",
            "Ticker",
            "Type",
            "BidSize",
            "Bid",
            "Ask",
            "AskSize",
            "Price",
            "Size",
        ]
    ]
    if remove_bo:
        data = data[data.Type.str.contains("TickType.TRADE")]
    data.Time = data.Time.apply(
        lambda t: datetime.strptime(f"{asofdate} {t}", "%Y%m%d %H:%M:%S.%f")
    )
    data.set_index("Time", inplace=True)
    data.index = data.index.tz_localize(tz)  # # US/Eastern, UTC
    dg = data.groupby("Ticker")
    dict_ret = {}
    for sym, dgf in dg:
        dgf = dgf[~dgf.index.duplicated(keep="last")]
        dict_ret[sym] = dgf
    return dict_ret


def save_one_run_results(
    output_dir: str,
    equity: pd.DataFrame,
    df_positions: pd.DataFrame,
    df_trades: pd.DataFrame,
    batch_tag: bool = False,
) -> None:

    df_positions.to_csv(f"{output_dir}/positions_{batch_tag if batch_tag else ""}.csv")
    df_trades.to_csv(f"{output_dir}/trades_{batch_tag if batch_tag else ""}.csv")
    equity.to_csv(f"{output_dir}/equity_{batch_tag if batch_tag else ""}.csv")
