import pandas as pd
from pathlib import Path
import re
from datetime import datetime, time


def parse_nmea_time(t_str):
    try:
        hh = int(t_str[0:2])
        mm = int(t_str[2:4])
        ss = float(t_str[4:])
        sec = int(ss)
        micro = int((ss - sec) * 1e6)
        return time(hh, mm, sec, micro)
    except:
        return None


def parse_hehdt(msg, sys_ts, delta_ms):
    try:
        parts = msg.split(',')
        return {
            'sys_timestamp_HEHDT': sys_ts,
            'delta_ms_HEHDT': delta_ms,
            'heading_HEHDT': float(parts[1])    # degree
        }
    except:
        return None


def parse_psat(msg, sys_ts, delta_ms):
    try:
        parts = msg.split(',')
        return {
            'sys_timestamp_PSAT': sys_ts,
            'delta_ms_PSAT': delta_ms,
            'utc_time': parse_nmea_time(parts[2]), 
            'heading_PSAT': float(parts[3]),    # degree, same as HEHDT heading
            'pitch': float(parts[4]),           # degree
            'roll': float(parts[5])             # degree
        }
    except:
        return None


def parse_gprmc(msg, sys_ts, delta_ms):
    try:
        parts = msg.split(',')

        # NMEA time and date
        nmea_time = parse_nmea_time(parts[1]) if parts[1] else None
        nmea_date = datetime.strptime(parts[9], "%d%m%y").date() if parts[9] else None

        # geoposition
        lat_deg = float(parts[3][:2])
        lat_min = float(parts[3][2:])
        lat = lat_deg + lat_min / 60
        if parts[4] == 'S':
            lat *= -1

        lon_deg = float(parts[5][:3])
        lon_min = float(parts[5][3:])
        lon = lon_deg + lon_min / 60
        if parts[6] == 'W':
            lon *= -1

        # magnetic variation
        mag_var = float(parts[10]) if parts[10] else None
        mag_var_dir = parts[11] if len(parts) > 11 and parts[11] else None  # direction (E)ast or (W)est
        signed_mag_var = -mag_var if mag_var_dir == 'W' else mag_var

        # integrity mode
        integrity = parts[12].split('*')[0] if len(parts) > 12 else None

        return {
            'sys_timestamp_GPRMC': sys_ts,
            'delta_ms_GPRMC': delta_ms,
            'status': parts[2],
            'lat': lat,     # degree
            'lon': lon,     # degree
            'sog': float(parts[7]),     # knots
            'cog': float(parts[8]),     # degree
            'utc_datetime': datetime.combine(nmea_date, nmea_time),   # UTC
            'signed_mag_var': signed_mag_var,   # degree
            'integrity_mode': integrity
        }
    except Exception as e:
        return None


def parse_nmea(input_dir, output_file):
    """
    Reads all NMEA files in a directory,
    combines consecutive HEHDT, PSAT and GPRMC messages
    and saves the data as CSV.
    """

    print("Parsing dual GPS (NMEA) data...")

    data = []

    # dictionary for collecting current instances of 3 different messages
    default_entry = {
        "sys_timestamp_HEHDT": pd.NA,
        "delta_ms_HEHDT": pd.NA,
        "heading_HEHDT": pd.NA,
        "sys_timestamp_PSAT": pd.NA,
        "delta_ms_PSAT": pd.NA,
        "utc_time": pd.NA,
        "heading_PSAT": pd.NA,
        "pitch": pd.NA,
        "roll": pd.NA,
        "sys_timestamp_GPRMC": pd.NA,
        "delta_ms_GPRMC": pd.NA,
        "status": pd.NA,
        "lat": pd.NA,
        "lon": pd.NA,
        "sog": pd.NA,
        "cog": pd.NA,
        "utc_datetime": pd.NA,
        "signed_mag_var": pd.NA,
        "integrity_mode": pd.NA,
    }
    data_entry = default_entry.copy()

    # helping variables to get correct delta_ms for each message
    delta_ms_hehdt = 0
    delta_ms_psat = 0
    delta_ms_gprmc = 0

    # regex for single line, independent of message
    timestamp_re = re.compile(
        r"(?P<sys_ts>\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})\s+(?P<delta_ms>\d+)ms\s*(?P<msg>\$.*)?"
    )

    # iterate through directory
    for file in sorted(Path(input_dir).iterdir()):
        if file.is_file():
            with open(file, "r", encoding="utf-8") as f:

                # iterate through lines in file
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # check for timestamp in line
                    match = timestamp_re.match(line)
                    if not match:
                        continue
                    
                    # assign timestamp, delta_ms and message
                    sys_ts = datetime.strptime(match.group("sys_ts"), "%d.%m.%Y %H:%M:%S")
                    delta_ms = int(match.group("delta_ms"))
                    msg = match.group("msg")

                    # update delta_ms since last message
                    delta_ms_hehdt += delta_ms
                    delta_ms_psat += delta_ms
                    delta_ms_gprmc += delta_ms
                    
                    # check for message and append to data
                    if msg is None:
                        continue
                    
                    # 1st message: HEHDT
                    if msg.startswith("$HEHDT"):
                        rec = parse_hehdt(msg, sys_ts, delta_ms_hehdt)
                        if rec:
                            data_entry = rec    # begin new entry
                            delta_ms_hehdt = 0  # reset delta_ms

                    # 2nd message: PSAT
                    elif msg.startswith("$PSAT,HPR"):
                        rec = parse_psat(msg, sys_ts, delta_ms_psat)
                        if rec:
                            data_entry.update(rec)  # update current entry
                            delta_ms_psat = 0       # reset delta_ms

                    # 3rd and last message: GPRMC -> after this comes new $HEHDT with different timestamp
                    elif msg.startswith("$GPRMC"):
                        rec = parse_gprmc(msg, sys_ts, delta_ms_gprmc)
                        if rec:
                            data_entry.update(rec)      # update current entry
                            delta_ms_gprmc = 0          # reset delta_ms
                            data.append(data_entry)     # append current entry to data after each GPRMC parsing
                            data_entry = default_entry.copy()   # reset current entry to empty default
    
    if not data:
        raise ValueError("No NMEA data found.")
    
    # create output directory if not existing
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # save data as csv
    df = pd.DataFrame(data)
    df.to_csv(output_file, index=False)

    return df