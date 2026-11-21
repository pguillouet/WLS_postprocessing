
import pandas as pd
import numpy as np
from pathlib import Path
from processing.utils import interpolate_at
from config import EARTH_RADIUS


def correct_utc(
    df_input_file,
    utc_column,
    reference_column,
    min_timestamp_seconds,
    max_timestamp_seconds,
    output_file=None
):
    """
    Detects UTC timestamp anomalies based on irregular time intervals.
    Anomalous sections are corrected using reference timestamps and
    the UTC-reference offset measured immediately before each anomaly.
    """

    # Read data
    df = pd.read_csv(df_input_file)

    # Convert timestamps
    df[utc_column] = pd.to_datetime(
        df[utc_column], format="mixed"
    )
    df[reference_column] = pd.to_datetime(
        df[reference_column], format="mixed"
    )

    # Detect anomalous time intervals
    timestamp_delta = df[utc_column].diff()

    anomaly_mask = (
        (timestamp_delta > pd.Timedelta(seconds=max_timestamp_seconds))
        |
        (timestamp_delta < pd.Timedelta(seconds=min_timestamp_seconds))
    )

    # Identify anomaly boundaries
    anomaly_indices = df.index[anomaly_mask].tolist()

    # Pair consecutive anomaly boundaries
    anomaly_sections = []

    for start, end in zip(
        anomaly_indices[::2],
        anomaly_indices[1::2]
    ):
        anomaly_sections.append((start, end - 1))

    # Handle an anomaly extending to the end of the data
    if len(anomaly_indices) % 2 == 1:
        anomaly_sections.append(
            (anomaly_indices[-1], len(df) - 1)
        )

    # Correct detected anomaly sections
    for start, end in anomaly_sections:

        # Determine UTC-reference offset before the anomaly
        utc_reference_timedelta = (
            df.loc[start - 1, utc_column]
            - df.loc[start - 1, reference_column]
        )

        # Determine local UTC shift
        utc_shift = (
            df.loc[start, utc_column]
            - df.loc[start, reference_column]
            - utc_reference_timedelta
        )

        print(
            f"\nAnomaly from row {start} to row {end}:"
        )
        print(
            f"UTC timestamps are corrected locally with a shift of {-utc_shift}."
        )

        df.loc[start:end, utc_column] = (
            df.loc[start:end, reference_column]
            + utc_reference_timedelta
        )

    # Save corrected data
    if output_file is not None:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_file, index=False)
        print(f"UTC-corrected data saved to {output_file}")

    return df


def prepare_ahrs_gps(
    gps_input_file,
    imu_input_file,
    gps_output_file=None,
    imu_utc_confirmed=False
):
    """
    Creates UTC timestamps for AHRS GPS data by interpolating
    between the UTC timestamps of the AHRS IMU data.

    Also inverts the MSL height, because we need delta z defined downward

    The AHRS IMU UTC timestamps must already be corrected.
    """

    if not imu_utc_confirmed:
        raise ValueError(
            "AHRS IMU UTC timestamps must be confirmed as correct "
            "before interpolating GPS timestamps."
        )

    # Read AHRS GPS data
    df_AHRS_GPS = pd.read_csv(gps_input_file)

    # Read AHRS IMU data
    df_AHRS_IMU = pd.read_csv(imu_input_file)

    # Convert timestamps
    df_AHRS_GPS["AHRS_timestamp_COLLECTED"] = pd.to_datetime(
        df_AHRS_GPS["AHRS_timestamp_COLLECTED"],
        format="mixed"
    )

    df_AHRS_IMU["UTC_timestamp"] = pd.to_datetime(
        df_AHRS_IMU["UTC_timestamp"],
        format="mixed"
    )

    df_AHRS_IMU["AHRS_timestamp_COLLECTED"] = pd.to_datetime(
        df_AHRS_IMU["AHRS_timestamp_COLLECTED"],
        format="mixed"
    )

    # Interpolate UTC timestamps
    utc_times = [
        interpolate_at(
            timestamp,
            df_AHRS_IMU,
            "UTC_timestamp",
            "AHRS_timestamp_COLLECTED"
        )
        for timestamp in df_AHRS_GPS["AHRS_timestamp_COLLECTED"]
    ]

    # Add UTC timestamps to GPS data
    df_AHRS_GPS["UTC_timestamp"] = pd.to_datetime(utc_times)

    # Invert MSL height
    df_AHRS_GPS["llh_pos.msl_height_inverted"] = -df_AHRS_GPS["llh_pos.msl_height"]

    # Save corrected data if an output path was provided
    if gps_output_file is not None:
        gps_output_file = Path(gps_output_file)
        gps_output_file.parent.mkdir(parents=True, exist_ok=True)
        df_AHRS_GPS.to_csv(gps_output_file, index=False)
        print(f"AHRS GPS data with UTC timestamps saved to {gps_output_file}")

    return df_AHRS_GPS


