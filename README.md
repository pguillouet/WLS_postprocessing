# Wind Lidar Motion Correction

## Overview

This project provides a Python-based processing pipeline for parsing, synchronizing, and correcting floating Wind Lidar (WLS) measurements using vessel motion data. The code implements the post-processing techniques described in https://doi.org/10.5194/egusphere-2026-6846 (Preprint).

The primary objective is to compensate for the influence of vessel motion on Wind Lidar measurements.

Two main processing algorithms are implemented:

- Full motion compensation of Lidar high-frequency (RTD) data
- Simple correction of the measured wind direction in the Lidar statistical (STA) data

The project processes three main types of input data:

- **Wind Lidar data:** Realtime (RTD) and statistical (STA) measurements.
- **Dual GPS/NMEA data:** Position, navigation, and heading information.
- **AHRS-IMU/AHRS-GPS data:** Vessel attitude and motion measurements, including roll, pitch, and vertical position.

The processing pipeline consists of independent modules for data parsing, preparation, correction, and output generation.

## Project Structure

```text
wind_lidar_correction/
│
├── main.py
├── config.py
│
├── parsers/
│   ├── __init__.py
│   ├── ahrs_parser.py
│   ├── nmea_parser.py
│   └── wls_parser.py
│
├── processing/
│   ├── __init__.py
│   ├── data_preparation.py
│   ├── utils.py
│   └── WLS_postprocessing.py
│
├── data/
│   ├── raw/
│   ├── parsed/
│   ├── prepared/
│   └── corrected/
│
├── README.md
└── requirements.txt
```

### Main components

| Module | Description |
|---|---|
| `main.py` | Main entry point; controls the processing workflow. |
| `config.py` | Central configuration of file paths, measurement altitudes, thresholds, and processing parameters. |
| `parsers/` | Parses the original WLS, GPS/NMEA, and AHRS/IMU data files. |
| `processing/` | Contains shared functions, data preparation routines and the correction algorithms for the Lidar data. |
| `data/raw/` | Original measurement files. |
| `data/parsed/` | Parsed measurement data stored as CSV files. |
| `data/prepared/` | Preprocessed motion data, with corrected timestamps and a fitting format for Lidar motion compensation. |
| `data/corrected/` | Corrected Lidar measurement data. |

## Requirements

The project uses Python and the following main packages:

- pandas
- NumPy
- SciPy

Additional dependencies may be required by the individual parsers.

Install the dependencies using:

```bash
pip install -r requirements.txt
```

## Input Data

The processing pipeline requires the following data sources.

### Wind Lidar data

The Wind Lidar provides two types of measurements:

- **RTD (Realtime Data):** Individual line-of-sight measurements and derived wind vectors.
- **STA (Statistical Data):** Wind statistics calculated by the Wind Lidar over predefined measurement intervals.

The measurements are available at several nominal altitudes:

```python
WLS_ALTITUDES = [
    46, 66, 76, 86, 97, 114,
    134, 154, 174, 194, 244, 274
]
```

The coordinate system is defined as follows:

| Axis | Positive direction |
|---|---|
| x | North to South |
| y | East to West |
| z | Up to Down |

Euler angles are defined as right-handed rotations around the respective axes.

### Dual GPS/NMEA data

The NMEA data provides navigation information, including horizontal position and vessel heading.

The heading information can be used to correct wind directions measured relative to the vessel.

### AHRS-IMU/AHRS-GPS data

The AHRS data is split into IMU output files and internal GPS output files.

They provides further information about the vessel's motion:

- Roll and pitch angles (AHRS-IMU)
- Vertical position (AHRS-GPS)

## Processing Workflow

The processing pipeline is divided into several independent steps.

### 1. Data Parsing

The original measurement files are parsed and converted into CSV files.

The individual parser modules are responsible for:

- Reading the original data formats.
- Extracting relevant measurement parameters.
- Converting timestamps into a consistent representation.
- Saving the parsed data for subsequent processing.

The parsed files are stored in `data/parsed/`.

### 2. Data Preparation

The following steps must first be applied before the Lidar data can be corrected.

As the parsed data contains partially inconsistent timestamps, several functions are provided to account for synchronized time indications between the motion datasets.

Within `data_preparation.py`, the function `correct_utc()` detects anomalies in UTC timestamps and corrects the respective intervals, based on a comparison with CPU timestamps.

`prepare_ahrs_gps()` creates new UTC timestamps for the AHRS-GPS files, based on a comparison with the IMU files. Additionally, it inverts the measured MSL height in order to match the coordinate definitions within this project.

`derive_velocities()` calculates horizontal and vertical vessel velocities from GPS data.

The resulting preprocessed data is stored in `data/prepared` and used by the subsequent processing steps.

### 3. Loading Lidar and Motion Data

All Lidar post-processing steps are implemented within the class `WLS_postprocessing`.

Lidar data is loaded using `load_WLS_rtd_data()` and `load_WLS_sta_data()`.

Motion data is loaded using `load_motion_data()`. Only the specified columns are loaded to reduce memory consumption.

The motion channels are registered using a channel mapping that associates each channel with its corresponding dataset and column.

For example:

```python
self.motion_channels["yaw"] = {
    "dataset": dataset_name,
    "column": yaw_column
}
```

This allows different motion channels to originate from different measurement systems or files.

### 4. Realtime Data Correction (RTD)

The realtime correction compensates for the influence of vessel motion on the Wind Lidar measurements.

Using `process_entire_rtd()` performs motion compensation on the entire parsed RTD data.

The corrected data is saved in `data/corrected/RTD`.

The correction includes the following components:

#### Attitude correction

