# code to read sensor data from api at luftdaten.info and print it to console

import time 
import pandas as pd
import datetime
from pytz import timezone
import sys
import os
import re
import numpy as np
import sqlite3
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


DB_NAME = "data/radiation.db" # sqlite3

TZ = timezone('Europe/Berlin')


def resample_and_export(sid, N, RESAMPLE_FREQ):
    # read rows for this sensor

    df = pd.read_sql_query(
        "SELECT timestamp, counts_per_minute FROM radiation_data WHERE sensor_id = ? ORDER BY timestamp",
        conn,
        params=(sid,),
    )
    if df.empty:
        return []

    # parse timestamps and drop bad rows
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return []

    # ensure timestamps are in the configured timezone
    try:
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(TZ)
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert(TZ)
    except Exception:
        # best-effort localization if above fails
        df["timestamp"] = df["timestamp"].dt.tz_localize(TZ, ambiguous="infer", nonexistent="shift_forward")

    # drop old entries older than N days
    cutoff = pd.Timestamp.now(TZ) - pd.Timedelta(days=N)
    df = df[df["timestamp"] >= cutoff]
    if df.empty:
        print(f"No recent data for sensor {sid}, {N}")
        return []

    df = df.sort_values("timestamp").set_index("timestamp")

    # ensure numeric counts and resample to 15-minute bins (mean if multiple in bin)
    df["counts_per_minute"] = pd.to_numeric(df["counts_per_minute"], errors="coerce")
    series = df["counts_per_minute"].resample(RESAMPLE_FREQ).mean()

    if series.empty or series.isna().all():
        # nothing to save for this sensor
        print(f"No valid data for sensor {sid}, {N}")
        return []

    # interpolate internal NaNs by time, then fill leading/trailing gaps
    series = series.interpolate(method="time")
    series = series.ffill().bfill()

    return series
    

if __name__ == "__main__":

        db_path = DB_NAME
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # check for -png flag on command line
        ENABLE_PNG = "-png" in sys.argv[1:]

        # get unique sensor ids
        cur.execute("SELECT DISTINCT sensor_id FROM radiation_data")
        sensor_rows = cur.fetchall()
        sensor_ids = [r[0] for r in sensor_rows]

        os.makedirs("data", exist_ok=True)

        for i,sid in enumerate(sensor_ids):
            day_data = resample_and_export(sid, 2, "15min")
            if len(day_data) == 0:
                continue
            # prepare JSON output
            out = []
            for ts, val in day_data.items():
                out.append({"timestamp": ts.isoformat(), "counts_per_minute": None if pd.isna(val) else float(val)})
            out_path = os.path.join("data", f"series_day_{str(int(sid))}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"sensor_id": str(int(sid)), "series": out}, f, ensure_ascii=False, indent=2)
                
            # also create a PNG plot for first 10 sensors only
            if ENABLE_PNG and (i <= 10):
                if not day_data.empty:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.plot(day_data.index, day_data.values, marker="o", ms=3, lw=1, color="#1f77b4")
                    ax.set_xlabel("time")
                    ax.set_ylabel("counts_per_minute")
                    ax.set_title(f"Sensor {int(sid)} — last {2} days")
                    ax.grid(True, alpha=0.3)

                    # pretty time formatting (respect timezone)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M", tz=TZ))
                    fig.autofmt_xdate()

                    out_png = os.path.join("data", f"series_day_{int(sid)}.png")
                    fig.tight_layout()
                    fig.savefig(out_png, dpi=150)
                    plt.close(fig)

            month_data = resample_and_export(sid, 30, "6h")
            if len(month_data) == 0:
                continue
            # prepare JSON output
            out = []
            for ts, val in month_data.items():
                out.append({"timestamp": ts.isoformat(), "counts_per_minute": None if pd.isna(val) else float(val)})
            out_path = os.path.join("data", f"series_month_{str(int(sid))}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"sensor_id": str(int(sid)), "series": out}, f, ensure_ascii=False, indent=2)
                
            # also create a PNG plot for first 10 sensors only
            if ENABLE_PNG and (i <= 10):
                if not month_data.empty:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.plot(month_data.index, month_data.values, marker="o", ms=3, lw=1, color="#1f77b4")
                    ax.set_xlabel("time")
                    ax.set_ylabel("counts_per_minute")
                    ax.set_title(f"Sensor {int(sid)} — last {30} days")
                    ax.grid(True, alpha=0.3)

                    # pretty time formatting (respect timezone)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M", tz=TZ))
                    fig.autofmt_xdate()

                    out_png = os.path.join("data", f"series_month_{int(sid)}.png")
                    fig.tight_layout()
                    fig.savefig(out_png, dpi=150)
                    plt.close(fig)

