# code to read sensor data from api at luftdaten.info and print it to console

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


#const API_URL = 'https://api.sensor.community/static/v1/data.json';	// URL to API on 'luftdaten.info'
#const API24_URL = 'https://api.luftdaten.info/static/v2/data.24h.json';	// URL to API on 'luftdaten.info'
#const SAVE_NAME = 'data/aktdata.json';  // filename for actual data
#const MY_SIDS = 'data/mysids.json';      // file, where my SIDs are stored
#const PROP_COLL='properties';
#const MAP_COLL='mapdata';


API_URL = 'https://api.sensor.community/static/v1/data.json'	# URL to API on 'luftdaten.info'
API24_URL = 'https://api.luftdaten.info/static/v2/data.24h.json'	# URL to API on 'luftdaten.info'
SAVE_NAME = 'data/aktdata.json'  # filename for actual data
MY_SIDS = 'data/mysids.json'      # file, where my SIDs are stored
PROP_COLL='properties'
MAP_COLL='mapdata'  

DB_NAME = "data/radiation.db" # sqlite3

TZ = timezone('Europe/Berlin')

def fetch_sensor_data():
    try:
        response = requests.get(API_URL)
        response.raise_for_status()  # Raise an error for bad status codes
        data = response.json()
        return data
    except requests.RequestException as e:
        print(f"Error fetching data from API: {e}")
        return None


def print_sensor_data(data):
    if data is None:
        print("No data to display.")
        return
    for sensor in data:
        sensor_id = sensor.get('sensor', {}).get('id', 'N/A')
        timestamp = sensor.get('timestamp', 'N/A')
        location = sensor.get('location', {})
        latitude = location.get('latitude', 'N/A')
        longitude = location.get('longitude', 'N/A')
        measurements = sensor.get('sensordatavalues', [])
        type_name = sensor.get('sensor', {}).get('sensor_type', {}).get('name', 'N/A')
        manuf_name = sensor.get('sensor', {}).get('sensor_type', {}).get('manufacturer', 'N/A') 
        
        print(f"Sensor ID: {sensor_id}")
        print(f"Location: Latitude {latitude}, Longitude {longitude}")
        print(f"Timestamp: {timestamp}")
        print(f"Sensor Type: {type_name}")
        print(f"Manufacturer: {manuf_name}")
        print("Measurements:")
        for measurement in measurements:
            value_type = measurement.get('value_type', 'N/A')
            value = measurement.get('value', 'N/A')
            print(f"  {value_type}: {value}")
        print("-" * 40)

def findItemsAndManufacturers(data):
    measurement_items = set()
    manufacturers = set()
    types = set()

    for s in data:
        # collect measurement item types
        for m in s.get('sensordatavalues', []):
            vt = m.get('value_type')
            if vt:
                measurement_items.add(vt)

        # collect manufacturer information from common possible locations
        manu = None
        manu = s.get('sensor', {}).get('sensor_type', {}).get('manufacturer') or manu
        manu = s.get('sensor', {}).get('manufacturer') or manu
        manu = (s.get('sensor_type', {}) if isinstance(s.get('sensor_type'), dict) else {}).get('manufacturer') or manu
        if manu:
            manufacturers.add(manu)
        type_name = s.get('sensor', {}).get('sensor_type', {}).get('name')
        if type_name:
            types.add(type_name)

    return list(sorted(measurement_items)), list(sorted(manufacturers)), list(sorted(types)) 

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

    FILTER_BASE = 'https://data.sensor.community/airrohr/v1/filter/'

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

    url = requote_uri(FILTER_BASE + query)

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

