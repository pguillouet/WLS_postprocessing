import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

from config import GPS_LEAP_SECONDS


def convert_timestamp(series, timestamp_format):
    """Convert timestamp strings into datetime objects."""

    try:
        return pd.to_datetime(series, format=timestamp_format)
    except (ValueError, TypeError):
        return pd.to_datetime(series, format="mixed")


def convert_gps_to_utc(week, tow, leap_seconds=GPS_LEAP_SECONDS):
    """
    Convert GPS week and time-of-week into UTC timestamps.
    November 2021: 18 leap seconds since 1980
    """

    gps_seconds = week * 604800 + tow

    return (
        pd.Timestamp("1980-01-06T00:00:00")
        + pd.to_timedelta(gps_seconds - leap_seconds, unit="s")
    )


def parse_ahrs_imu(input_dir, output_file):
    """
    Reads all AHRS files in the directory,
    parses data and saves it as CSV file.
    """

    print("Parsing AHRS-IMU data...")

    data = []

    for file in sorted(Path(input_dir).iterdir()):

        if not file.is_file() or not file.name.endswith("AHRS.csv"):
            continue

        # read csv file
        df_file = pd.read_csv(file, sep=';')
        df_file.columns = df_file.columns.str.strip()

        # get rid of unnecessary columns (no useable data in here)
        df_file = df_file.drop([
            'AHRS_timestamp_UTC', 'EST_Roll', 'EST_Pitch', 'EST_Yaw', 'EST_Roll_ERR', 'EST_Pitch_ERR', 'EST_Yaw_ERR', 
            'EST_NED_X', 'EST_NED_Y', 'EST_NED_Z', 'EST_NED_X_ERR', 'EST_NED_Y_ERR', 'EST_NED_Z_ERR', 'Heading', 'Heading_ERR', 
            'rawGyroX', 'rawGyroY', 'rawGyroZ', 'EST_GyroBiasUNCERT_X', 'EST_GyroBiasUNCERT_Y', 'EST_GyroBiasUNCERT_Z', 
            'EST_GyroScaleFactorX', 'EST_GyroScaleFactorY', 'EST_GyroScaleFactorZ', 'EST_GyroScaleFactorUNCERT_X', 
            'EST_GyroScaleFactorUNCERT_Y', 'EST_GyroScaleFactorUNCERT_Z'
            ], axis=1)

        # CPU timestamp parsing
        file_date = datetime.strptime(file.name[:8], "%Y%m%d").date()    # extract the date from filename
        times = convert_timestamp(df_file["CPU_timestamp"], "%H:%M:%S.%f").dt.time
        df_file["CPU_timestamp"] = [datetime.combine(file_date, t) for t in times]

        # date adjustments for CPU timestamp
        if file.name[8:10] == "00":
            df_file.loc[df_file["CPU_timestamp"].dt.hour == 23, "CPU_timestamp"] -= timedelta(days=1)
        if file.name[8:10] == "23":
            df_file.loc[df_file["CPU_timestamp"].dt.hour == 00, "CPU_timestamp"] += timedelta(days=1)
        
        # AHRS timestamp transformation from string to datetime
        df_file["AHRS_timestamp_COLLECTED"] = convert_timestamp(df_file["AHRS_timestamp_COLLECTED"], "%Y-%m-%d %H:%M:%S.%f")
        
        # GPS Timestamp conversion to UTC (-> new column for UTC times)
        df_file["UTC_timestamp"] = convert_gps_to_utc(df_file["gps_timestamp.week_number"], df_file["gps_timestamp.tow"])

        # append data from current file
        data.append(df_file)

    if not data:
        raise ValueError("No AHRS data found.")

    # create output directory if not existing
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # concat data and save as csv
    df = pd.concat(data, ignore_index=True)
    df.to_csv(output_file, index=False)

    return df


def parse_ahrs_gps(input_dir, output_file):
    """
    Liest die GPS-Daten aus den IMU-Dateien ein
    und speichert sie als CSV.
    """

    print("Parsing AHRS-GPS data...")

    data = []

    for file in sorted(Path(input_dir).iterdir()):

        if not file.is_file() or not file.name.endswith("GPS.csv"):
            continue

        # define header because header in files is incorrect
        header = [
            "AHRS_timestamp_UTC", "AHRS_timestamp_COLLECTED", "utc_timestamp", "utc_time.valid_flags", "clock_info.bias", 
            "clock_info.drift", "clock_info.accuracy_estimate", "clock_info.valid_flags", "llh_pos.latitude", 
            "llh_pos.longitude", "llh_pos.ellipsoid_height", "llh_pos.msl_height", "llh_pos.horizontal_accuracy", 
            "llh_pos.vertical_accuracy", "llh_pos.valid_flags", "fix_info.fix_type", "fix_info.num_sv", "fix_info.fix_flags", 
            "fix_info.valid_flags", "gps_dop.gdop", "gps_dop.pdop", "gps_dop.hdop", "gps_dop.vdop", "gps_dop.tdop", 
            "gps_dop.ndop", "gps_dop.edop", "gps_dop.valid_flags"
        ]   # not sure for columns 3 and 4

        # read csv file
        df_file = pd.read_csv(file, sep=';', header=None, skiprows=1, names=header)
        df_file.columns = df_file.columns.str.strip()

        # get rid of unnecessary columns (no useable data in here)
        df_file = df_file.drop([
            'AHRS_timestamp_UTC', 'utc_timestamp', 'utc_time.valid_flags', 'clock_info.valid_flags', 'llh_pos.valid_flags', 
            'fix_info.fix_type', 'fix_info.fix_flags', 'fix_info.valid_flags', 'gps_dop.valid_flags'], axis=1)

        # AHRS timestamp transformation from string to datetime
        df_file["AHRS_timestamp_COLLECTED"] = convert_timestamp(df_file['AHRS_timestamp_COLLECTED'], "%Y-%m-%d %H:%M:%S.%f")

        # append data from current file
        data.append(df_file)

    if not data:
        raise ValueError("No AHRS-GPS data found.")

    # create output directory if not existing
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # concat data and save as csv
    df = pd.concat(data, ignore_index=True)
    df.to_csv(output_file, index=False)

    return df