from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent

DATA_DIR = PROJECT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PARSED_DATA_DIR = DATA_DIR / "parsed"
PREPARED_DATA_DIR = DATA_DIR / "prepared"
CORRECTED_DATA_DIR = DATA_DIR / "corrected"


# ============================================================
# RAW DATA PATHS
# ============================================================

RAW_WLS_DIR = RAW_DATA_DIR / "WLS7-261_2021_11"
RAW_NMEA_DIR = RAW_DATA_DIR / "DWD_NMEA_DATA_UFS4_202111"
RAW_AHRS_DIR = RAW_DATA_DIR / "data/raw/202111_AHRS"


# ============================================================
# PARSED DATA PATHS
# ============================================================

PARSED_NMEA_FILE = PARSED_DATA_DIR / "DWD_NMEA_DATA_UFS4_202111.csv"
PARSED_AHRS_IMU_FILE = PARSED_DATA_DIR / "202111_AHRS_imu.csv"
PARSED_AHRS_GPS_FILE = PARSED_DATA_DIR / "202111_AHRS_gps.csv"


# ============================================================
# INPUT FILES (all data prepared for WLS post-processing)
# ============================================================

# Parsed input data
WLS_RTD_FILE = PARSED_DATA_DIR / "WLS7-261_2021_11_rtd.csv"
WLS_STA_FILE = PARSED_DATA_DIR / "WLS7-261_2021_11_sta.csv"

# Prepared motion data
NMEA_FILE = PREPARED_DATA_DIR / "DWD_NMEA_DATA_UFS4_202111_utc_corrected.csv"
AHRS_IMU_FILE = PREPARED_DATA_DIR / "202111_AHRS_imu_utc_corrected.csv"
AHRS_GPS_FILE = PREPARED_DATA_DIR / "202111_AHRS_gps_with_utc.csv"
VEL_X_Y_FILE = PREPARED_DATA_DIR / "vel_x_y_NMEA_derived.csv"
VEL_Z_FILE = PREPARED_DATA_DIR / "vel_z_AHRS_GPS_derived.csv"


# ============================================================
# OUTPUT DIRECTORIES
# ============================================================

RTD_CORRECTED_DIR = CORRECTED_DATA_DIR / "RTD"
STATISTICS_CORRECTED_DIR = CORRECTED_DATA_DIR / "STA"


# ============================================================
# WLS PARAMETERS
# ============================================================

# Available nominal measurement altitudes [m]
WLS_ALTITUDES = [
    46, 66, 76, 86, 97, 114,
    134, 154, 174, 194, 244, 274
]

# CNR threshold [dB]
CNR_THRESHOLD = -23

# Beam inclination angle [deg]
WLS_BEAM_ANGLE = 28

# Time between LOS measurement and interpolation time [s]
WLS_MEASUREMENT_TIME_OFFSET = 0.333

# Default synchronization shift [s]
WLS_DEFAULT_SYNC_SHIFT = 0.41


# ============================================================
# RTD CORRECTION PARAMETERS
# ============================================================

# Maximum distance to nearest valid altitude measurement [m]
RTD_MAX_ALTITUDE_DISTANCE = 10

# Altitudes used for synchronization optimization [m]
RTD_SYNC_ALTITUDES = [
    76, 86, 97, 114, 134, 154
]

# Altitude used as optimization target for SSR
RTD_SYNC_TARGET_ALTITUDE = 97

# Synchronization optimization parameters
RTD_SYNC_INITIAL_SHIFTS = [-1, 0, 1]
RTD_SYNC_TOLERANCE = 0.01
RTD_SYNC_MAX_ITERATIONS = 10

# Maximum fraction of missing SSR values
RTD_SYNC_MAX_NAN_FRACTION = 0.8

# Synchronization output file
RTD_SYNC_FILE = CORRECTED_DATA_DIR / "rtd_sync_shift.csv"


# ============================================================
# UTC CORRECTION PARAMETERS
# ============================================================

# NMEA expected timestamp interval [s]
NMEA_MIN_TIMESTAMP_INTERVAL = 0.9
NMEA_MAX_TIMESTAMP_INTERVAL = 1.1

# AHRS expected timestamp interval [s]
AHRS_MIN_TIMESTAMP_INTERVAL = 0.05
AHRS_MAX_TIMESTAMP_INTERVAL = 0.3

# GPS leap seconds
GPS_LEAP_SECONDS = 18


# ============================================================
# PROCESSING PARAMETERS
# ============================================================

# Earth radius [m]
EARTH_RADIUS = 6_371_000

# Default interpolation method
INTERPOLATION_METHOD = "linear"