Roll, pitch, and yaw are used to transform the nominal Wind Lidar beam direction into the earth-fixed coordinate system.

The resulting line-of-sight unit vector is used for the subsequent wind vector reconstruction.

#### Translational velocity correction

The vessel's translational velocity is projected onto the corrected line-of-sight direction.

The resulting velocity component is added to the measured radial velocity to compensate for the vessel's translational motion.

#### Altitude correction

The actual measurement altitude is corrected using the transformed beam geometry.

If available, the vertical vessel displacement (`delta z`) is also considered.

The corrected radial velocities are interpolated to the nominal Wind Lidar measurement altitudes.

#### Wind vector reconstruction

Wind vectors are reconstructed from the corrected radial velocities using a least-squares approach.

The pseudoinverse of the measurement matrix is used to determine the three-dimensional wind vector.

The following parameters are calculated for each altitude:

- x-, y-, and z-components of the wind vector
- Horizontal wind speed
- Wind direction
- Sum of squared residuals (SSR)
- CNR
- Raw radial velocity
- Corrected radial velocity

The corrected RTD data is stored as CSV files in the configured output directory.

#### Synchronization optimization

An additional synchronization procedure `sync_with_SSR()` can be used to optimize the time offset between the Wind Lidar and the motion measurements.

The synchronization offset is determined by minimizing the mean SSR at a predefined target altitude.

The optimization uses selected altitudes and a parabolic approximation to determine the optimal time shift.

The resulting synchronization offsets are stored for subsequent processing.

This process is really time consuming, as it involves an iterative RTD motion compensation procedure.

If the synchronization is not applied, the RTD correction will assume a fixed timestamp offset of +0.41 s. This value was found as the mean synchronization offset of RTD timestamps in previous investigations.

### 5. Statistical Data Generation from Corrected RTD Data

Statistical data can be generated directly from the corrected RTD measurements.

The method `create_sta_from_rtd()` calculates statistics over consecutive 10-minute intervals.

For each altitude, the following parameters are calculated:

| Parameter | Description |
|---|---|
| Wind Speed | Mean horizontal wind speed |
| Wind Speed Dispersion | Standard deviation of wind speed |
| Wind Speed min | Minimum wind speed |
| Wind Speed max | Maximum wind speed |
| Wind Direction | Circular mean wind direction |
| Z-wind | Mean vertical wind component |
| Z-wind Dispersion | Standard deviation of the vertical wind component |
| Data Availability | Percentage of valid wind speed measurements |

Wind direction is averaged using a circular mean to account for the angular nature of the data.

The generated statistical data is saved in the same folder as the underlying RTD results.

### 6. Statistical Wind Direction Correction

Existing Wind Lidar statistical data can also be corrected using the vessel's heading.

The method `correct_sta_wind_direction()` uses the previously loaded yaw channel.

For each 10-minute WLS measurement interval, the circular mean vessel heading is calculated over the corresponding interval.

The wind direction is then corrected according to:

\[
WD_{\mathrm{corrected}} =
(WD_{\mathrm{WLS}} + \overline{\mathrm{Heading}}) \bmod 360
\]

The corrected data is saved in `data/corrected/STA`.

## Configuration

All relevant processing parameters and file paths are defined centrally in `config.py`.

File paths are constructed using `pathlib.Path` relative to the project directory.

This allows the project to be moved without manually changing absolute paths throughout the code.

## Output Structure

Corrected data is stored in timestamped output directories.

A typical output structure looks like this:

```text
data/
└── corrected/
    └── RTD/
    │   ├── rtd_corrected_YYYY-MM-DD_HH-MM-SS
    │   │   ├── sta_from_rtd
    │   │   │   └── sta_from_rtd.csv
    │   │   │
    │   │   ├── YYYY-MM-DD.csv
    │   │   └── ...
    │   │
    └── STA/
        ├── sta_corrected_YYYY-MM-DD_HH-MM-SS.csv
        └── ...
```

The two types of statistical data have different origins:

- `sta_corrected_...csv`: Existing WLS statistical data corrected using vessel heading. Stored seperately from RTD data.
- `sta_from_rtd_...csv`: Newly generated statistical data calculated from corrected RTD measurements. Stored in the respective RTD directory.

Synchronization results are stored separately as defined in `config.py`.

## Running the Project

The processing workflow is controlled through `main.py`.

A typical processing sequence is:

1. Parse the original measurement files.
2. Correct UTC timestamps.
3. Prepare AHRS-GPS data (only necessary for RTD correction).
4. Derive translational velocities (only necessary for RTD correction).
5. Load the required motion data channels.
6. Optionally find optimized synchronization time shift.
7. Process and correct the RTD measurements (and optionally generate new statistical data).
8. Process STA data directly using vessel heading.

Run the project from the project root directory:

```bash
python main.py
```

Individual processing steps should be configurable so that they can be executed independently when required.

## Notes and Assumptions

- All measurement timestamps must refer to a consistent time basis before interpolation and correction.
- Motion data must be sorted chronologically.
- Yaw and wind direction are represented in degrees.
- Roll and pitch are represented in radians.
- Angular quantities must be interpolated and averaged using circular methods.
- Missing or invalid measurements should be handled explicitly.
- The correction algorithms assume that the coordinate definitions and sign conventions described above are applied consistently across all input datasets.
- The original parsed measurement files should remain unchanged.
- Corrected data is stored separately to preserve traceability and reproducibility.

## Future Improvements

Potential extensions include:

- Automated quality control of motion and Wind Lidar measurements.
- Improved handling of missing motion data.
- Logging of processing parameters and correction settings.
- Automated comparison between original WLS statistics and statistics generated from corrected RTD data.
