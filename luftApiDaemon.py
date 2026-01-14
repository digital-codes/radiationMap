# code to read sensor data from api at luftdaten.info and print it to console

from turtle import left
import requests
import time 
import pandas as pd
import json
import datetime
from pytz import timezone
import sys
import os
from requests.utils import requote_uri
import re
import numpy as np
import sqlite3

# put this line into your crontab (crontab -e) to run every 5 minutes
# */5 * * * * cd /home/kugel/daten/work/python/openData/luftdaten.info && /usr/bin/python3 /home/kugel/daten/work/python/openData/luftdaten.info/luftApiDaemon.py >> /home/kugel/daten/work/python/openData/luftdaten.info/luftApiDaemon.log 2>&1

API_BASE = 'https://data.sensor.community/airrohr/v1/filter/'

DB_NAME = "data/radiation.db" # sqlite3

TZ = timezone('Europe/Berlin')


def flattenData(data,items = []):
    records = []
    for s in data:
        base_info = {
            "file_id": s.get('id', 'N/A'),
            'sensor_id': s.get('sensor', {}).get('id', 'N/A'),
            'timestamp': s.get('timestamp', 'N/A'),
            'latitude': s.get('location', {}).get('latitude', 'N/A'),
            'longitude': s.get('location', {}).get('longitude', 'N/A'),
            'sensor_type': s.get('sensor', {}).get('sensor_type', {}).get('name', 'N/A'),
            'manufacturer': s.get('sensor', {}).get('sensor_type', {}).get('manufacturer', 'N/A')
        }
        # build a map of available measurements for this sensor
        value_map = {m.get('value_type'): m.get('value') for m in s.get('sensordatavalues', []) if m.get('value_type')}
        # decide which items to iterate: use provided master list if given, otherwise use items present in this reading
        current_items = items if items else list(value_map.keys())
        record = base_info.copy()
        # do not allow measurement items to overwrite reserved base fields (e.g. timestamp/latitude)
        reserved_keys = set(base_info.keys())
        for item in current_items:
            if item in reserved_keys:
                # preserve the base_info value for this key
                continue
            record[item] = value_map.get(item, 'N/A')
        records.append(record)
    return pd.DataFrame(records)