def makeRadiationSchema(columns):
    # build a small schema describing each relevant column for later SQL table creation
    schema = []
    for idx, col in enumerate(columns):
        col_type = "text"
        # prefer explicit name checks
        if col.lower() == "timestamp" or "time" in col.lower() or "date" in col.lower():
            col_type = "timestamp"
        else:
            # use pandas dtype heuristics first
            try:
                if pd.api.types.is_numeric_dtype(df_rad_relevant[col].dtype):
                    col_type = "number"
                elif pd.api.types.is_datetime64_any_dtype(df_rad_relevant[col].dtype):
                    col_type = "timestamp"
                else:
                    # try coercion to numeric to detect numeric-like text columns
                    coerced = pd.to_numeric(df_rad_relevant[col], errors="coerce")
                    if coerced.notna().sum() > 0 and coerced.notna().sum() >= len(df_rad_relevant) * 0.5:
                        # treat as number if at least half the values coerce to numeric
                        col_type = "number"
            except Exception:
                col_type = "text"

        schema.append({"order": idx, "name": col, "type": col_type})

    os.makedirs("data", exist_ok=True)
    with open("data/radiation_relevant_schema.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if 'test' in sys.argv[1:]:
        try:
            print("Running in test mode, reading data from mist.json")
            with open('mist.json', 'r', encoding='utf-8') as f:
                sensor_data = json.load(f)
        except Exception as e:
            print(f"Error reading mist.json: {e}")
            raise
    else:
        sensor_data = fetch_sensor_data()
    print("Fetched sensor data:", len(sensor_data) if sensor_data else 0, "sensors")    
    
    print_sensor_data(sensor_data[:10])  # Print data for first 10 sensors
    
    # gather unique measurement items and manufacturers and optionally save them
    if not sensor_data:
        print("No sensor data available to extract lists.")
    else:
        measurement_list, manufacturer_list, type_list = findItemsAndManufacturers(sensor_data)   
        
        print(f"\nFound {len(measurement_list)} unique measurement items:")
        for item in measurement_list:
            print(f" - {item}")

        print(f"\nFound {len(manufacturer_list)} unique manufacturers:")
        for m in manufacturer_list:
            print(f" - {m}")

        print(f"\nFound {len(type_list)} unique sensor types:")
        for t in type_list:
            print(f" - {t}")

        # optionally save lists for later use
        os.makedirs('data', exist_ok=True)
        with open('data/measurement_items.json', 'w', encoding='utf-8') as f:
            json.dump(measurement_list, f, ensure_ascii=False, indent=2)
        with open('data/manufacturers.json', 'w', encoding='utf-8') as f:
            json.dump(manufacturer_list, f, ensure_ascii=False, indent=2)
        with open('data/sensor_types.json', 'w', encoding='utf-8') as f:
            json.dump(type_list, f, ensure_ascii=False, indent=2)   
            
        # flatten data into a DataFrame
        df = flattenData(sensor_data, measurement_list)
        print(f"\nFlattened data into DataFrame with {len(df)} records.")
        print(df.head())
        df.to_json('data/flattened_sensor_data.json', orient='records', lines=True)
        # save rows for manufacturer "EcoCurious" into separate file
        target = "EcoCurious".strip().lower()
        mask = df['manufacturer'].astype(str).str.strip().str.lower() == target
        df_ecocurious = df[mask]

        if not df_ecocurious.empty:
            os.makedirs('data', exist_ok=True)
            df_ecocurious.sort_values(by=['sensor_id', 'timestamp'], inplace=True) 
            df_ecocurious.to_json('data/ecocurious.json', orient='records', lines=True, force_ascii=False)
            df_ecocurious.to_csv('data/ecocurious.csv', index=False)
            print(f"Wrote {len(df_ecocurious)} records for manufacturer 'EcoCurious' to data/ecocurious.json and data/ecocurious.csv")
        else:
            print("No records found for manufacturer 'EcoCurious'")

        # radion sensors: use all types starting with radiation
        radSensors = [t for t in type_list if t.lower().startswith('radiation')]
        print(f"\nFound {len(radSensors)} radiation sensor types:")
        rad = []
        for rs in radSensors:
            print(f" - {rs}")                   
            r = fetch_sensor_data_filtered(sensor_type=rs) # , country='DE')
            print(f"  Fetched {len(r) if r else 0} records for sensor type '{rs}'.")
            if r:
                rad.extend(r)
        if len(rad) > 0:
            print(f"\nFetched {len(rad)} records for filtered sensor data (Radiation).")
            # flatten and write to file radiation.csv/json
            df_rad = flattenData(rad, measurement_list)
            os.makedirs('data', exist_ok=True)
            df_rad.sort_values(by=['sensor_id', 'timestamp'], inplace=True) 
            df_rad.to_json('data/radiation.json', orient='records', lines=True, force_ascii=False)
            df_rad.to_csv('data/radiation.csv', index=False)
            print(f"Wrote {len(df_rad)} records for radiation sensors to data/radiation.json and data/radiation.csv")
            # pick relevant columns (keep only ones that exist)
            base_cols = ["file_id", "sensor_id", "timestamp", "latitude", "longitude", "sensor_type", "manufacturer"]
            existing_base = [c for c in base_cols if c in df_rad.columns]

            count_col = "counts"
            count_per_min_col = "counts_per_minute"

            relevant_cols = existing_base.copy()
            # add relevant measurement columns
            relevant_cols.append(count_col)
            relevant_cols.append(count_per_min_col)
            relevant_cols.append("hv_pulses")
            relevant_cols.append("sample_time_ms")

            print(f"Relevant columns for radiation data: {relevant_cols}")

            # build reduced dataframe
            df_rad_relevant = df_rad[relevant_cols].copy()

            # convert measurement columns to numeric
            df_rad_relevant[count_col] = pd.to_numeric(df_rad_relevant[count_col], errors='coerce')
            df_rad_relevant[count_per_min_col] = pd.to_numeric(df_rad_relevant[count_per_min_col], errors='coerce')
            df_rad_relevant["hv_pulses"] = pd.to_numeric(df_rad_relevant["hv_pulses"], errors='coerce')
            df_rad_relevant["sample_time_ms"] = pd.to_numeric(df_rad_relevant["sample_time_ms"], errors='coerce')

            # prefer using count per minute if available
            if count_per_min_col is None and count_col is not None:
                # no explicit per-minute column found; attempt to treat 'count' as per-minute if that's what you want
                # (user wanted count per minute specifically — here we fallback to using 'count' if no other option)
                count_per_min_col = count_col

            if count_per_min_col is None:
                print("No count-per-minute (or count) column could be identified in df_rad.")
            else:
                # keep only rows with non-null, non-negative and non-zero values
                mask_nonneg = df_rad_relevant[count_per_min_col].notnull() & (df_rad_relevant[count_per_min_col] >= 0)
                mask_pos = df_rad_relevant[count_per_min_col] > 0
                df_nonneg = df_rad_relevant[mask_nonneg].copy()
                df_pos = df_rad_relevant[mask_pos].copy()

                # mean count per minute per sensor (only using strictly positive values)
                per_sensor_mean = df_pos.groupby("sensor_id")[count_per_min_col].mean().reset_index(name="mean_count_per_min")
                overall_mean_all_measurements = df_pos[count_per_min_col].mean() if not df_pos.empty else np.nan
                overall_mean_per_sensor = per_sensor_mean["mean_count_per_min"].mean() if not per_sensor_mean.empty else np.nan

                # compute evaluation column based on count_per_min relative to mean
                mean_value = overall_mean_all_measurements
                if pd.isna(mean_value):
                    # fallback: compute mean from positive values in the reduced dataframe
                    mean_value = df_rad_relevant[count_per_min_col][df_rad_relevant[count_per_min_col] > 0].mean()

                cpm = df_rad_relevant[count_per_min_col]

                cond_neg_or_zero = cpm <= 0
                cond_less_than_mean = (cpm > 0) & (cpm < mean_value)
                cond_greater_than_mean = cpm > mean_value

                # print brief summary
                print(f"Relevant reduced dataframe has {len(df_rad_relevant)} rows, {len(df_pos)} rows with positive count/min.")
                print(f"Per-sensor means computed for {len(per_sensor_mean)} sensors.")
                print(f"Overall mean (all positive measurements): {overall_mean_all_measurements}")
                print(f"Overall mean (mean of per-sensor means): {overall_mean_per_sensor}")

                # optionally save results
                os.makedirs("data", exist_ok=True)
                df_rad_relevant.to_csv("data/radiation_relevant.csv", index=False)
                per_sensor_mean.to_csv("data/radiation_per_sensor_mean_cpm.csv", index=False)

                schema_path = "data/radiation_relevant_schema.json"
                if not os.path.exists(schema_path):
                    try:
                        makeRadiationSchema(list(df_rad_relevant.columns))
                        print(f"Created radiation schema: {schema_path}")
                    except Exception as e:
                        print(f"Error creating radiation schema: {e}")

                db_path = DB_NAME
                os.makedirs(os.path.dirname(db_path), exist_ok=True)

                conn = sqlite3.connect(db_path)
                cur = conn.cursor()

                # prepare columns and sqlite types based on dataframe dtypes
                cols = list(df_rad_relevant.columns)
                col_defs = []
                for c in cols:
                    if pd.api.types.is_numeric_dtype(df_rad_relevant[c].dtype):
                        typ = "REAL"
                    elif "time" in c.lower() or "date" in c.lower() or c.lower() == "timestamp":
                        typ = "TEXT"
                    else:
                        typ = "TEXT"
                    col_defs.append(f'"{c}" {typ}')

                # create table with UNIQUE constraint on sensor_id + timestamp so duplicates are ignored
                unique_clause = ""
                if "sensor_id" in cols and "timestamp" in cols:
                    unique_clause = ", UNIQUE(\"sensor_id\",\"timestamp\")"
                create_sql = f'CREATE TABLE IF NOT EXISTS radiation_data ({", ".join(col_defs)}{unique_clause});'
                cur.execute(create_sql)

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
                after = cur.execute("SELECT COUNT(*) FROM radiation_data").fetchone()[0]

                inserted = after - before
                print(f"Inserted {inserted} new rows into {db_path} (table radiation_data).")

                conn.close()


                # open DB, get latest row per sensor_id, build GeoJSON FeatureCollection and save
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()

                query = """
                SELECT t.sensor_id, t.sensor_type, t.counts_per_minute, t.latitude, t.longitude, t.timestamp
                FROM radiation_data t
                JOIN (
                    SELECT sensor_id, MAX(timestamp) AS max_ts
                    FROM radiation_data
                    GROUP BY sensor_id
                ) m ON t.sensor_id = m.sensor_id AND t.timestamp = m.max_ts
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