def derive_velocities(
    nmea_input_file,
    ahrs_gps_input_file,
    output_dir=None,
    utc_confirmed=False,
    earth_radius=EARTH_RADIUS
):
    """
    Derives ship velocities from NMEA and AHRS GPS data.

    X: North -> South
    Y: East -> West
    Z: Up -> Down

    Velocity timestamps are placed at the midpoint between
    two consecutive GPS position measurements.

    Returns:
        df_vel_xy: DataFrame containing horizontal velocities.
        df_vel_z: DataFrame containing vertical velocity.
    """

    if not utc_confirmed:
        raise ValueError(
            "UTC timestamps in NMEA and AHRS-GPS data must be confirmed as correct "
            "before deriving velocities."
        )

    # Read NMEA GPS data
    df_NMEA = pd.read_csv(nmea_input_file)

    df_NMEA["utc_datetime"] = pd.to_datetime(
        df_NMEA["utc_datetime"],
        format="mixed"
    )

    # Read AHRS GPS data
    df_AHRS_GPS = pd.read_csv(ahrs_gps_input_file)

    df_AHRS_GPS["UTC_timestamp"] = pd.to_datetime(
        df_AHRS_GPS["UTC_timestamp"],
        format="mixed"
    )

    # Prepare NMEA data
    df_NMEA = df_NMEA.dropna(
        subset=["utc_datetime", "lat", "lon"]
    ).copy()

    df_NMEA["lat"] = pd.to_numeric(
        df_NMEA["lat"], errors="coerce"
    )
    df_NMEA["lon"] = pd.to_numeric(
        df_NMEA["lon"], errors="coerce"
    )

    df_NMEA = (
        df_NMEA.dropna(subset=["lat", "lon"])
        .sort_values("utc_datetime")
        .reset_index(drop=True)
    )

    # Calculate time differences
    dt_xy = df_NMEA["utc_datetime"].diff().dt.total_seconds()

    # Calculate coordinate differences
    delta_lat = df_NMEA["lat"].diff()
    delta_lon = df_NMEA["lon"].diff()

    # Calculate horizontal distances
    distance_x = -np.radians(delta_lat) * earth_radius
    distance_y = -np.radians(delta_lon) * earth_radius  #!!! This calculation is false -> must be corrected for latitude
    """
    # Correct longitude distance for latitude
    mean_lat = np.radians(
        (df_NMEA["lat"] + df_NMEA["lat"].shift()) / 2
    )

    distance_y = (
        -np.radians(delta_lon)
        * earth_radius
        * np.cos(mean_lat)
    )
    """
    # Calculate horizontal velocities
    vel_x = distance_x / dt_xy
    vel_y = distance_y / dt_xy

    # Calculate midpoint timestamps
    timestamp_vel_xy = (
        df_NMEA["utc_datetime"]
        - pd.to_timedelta(dt_xy / 2, unit="s")
    )

    # Create horizontal velocity DataFrame
    df_vel_xy = pd.DataFrame({
        "UTC_timestamp": timestamp_vel_xy,
        "Velocity X (m/s)": vel_x,
        "Velocity Y (m/s)": vel_y
    })

    df_vel_xy = (
        df_vel_xy.replace([np.inf, -np.inf], np.nan)
        .dropna()
        .reset_index(drop=True)
    )

    # Prepare AHRS GPS data
    df_AHRS_GPS = df_AHRS_GPS.dropna(
        subset=["UTC_timestamp", "llh_pos.msl_height"]
    ).copy()

    df_AHRS_GPS["llh_pos.msl_height"] = pd.to_numeric(
        df_AHRS_GPS["llh_pos.msl_height"],
        errors="coerce"
    )

    df_AHRS_GPS = (
        df_AHRS_GPS.dropna(subset=["llh_pos.msl_height"])
        .sort_values("UTC_timestamp")
        .reset_index(drop=True)
    )

    # Calculate time differences
    dt_z = df_AHRS_GPS["UTC_timestamp"].diff().dt.total_seconds()

    # Calculate vertical distance
    distance_z = -df_AHRS_GPS["llh_pos.msl_height"].diff()

    # Calculate vertical velocity
    vel_z = distance_z / dt_z

    # Calculate midpoint timestamps
    timestamp_vel_z = (
        df_AHRS_GPS["UTC_timestamp"]
        - pd.to_timedelta(dt_z / 2, unit="s")
    )

    # Create vertical velocity DataFrame
    df_vel_z = pd.DataFrame({
        "UTC_timestamp": timestamp_vel_z,
        "Velocity Z (m/s)": vel_z
    })

    df_vel_z = (
        df_vel_z.replace([np.inf, -np.inf], np.nan)
        .dropna()
        .reset_index(drop=True)
    )

    print(f"Number of horizontal velocity records: {len(df_vel_xy)}")
    print(f"Number of vertical velocity records: {len(df_vel_z)}")

    # Save results if output directory is provided
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        df_vel_xy.to_csv(
            output_dir / "vel_x_y_NMEA_derived.csv",
            index=False
        )

        df_vel_z.to_csv(
            output_dir / "vel_z_AHRS_GPS_derived.csv",
            index=False
        )

        print("Horizontal and vertical velocity data saved.")

    return df_vel_xy, df_vel_z