def fetch_sensor_data_filtered(sensor_type, country=None, timeout=10):
    """
    Fetch sensor data filtered by sensor_type (string or list) and optional country (string or list).
    Returns parsed JSON list on success or None on failure.
    """


    # normalize inputs
    if isinstance(sensor_type, (list, tuple)):
        type_str = ",".join(map(str, sensor_type))
    else:
        type_str = str(sensor_type)

    if country:
        if isinstance(country, (list, tuple)):
            country_str = ",".join(map(str, country))
        else:
            country_str = str(country)
    else:
        country_str = None

    # build query part expected by the API: e.g. "type=SDS011,BME280&country=DE,NL"
    query_parts = [f"type={type_str}"]
    if country_str:
        query_parts.append(f"country={country_str}")
    query = "&".join(query_parts)

    url = requote_uri(API_BASE + query)

    headers = {
        "User-Agent": "luftdaten-fetcher/1.0 (+https://example.org; contact: ops@example.org)"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Error fetching filtered data from API: {e}")
        return None


if __name__ == "__main__":
    with open("data/sensor_types.json", "r") as f:
        type_list = json.load(f)
    with open("data/measurement_items.json", "r") as f:
        measurement_list = json.load(f)

    # radion sensors: use all types starting with radiation
    radSensors = [t for t in type_list if t.lower().startswith('radiation')]
    print(f"\nFound {len(radSensors)} radiation sensor types:")
    rad = []
    # for rs in radSensors:
    #     print(f" - {rs}")                   
    #     r = fetch_sensor_data_filtered(sensor_type=rs) # , country='DE')
    #     print(f"  Fetched {len(r) if r else 0} records for sensor type '{rs}'.")
    #     if r:
    #         rad.extend(r)
    r = fetch_sensor_data_filtered(sensor_type=radSensors) # , country='DE')
    print(f"  Fetched {len(r) if r else 0} records for sensor type '{radSensors}'.")
    if r:
        rad.extend(r)
    if len(rad) > 0:
        print(f"\nFetched {len(rad)} records for filtered sensor data (Radiation).")
        # flatten and write to file radiation.csv/json
        df_rad = flattenData(rad, measurement_list)
        os.makedirs('data', exist_ok=True)
        df_types = df_rad['sensor_type'].value_counts()
        print("\nSensor type counts in fetched radiation data:")
        for stype, count in df_types.items():
            print(f" - {stype}: {count} records")
        df_sensors = df_rad['sensor_id'].unique()
        print(f"\nUnique sensors in fetched radiation data: {len(df_sensors)}")
        df_rad.sort_values(by=['sensor_id', 'timestamp'], inplace=True) 
        df_rad.to_json('data/radiation.json', orient='records', lines=True, force_ascii=False)
        df_rad.to_csv('data/radiation.csv', index=False)
        print(f"Wrote {len(df_rad)} records for radiation sensors to data/radiation.json and data/radiation.csv")
        # pick relevant columns (keep only ones that exist)
        base_cols = ["file_id", "sensor_id", "timestamp", "latitude", "longitude", "sensor_type", "manufacturer"]
        existing_base = [c for c in base_cols if c in df_rad.columns]

        radiation_cols = ["counts", "counts_per_minute", "hv_pulses", "sample_time_ms"]
        relevant_cols = existing_base.copy()
        # add relevant measurement columns
        relevant_cols.append(radiation_cols[0])  # counts
        relevant_cols.append(radiation_cols[1])  # counts_per_minute
        relevant_cols.append(radiation_cols[2])  # hv_pulses
        relevant_cols.append(radiation_cols[3])  # sample_time_ms

        print(f"Relevant columns for radiation data: {relevant_cols}")

        # build reduced dataframe
        df_rad_relevant = df_rad[relevant_cols].copy()

        # convert measurement columns to numeric
        df_rad_relevant[radiation_cols[0]] = pd.to_numeric(df_rad_relevant[radiation_cols[0]], errors='coerce')
        df_rad_relevant[radiation_cols[1]] = pd.to_numeric(df_rad_relevant[radiation_cols[1]], errors='coerce')
        df_rad_relevant["hv_pulses"] = pd.to_numeric(df_rad_relevant["hv_pulses"], errors='coerce')
        df_rad_relevant["sample_time_ms"] = pd.to_numeric(df_rad_relevant["sample_time_ms"], errors='coerce')

        # keep only rows with non-null, non-negative and non-zero values
        mask_nonneg = df_rad_relevant[radiation_cols[1]].notnull() & (df_rad_relevant[radiation_cols[1]] >= 0)
        mask_pos = df_rad_relevant[radiation_cols[1]] > 0
        df_nonneg = df_rad_relevant[mask_nonneg].copy()
        df_pos = df_rad_relevant[mask_pos].copy()

        # mean count per minute per sensor (only using strictly positive values)
        per_sensor_mean = df_pos.groupby("sensor_id")[radiation_cols[1]].mean().reset_index(name="mean_count_per_min")
        overall_mean_all_measurements = df_pos[radiation_cols[1]].mean() if not df_pos.empty else np.nan
        overall_mean_per_sensor = per_sensor_mean["mean_count_per_min"].mean() if not per_sensor_mean.empty else np.nan

        # compute evaluation column based on count_per_min relative to mean
        mean_value = overall_mean_all_measurements
        if pd.isna(mean_value):
            # fallback: compute mean from positive values in the reduced dataframe
            mean_value = df_rad_relevant[radiation_cols[1]][df_rad_relevant[radiation_cols[1]] > 0].mean()

        cpm = df_rad_relevant[radiation_cols[1]]

        cond_neg_or_zero = cpm <= 0
        cond_less_than_mean = (cpm > 0) & (cpm < mean_value)
        cond_greater_than_mean = cpm > mean_value

        # check db: throw if DB file does not exist (do not create directories or files here)
        db_path = DB_NAME

        if not os.path.isfile(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # remove all data older than 40 days 
        dayLimit = 40 # keep max of 40 days
        print(f"Deleting data older than {dayLimit} days from database.")
        cur.execute(f"DELETE FROM radiation_data WHERE timestamp < datetime('now', '-{dayLimit} days')")
        conn.commit()
        cur.execute("VACUUM;")
        conn.commit()

        # prepare columns and sqlite types based on dataframe dtypes
        cols = list(df_rad_relevant.columns)

        # build insert statement (use INSERT OR IGNORE to skip existing sensor_id+timestamp)
        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join([f'"{c}"' for c in cols])
        insert_sql = f'INSERT OR IGNORE INTO radiation_data ({col_list}) VALUES ({placeholders})'

        # prepare rows, converting NaN to None
        to_insert = []
        for _, row in df_rad_relevant.iterrows():
            vals = []
            for c in cols:
                v = row[c]
                if pd.isna(v):
                    vals.append(None)
                else:
                    vals.append(v)
            to_insert.append(tuple(vals))

        before = cur.execute("SELECT COUNT(*) FROM radiation_data").fetchone()[0]
        if to_insert:
            cur.executemany(insert_sql, to_insert)
            conn.commit()
        afterIns = cur.execute("SELECT COUNT(*) FROM radiation_data").fetchone()[0]

        inserted = afterIns - before
        print(f"Inserted {inserted} new rows into {db_path} (table radiation_data).")

        # ------------------------------------------------------------------
        # Delete duplicates, keeping the row with the smallest `id`
        # ------------------------------------------------------------------
        # The sub‑query finds the minimum id for each (itemId, timestamp) group.
        # Any row whose id is NOT in that list gets removed.
        # use sqlite impicit rowid as unique identifier
        cur.execute("DELETE FROM radiation_data WHERE rowid NOT IN (SELECT MIN(rowid) FROM radiation_data GROUP BY sensor_id, timestamp);")
        conn.commit()

        afterCln = cur.execute("SELECT COUNT(*) FROM radiation_data").fetchone()[0]
        deleted = afterIns - afterCln
        print(f"Left {afterCln} rows after deleting {deleted} in {db_path} (table radiation_data) after removing duplicates.")

        conn.close()


        # open DB, get latest row per sensor_id, build GeoJSON FeatureCollection and save
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        sensors = cur.execute("SELECT COUNT(DISTINCT sensor_id) FROM radiation_data").fetchone()[0]
        print(f"Building GeoJSON FeatureCollection for latest data from {sensors} sensors.")

        # latest row per sensor_id
        query = """
        SELECT
            rd.sensor_id,
            rd.sensor_type,
            rd.counts_per_minute,
            rd.latitude,
            rd.longitude,
            rd.timestamp
        FROM radiation_data rd
        JOIN (
                SELECT sensor_id, MAX(timestamp) AS max_ts
                FROM radiation_data
                GROUP BY sensor_id
            ) AS latest
        ON rd.sensor_id = latest.sensor_id
        AND rd.timestamp = latest.max_ts;
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []

        features = []
        for row in rows:
                rec = dict(zip(cols, row))
                lat = rec.get("latitude")
                lon = rec.get("longitude")
                # try to coerce lat/lon to floats; skip if not valid
                try:
                        if lat is None or lon is None:
                                continue
                        lat_f = float(lat)
                        lon_f = float(lon)
                except Exception:
                        continue

                properties = {
                        "sensor_id": rec.get("sensor_id"),
                        "sensor_type": rec.get("sensor_type"),
                        # map DB column counts_per_minute -> output property count_per_minute
                        "count_per_minute": rec.get("counts_per_minute"),
                        "timestamp": rec.get("timestamp")
                }

                feature = {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon_f, lat_f]},
                        "properties": properties
                }
                features.append(feature)

        feature_collection = {"type": "FeatureCollection", "features": features}

        os.makedirs("data", exist_ok=True)
        out_path = os.path.join("data", "radiationLatest.geojson")
        with open(out_path, "w", encoding="utf-8") as f:
                json.dump(feature_collection, f, ensure_ascii=False, indent=2)

        print(f"Wrote {len(features)} features to {out_path}")

        cur.close()
        conn.close()
        
    else:
        print("No data fetched for filtered sensor data.")
