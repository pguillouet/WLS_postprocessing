from parsers.wls_parser import parse_wls_rtd, parse_wls_sta
from parsers.nmea_parser import parse_nmea
from parsers.ahrs_parser import parse_ahrs_imu, parse_ahrs_gps
from processing.data_preparation import correct_utc, prepare_ahrs_gps, derive_velocities
from processing.WLS_postprocessing import WLS_postprocessing

from config import (
    RAW_WLS_DIR, WLS_RTD_FILE, WLS_STA_FILE, 
    RAW_NMEA_DIR, PARSED_NMEA_FILE, 
    RAW_AHRS_DIR, PARSED_AHRS_IMU_FILE, PARSED_AHRS_GPS_FILE,
    NMEA_MIN_TIMESTAMP_INTERVAL, NMEA_MAX_TIMESTAMP_INTERVAL, NMEA_FILE,
    AHRS_MIN_TIMESTAMP_INTERVAL, AHRS_MAX_TIMESTAMP_INTERVAL, AHRS_IMU_FILE,
    AHRS_GPS_FILE, PREPARED_DATA_DIR,
    VEL_X_Y_FILE, VEL_Z_FILE
)



# ============================================================
# PARSING
# ============================================================


parse_raw_data = False

if parse_raw_data:

    # WLS high-frequency data
    df_rtd = parse_wls_rtd(
        RAW_WLS_DIR,
        WLS_RTD_FILE
    )

    # WLS statistical data
    df_sta = parse_wls_sta(
        RAW_WLS_DIR,
        WLS_STA_FILE
    )

    # Dual GPS (NMEA) data
    df_nmea = parse_nmea(
        RAW_NMEA_DIR,
        PARSED_NMEA_FILE
    )

    # AHRS (IMU and GPS) data
    df_ahrs_imu = parse_ahrs_imu(
        RAW_AHRS_DIR,
        PARSED_AHRS_IMU_FILE
    )

    df_ahrs_gps = parse_ahrs_gps(
        RAW_AHRS_DIR,
        PARSED_AHRS_GPS_FILE
    )



# ============================================================
# DATA PREPARATION
# ============================================================


prepare_motion_data = False

if prepare_motion_data:

    # UTC correction in NMEA data
    df_nmea = correct_utc(
        df_input_file=PARSED_NMEA_FILE,
        utc_column="utc_datetime",
        reference_column="sys_timestamp_GPRMC",
        min_timestamp_seconds=NMEA_MIN_TIMESTAMP_INTERVAL,
        max_timestamp_seconds=NMEA_MAX_TIMESTAMP_INTERVAL,
        output_file=NMEA_FILE
    )

    # UTC correction in AHRS data
    df_ahrs_imu = correct_utc(
        df_input_file=PARSED_AHRS_IMU_FILE,
        utc_column="UTC_timestamp",
        reference_column="CPU_timestamp",
        min_timestamp_seconds=AHRS_MIN_TIMESTAMP_INTERVAL,
        max_timestamp_seconds=AHRS_MAX_TIMESTAMP_INTERVAL,
        output_file=AHRS_IMU_FILE
    )

    #  Prepare AHRS GPS data (Create UTC Timestamps and invert MSL height for delta z)
    df_ahrs_gps = prepare_ahrs_gps(
        gps_input_file=PARSED_AHRS_GPS_FILE,
        imu_input_file=AHRS_IMU_FILE,
        gps_output_file=AHRS_GPS_FILE,
        imu_utc_confirmed=True
    )

    # Derive ship velocities from GPS data
    df_vel_xy, df_vel_z = derive_velocities(
        nmea_input_file=NMEA_FILE,
        ahrs_gps_input_file=AHRS_GPS_FILE,
        output_dir=PREPARED_DATA_DIR,
        utc_confirmed=True
    )



# ============================================================
# WLS POST-PROCESSING
# ============================================================


# Create post-processing object
wls_pp = WLS_postprocessing()


# Statistical (STA) post-processing -> Correction of wind direction based on mean yaw angle

# Load WLS statistical data
wls_pp.load_WLS_sta_data(WLS_STA_FILE)

# Load motion data (STA processing only needs yaw data)
wls_pp.load_motion_data('dualGPS', NMEA_FILE, 'utc_datetime', yaw_column='heading_HEHDT')

# STA post-processing
wls_pp.correct_sta_wind_direction()


# High-frequency (RTD) post-processing -> full motion compensation

# Load WLS high-frequency (rtd) data
wls_pp.load_WLS_rtd_data(WLS_RTD_FILE)

# Load remaining motion data
wls_pp.load_motion_data('AHRS_IMU', AHRS_IMU_FILE, 'UTC_timestamp', roll_column='AHRS_Roll', pitch_column='AHRS_Pitch')
wls_pp.load_motion_data('dualGPS_derived_velxy', VEL_X_Y_FILE, 'UTC_timestamp', velx_column='Velocity X (m/s)', vely_column='Velocity Y (m/s)')
wls_pp.load_motion_data('AHRS_GPS_derived_velz', VEL_Z_FILE, 'UTC_timestamp', velz_column='Velocity Z (m/s)')
wls_pp.load_motion_data('AHRS_GPS', AHRS_GPS_FILE, 'UTC_timestamp', deltaz_column='llh_pos.msl_height_inverted')

# Synchronization of WLS RTD data with motion data, using the sum of squared residuals (SSR)
# This process takes a lot of time
# If synchronization is disabled, a constant default RTD timestamp shift is automatically set to 0.41 s
sync_data = False
if sync_data:
    wls_pp.sync_with_SSR()

# High-frequency (RTD) post-processing
rtd_processing = True
if rtd_processing:
    df_rtd_corrected = wls_pp.process_entire_rtd(create_sta_file=True)