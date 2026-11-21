import pandas as pd
import numpy as np
from scipy.interpolate import interp1d

from processing.utils import interpolate_at, circular_mean_degree
from config import (CORRECTED_DATA_DIR, WLS_ALTITUDES, WLS_DEFAULT_SYNC_SHIFT, 
    CNR_THRESHOLD, WLS_BEAM_ANGLE, WLS_MEASUREMENT_TIME_OFFSET, INTERPOLATION_METHOD, RTD_MAX_ALTITUDE_DISTANCE, 
    RTD_SYNC_ALTITUDES, RTD_SYNC_TARGET_ALTITUDE, RTD_SYNC_INITIAL_SHIFTS, RTD_SYNC_TOLERANCE, 
    RTD_SYNC_MAX_ITERATIONS, RTD_SYNC_MAX_NAN_FRACTION, RTD_SYNC_FILE)


class WLS_postprocessing:

    def __init__(
        self, 
        output_dir: str = None
    ):
        """
        Creates WLS_postprocessing object.
        If no specific output directory is defined, the corrected data is saved in "data/corrected"
        """

        if output_dir is None:
            output_dir = CORRECTED_DATA_DIR

        self.df_WLS_rtd = pd.DataFrame()
        self.df_WLS_sta = pd.DataFrame()
        self.motion_datasets = {}
        self.motion_channels = {}
        self.altitudes = WLS_ALTITUDES
        self.output_dir = output_dir


    def load_WLS_rtd_data(
        self, 
        input_file: str
    ):
        """ Loads WLS high-frequency data from csv file """

        print("Loading WLS RTD data...")

        # read csv file
        self.df_WLS_rtd = pd.read_csv(input_file)

        # transformation str -> pd.datetime
        self.df_WLS_rtd['Timestamp'] = pd.to_datetime(self.df_WLS_rtd['Timestamp'], format="mixed", errors="coerce")

        if not self.df_WLS_rtd.empty:
            print("WLS RTD data loaded")
        else:
            print("Warning: WLS RTD data is empty")

        # set initial constant timestamp shift for synchronization with motion data
        self.df_WLS_rtd['sync_shift_seconds'] = WLS_DEFAULT_SYNC_SHIFT


    def load_WLS_sta_data(
        self, 
        input_file: str
    ):
        """
        Loads WLS statistics data from csv file.
        """

        print("Loading WLS statistics data...")

        self.df_WLS_sta = pd.read_csv(
            input_file,
            parse_dates=["Timestamp (end of interval)"],
            index_col="Timestamp (end of interval)"
        )

        self.df_WLS_sta.sort_index(inplace=True)

        if not self.df_WLS_sta.empty:
            print("WLS RTD data loaded")
        else:
            print("Warning: WLS RTD data is empty")


    def load_motion_data(
        self, 
        dataset_name: str, 
        filename: str, 
        timestamp_column: str, 
        roll_column: str = None, 
        pitch_column: str = None, 
        yaw_column: str = None, 
        velx_column: str = None, 
        vely_column: str = None, 
        velz_column: str = None, 
        deltaz_column: str = None
    ):
        """ 
        Loads a new csv file containing motion data. 
        Only the specified columns are loaded.

        Currently, the following units are expected: 
        roll, pitch: (rad); 
        yaw: (degree); 
        vel x, y, z: (m/s); 
        delta z: (m) 

        Coordinate definitions: 
        x: N -> S 
        y: E -> W 
        z: U -> D  ->  also applies to delta z (positive delta z means height reduction!)
        Euler angles defined as right-handed rotations around these axes
        Use the method invert_motion_data() to invert the sign of a motion channel to match these definitions
        """

        print("Loading motion data...")

        # Collect only required columns (for using less RAM)
        columns = [
            timestamp_column,
            roll_column,
            pitch_column,
            yaw_column,
            velx_column,
            vely_column,
            velz_column,
            deltaz_column
        ]

        # Remove None values and duplicate column names
        columns = list(dict.fromkeys(col for col in columns if col is not None))

        # Read only required columns
        df_new_motion_data = pd.read_csv(
            filename,
            usecols=columns
        )

        # Transform str -> pd.datetime
        df_new_motion_data[timestamp_column] = pd.to_datetime(
            df_new_motion_data[timestamp_column],
            format="mixed",
            errors="coerce"
        )

        # Set timestamp column as index and sort
        df_new_motion_data = (
            df_new_motion_data
            .set_index(timestamp_column)
            .sort_index()
        )

        if not df_new_motion_data.empty:
            print(f"Motion data '{dataset_name}' loaded")
        else:
            print(f"Warning: Motion data '{dataset_name}' is empty")

        # Save dataset and assign the specified motion-data channels
        self.motion_datasets[dataset_name] = df_new_motion_data

        if roll_column:
            self.motion_channels["roll"] = {
                "dataset": dataset_name,
                "column": roll_column
            }
            print("roll data defined")

        if pitch_column:
            self.motion_channels["pitch"] = {
                "dataset": dataset_name,
                "column": pitch_column
            }
            print("pitch data defined")

        if yaw_column:
            self.motion_channels["yaw"] = {
                "dataset": dataset_name,
                "column": yaw_column
            }
            print("yaw data defined")

        if velx_column:
            self.motion_channels["velx"] = {
                "dataset": dataset_name,
                "column": velx_column
            }
            print("velx data defined")

        if vely_column:
            self.motion_channels["vely"] = {
                "dataset": dataset_name,
                "column": vely_column
            }
            print("vely data defined")

        if velz_column:
            self.motion_channels["velz"] = {
                "dataset": dataset_name,
                "column": velz_column
            }
            print("velz data defined")

        if deltaz_column:
            self.motion_channels["deltaz"] = {
                "dataset": dataset_name,
                "column": deltaz_column
            }
            print("deltaz data defined")


    def _get_motion_channel(
        self, 
        channel: str, 
        timestamp: pd.Timestamp
    ):
        """ 
        Gets the instantanious, interpolated motion value from a defined motion channel at a given timestamp.
        Channels: "roll", "pitch", "yaw", "velx", "vely", "velz", "deltaz".
        Channel has first to be defined using load_motion_data(...) 
        """

        # search for channel
        try:
            cfg = self.motion_channels[channel]
        except KeyError:
            raise RuntimeError(f"The motion channel {channel} was not defined.")
        
        # return interpolated motion value
        circular = False
        if channel=="yaw":
            circular = True
        return interpolate_at(timestamp, self.motion_datasets[cfg["dataset"]], cfg["column"], circular=circular)


    def _get_true_unit_vec(
        self, 
        beam_pos, 
        roll, 
        pitch, 
        yaw
    ):
        """ 
        Returns the unit vector of a line of sight (LOS) measurement in the Earth-fixed frame based on Euler angles.
        also returns actual theta and phi angles in radians 
        ! Euler angles are expected in radians and as right-handed rotations !
        ! beam position is 0, 90, 180, 270 (int) or 'V' (char) !
        """

        # define unit vector in LIDAR frame
        if beam_pos=='V':
            n_lidar = np.array([0, 0, -1])
        else:
            theta = np.radians(float(beam_pos))
            phi = np.radians(WLS_BEAM_ANGLE)
            n_lidar = np.array([-np.cos(theta)*np.sin(phi), -np.sin(theta)*np.sin(phi), -np.cos(phi)])

        # rotation matrix
        rot_matrix = np.array([[np.cos(yaw)*np.cos(pitch), np.cos(yaw)*np.sin(pitch)*np.sin(roll)-np.sin(yaw)*np.cos(roll), np.cos(yaw)*np.sin(pitch)*np.cos(roll)+np.sin(yaw)*np.sin(roll)],
                    [np.sin(yaw)*np.cos(pitch), np.sin(yaw)*np.sin(pitch)*np.sin(roll)+np.cos(yaw)*np.cos(roll), np.sin(yaw)*np.sin(pitch)*np.cos(roll)-np.cos(yaw)*np.sin(roll)],
                    [-np.sin(pitch), np.cos(pitch)*np.sin(roll), np.cos(pitch)*np.cos(roll)]])
        
        # transform unit vector from rotated LIDAR frame to fixed frame
        n_fix = rot_matrix @ n_lidar

        # calculate actual theta and phi in Earth-fixed frame
        theta_fix = (np.pi + np.atan2(n_fix[1], n_fix[0])) % (2*np.pi)
        phi_fix = np.acos(-n_fix[2])

        return n_fix, theta_fix, phi_fix


    def _get_v_r_transl_addend(
        self, 
        v_mov_vec, 
        n_vec
    ):
        """ function for determining the correction addend that has to be added to the measured LOS velocity 
        ! vectors are expected in Earth-fixed reference frame !"""

        v_r_correction = v_mov_vec @ (-n_vec)
        return v_r_correction


    def _process_rtd_section(
        self, 
        t_start: pd.Timestamp, 
        t_end: pd.Timestamp, 
        altitudes: list=None, 
        translation_cor: bool=True, 
        altitude_cor: bool=True, 
        three_los_per_windvec: bool=False
    ):
        """ 
        Core part of high-frequency post-processing: 
        The WLS rtd data stored in self.df_WLS_rtd is processed from t_start to t_end.
        This function does not save the processed data in a file; use process_entire_rtd(...) instead.
        
        Default: 5 successive radial wind speeds (Vr) are modified and recombined 
        based on motion data to calculate wind vectors with least-squares solution.
        
        Options:
        altitudes -> Define selection of nominal altitudes to be post-processed (selection must be included in raw data as well).
        translation_cor -> Choose wether Vr should be corrected for doppler shift distortion due to translational LIDAR motion.
        altitude_cor -> Choose wether Vr should be interpolated to nominal heights (including platform heave, if delta z is defined).
        three_los_per_windvec -> If enabled, only latest 3 Vr are considered for wind vector reconstruction, leading to a 3x3 LES 
        (!not recommended, more prone to measurement errors!).
        """

        # check altitudes
        if altitudes is None:
            altitudes = self.altitudes
        if not all(a in self.altitudes for a in altitudes):
            raise ValueError("Altitudes to post-process don't correspond to the raw WLS heights.")
        
        # check for relevant motion data
        if translation_cor and not all(key in self.motion_channels for key in ('velx', 'vely', 'velz')):
            translation_cor = False
            print("Warning: Translational motion correction was turned off due to missing velocity data.")
        if altitude_cor:
            if len(altitudes) < 2:
                altitude_cor = False
                print("Warning: Altitude interpolation was turned off. Include at least 2 altitudes to enable.")
        delta_z_defined = False
        if 'deltaz' in self.motion_channels:
            delta_z_defined = True

        # define the number of LOS for wind vector reconstruction
        los_per_windvec = 5
        if three_los_per_windvec:
            los_per_windvec = 3

        # define section of WLS data to be corrected, including 4 LOS before t_start
        start_idx = self.df_WLS_rtd['Timestamp'].searchsorted(t_start)
        start_idx_with_history = max(0, start_idx - (los_per_windvec-1))  # makes sure that index doesn't get below 0
        end_idx = self.df_WLS_rtd['Timestamp'].searchsorted(t_end)
        df_WLS_rtd_section = self.df_WLS_rtd.iloc[start_idx_with_history:end_idx].reset_index()

        # print updates if post-processing could take longer...
        print_update = False
        if len(df_WLS_rtd_section) > 5000:
            print_update = True

        # ----- rtd data iteration loop -----
        v_r_history = np.full((los_per_windvec-1, len(altitudes)), np.nan)  # matrix for temporarily storing preceding Vr on each altitude
        n_history = np.full((los_per_windvec-1, 3), np.nan) # matrix for temporarily storing preceding unit vectors
        results = []    # corrected measurements are collected here
        for index_los, los_measurement in df_WLS_rtd_section.iterrows():    # each row is one LOS measurement
            # original rtd timestamp of current LOS
            los_timestamp = los_measurement['Timestamp']

            # print update
            if print_update and index_los % 1000 == 0:
                print(f"Processing LOS at {los_timestamp} ({index_los+1}/{len(df_WLS_rtd_section)}, {100*index_los/len(df_WLS_rtd_section):.2f}% finished)")

            # subtract half of LOS duration to get timestamp for interpolations
            t_interpolation = los_timestamp - pd.Timedelta(seconds=WLS_MEASUREMENT_TIME_OFFSET) # assumes LOS signal accumulation time of 0.666 s
            # add synchronization time shift to align WLS with motion data
            t_interpolation += pd.Timedelta(seconds=los_measurement['sync_shift_seconds'])
            
            # extract euler angles from motion data
            roll = self._get_motion_channel('roll', t_interpolation)
            pitch = self._get_motion_channel('pitch', t_interpolation)
            yaw = np.deg2rad(self._get_motion_channel('yaw', t_interpolation))  #! Umrechnung sollte vllt beim Laden schon passieren?

            # get the true unit vector n of LOS in Earth-fixed frame
            n, theta, phi = self._get_true_unit_vec(los_measurement['Position'], roll, pitch, yaw)   # LOS unit vector in Earth-fixed frame, theta and phi of LOS in radians
            
            # define matrix A from latest unit vectors (A is the same for each measurement altitude)
            A = -np.vstack([n, n_history])

            # create LOS DataFrame sorted by altitudes, containing raw Vr and CNR
            df_los = []
            for alt in altitudes:
                df_los.append({
                        "nominal_altitude": alt,
                        "v_r_raw": los_measurement[f'{alt}m Radial Wind Speed (m/s)'],
                        "cnr": los_measurement[f"{alt}m CNR (dB)"]
                    })
            df_los = pd.DataFrame(df_los)   # so far, df_los only contains raw data

            # apply CNR filter
            df_los["v_r_valid"] = df_los["v_r_raw"]
            df_los.loc[df_los["cnr"] < CNR_THRESHOLD, "v_r_valid"] = np.nan

            # ----- Vr modifications -----
            df_los["v_r"] = df_los.v_r_valid    # the column "v_r" is used later for solving the LES

            # translational correction
            if translation_cor:
                # extract translational velocities from motion data
                vel_x = self._get_motion_channel('velx', t_interpolation)
                vel_y = self._get_motion_channel('vely', t_interpolation)
                vel_z = self._get_motion_channel('velz', t_interpolation)

                # get translational correction term and add it to Vr
                v_r_transl_addend = self._get_v_r_transl_addend(np.array([vel_x, vel_y, vel_z]), n)
                df_los["v_r"] += v_r_transl_addend

            # altitude correction (Vr interpolation to nominal heights)
            if altitude_cor:
                # calculate actual measurement altitudes
                if los_measurement['Position'] == 'V':
                    df_los["real_altitude"] = df_los.nominal_altitude * np.cos(phi) # if current LOS is vertical
                else:
                    df_los["real_altitude"] = (df_los.nominal_altitude / np.cos(np.radians(WLS_BEAM_ANGLE))) * np.cos(phi)  # skew LOS
                # include platform heave if delta z is defined
                if delta_z_defined:
                    delta_z = self._get_motion_channel('deltaz', t_interpolation)
                    df_los["real_altitude"] -= delta_z  # minus because of coordinate definitions

                # interpolate Vr to nominal altitudes
                df_los_valid = df_los.dropna(subset=["v_r_valid"])   # excludes CNR-filtered nan values
                if len(df_los_valid) < 2:
                    # less than two valid points -> no interpolation possible
                    df_los["v_r"] = np.full(len(df_los), np.nan)
                else:
                    x = df_los.nominal_altitude.to_numpy()  # x points to interpolate at
                    xp = df_los_valid.real_altitude.to_numpy()  # valid data x
                    fp = df_los_valid.v_r.to_numpy()            # valid data y
                    f = interp1d(xp, fp, kind=INTERPOLATION_METHOD, fill_value="extrapolate")
                    y = f(x)

                    # interpolation criteria: max. allowed distance to nearest valid Vr
                    max_distance = RTD_MAX_ALTITUDE_DISTANCE    # meter
                    idx = np.searchsorted(xp, x)
                    dist_left = np.where(idx > 0, x - xp[idx - 1], np.inf)
                    dist_right = np.where(idx < len(xp), xp[np.minimum(idx, len(xp) - 1)] - x, np.inf)
                    dist = np.minimum(dist_left, dist_right)    # distance to nearest point
                    y[dist > max_distance] = np.nan     # filter cases where nearest valid Vr is more than 10m away
                    df_los["v_r"] = y

            # ----- linear equation system (LES) -----
            # each altitude has a different b vector of the LES, each consisting of the latest five Vr
            # here, the b vectors of all 12 altitudes are stacked into a matrix B (12 x 5) for quicker calculations
            # each row of B contains the b vector of one measurement altitude
            B = np.column_stack((df_los.v_r.to_numpy(), v_r_history.T))

            # solve overdetermined linear equation system A * wind_vec = b for each altitude
            if np.isnan(A).any():   # fallback if matrix A could not be defined (e.g. the first 4 steps)
                wind_vectors = np.full((len(df_los), 3), np.nan)
                ssr = np.full(len(df_los), np.nan)
            else:
                # pseudo inverse of matrix A (for quickly solving LES for all 12 altitudes)
                A_pinv = np.linalg.pinv(A)
                # solving LES with pseudo inverse
                wind_vectors = (A_pinv @ B.T).T # all 12 wind vectors are now stacked in 'wind_vectors'
                # calculate residuals of overdetermined LES
                residual_matrix = B.T - A @ wind_vectors.T
                ssr = np.sum(residual_matrix**2, axis=0)  # sum of squared residuals (SSR) for all altitudes stacked

            # save wind vector components into df_los
            df_los["u"] = wind_vectors[:, 0]
            df_los["v"] = wind_vectors[:, 1]
            df_los["w"] = wind_vectors[:, 2]

            # save residuals
            df_los["ssr"] = ssr

            # derive wind speed and direction
            df_los["wind_speed"] = np.hypot(df_los["u"], df_los["v"])
            df_los["wind_direction"] = (180 + np.degrees(np.arctan2(-df_los["v"], -df_los["u"])))

            # create new results row for output DataFrame
            results_row_dict = {
                "Timestamp": los_timestamp,
                "Sync Shift (s)": los_measurement["sync_shift_seconds"],
                "LOS Position": los_measurement["Position"],
                "LOS True Theta (deg)": np.degrees(theta),
                "LOS True Phi (deg)": np.degrees(phi),
            }
            if translation_cor:
                results_row_dict.update({
                    "LIDAR X-velocity (m/s)": vel_x,
                    "LIDAR Y-velocity (m/s)": vel_y,
                    "LIDAR Z-velocity (m/s)": vel_z,
                })
            if delta_z_defined:
                results_row_dict.update({
                    "LIDAR Z-position Offset (m)": delta_z,
                })
            for i, alt in enumerate(altitudes):
                results_row_dict.update({
                    f"{alt}m X-wind (m/s)": df_los.at[i, "u"],
                    f"{alt}m Y-wind (m/s)": df_los.at[i, "v"],
                    f"{alt}m Z-wind (m/s)": df_los.at[i, "w"],
                    f"{alt}m Wind Speed (m/s)": df_los.at[i, "wind_speed"],
                    f"{alt}m Wind Direction (°)": df_los.at[i, "wind_direction"],
                    f"{alt}m SSR (m^2/s^2)": df_los.at[i, "ssr"],
                    f"{alt}m CNR (dB)": df_los.at[i, "cnr"],
                    f"{alt}m Radial Wind Speed Raw (m/s)": df_los.at[i, "v_r_raw"],
                    f"{alt}m Radial Wind Speed Modified (m/s)": df_los.at[i, "v_r"],
                })  # could add more here (real_altitude, h interpolation distance to nearest point, ...)

            # append new results to output DataFrame
            results.append(results_row_dict)

            # update Vr history
            v_r_history[1:] = v_r_history[:-1]
            v_r_history[0] = df_los.v_r.to_numpy()
            
            # update unit vector history
            n_history[1:] = n_history[:-1]
            n_history[0] = n

        df_results = pd.DataFrame(results)

        # delete supplementary rows before returning
        history_rows = min(los_per_windvec-1, start_idx)
        if history_rows > 0:
            df_results = df_results.iloc[history_rows:].reset_index(drop=True)
        
        return df_results


    def sync_with_SSR(self):
        """ 
        Function for finding the optimal time shift between LIDAR and motion data timestamps.
        
        Uses iterative optimization based on minimizing the sum of squared residuals (SSR)
        from the least-squares wind vector solution for small time windows (sections of entire rtd set).
        
        The optimized sync shifts are stored in a csv file.
        Use this function before correcting the entire rtd dataset.
        """

        # if synchronization was already done, read file
        if RTD_SYNC_FILE.is_file():
            print("File found: rtd_sync_shift.csv -> reading...")
            df_sync_shift = pd.read_csv("rtd_sync_shift.csv")
            df_sync_shift['Timestamp'] = pd.to_datetime(df_sync_shift['Timestamp'], format="mixed", errors="coerce")
            self.df_WLS_rtd["sync_shift_seconds"] = self.df_WLS_rtd["Timestamp"].map(df_sync_shift.set_index("Timestamp")["sync_shift_seconds"])
            print("rtd_sync_shift.csv integrated.")
            return

        # limits of time shift investigation
        investig_start = self.df_WLS_rtd.iloc[0]['Timestamp'].floor("1h")
        # investig_end = self.df_WLS_rtd.iloc[-1]['Timestamp']
        investig_end = self.df_WLS_rtd.iloc[10000]['Timestamp']

        # define time window for SSR minimization (time shift is assumed constant within this time window)
        window_width = pd.Timedelta(hours=1)

        # iterate through rtd data with variable time windows
        max_iterations_count = 0    # for non-convergence cases
        bracketing_lost_count = 0   # fallback (should theoretically not happen)
        last_sync_shift = 0.0       # fallback value, if optimization is skipped within first time window

        for window_t_start in pd.date_range(start=investig_start, end=investig_end, freq=window_width):

            # define start and end of current time window
            window_t_end = window_t_start + window_width
            print(f"Optimizing sync shift: {window_t_start} to {window_t_end}")

            low_data = False

            # define target function: mean SSR at the altitude of 97m
            def f(x):
                # set sync shift to x within current time window
                self.df_WLS_rtd.loc[(self.df_WLS_rtd["Timestamp"] >= window_t_start) & (self.df_WLS_rtd["Timestamp"] < window_t_end), "sync_shift_seconds"] = x
                
                # process rtd with x as sync shift (this step takes long)
                df_window_corrected = self._process_rtd_section(t_start=window_t_start, t_end=window_t_end, altitudes=RTD_SYNC_ALTITUDES)   # only include altitudes necessary for interpolation
                
                # if more than 80 % NaN -> abort optimization for this time window
                if df_window_corrected[f"{RTD_SYNC_TARGET_ALTITUDE}m SSR (m^2/s^2)"].isna().mean() > RTD_SYNC_MAX_NAN_FRACTION:
                    return None
                
                # calculate and return mean SSR
                return df_window_corrected[f"{RTD_SYNC_TARGET_ALTITUDE}m SSR (m^2/s^2)"].mean()
            
            # lists for parabolic fit with first 3 points
            x = RTD_SYNC_INITIAL_SHIFTS # represents sync shift in (s)
            y = []          # represents corresponding mean SSR at h=97m

            # evaluate target function at first three points
            for xi in x:
                yi = f(xi)
                if yi==None:    # low data case: skip this time window
                    low_data = True
                    break
                y.append(yi)
            
            # abort optimization for this time window if data availabilty is very low. Instead, set sync shift to latest one
            if low_data:
                self.df_WLS_rtd.loc[(self.df_WLS_rtd["Timestamp"] >= window_t_start) & (self.df_WLS_rtd["Timestamp"] < window_t_end), "sync_shift_seconds"] = last_sync_shift
                print("Optimization skipped: < 20% data availability.")
                continue

            # make sure the local minimum of mean SSR is bracketed by the 3 points
            while not (y[1] <= y[0] and y[1] <= y[2]):
                if y[0] < y[2]:
                    # step to the left
                    x = [x[0]-1, x[0], x[1]]
                    y = [f(x[0]), y[0], y[1]]
                else:
                    # step to the right
                    x = [x[1], x[2], x[2]+1]
                    y = [y[1], y[2], f(x[2])]
            
            # iterative search for minimum with parabolic fit
            x_old = x[1]
            iterations = 1
            while True:
                print(f"Iteration {iterations}: parabolic fit with x = {[f'{xi:.3f}' for xi in x]}, y = {[f'{yi:.6f}' for yi in y]}")

                # parabolic fit
                a, b, c = np.polyfit(x, y, 2)   # coefficients ax^2 + bx + c
                x_new = -b / (2*a)  # expected minimum of parabolic fit

                print(f"Expected minimum: x = {x_new:.3f}")

                # break criteria: sync shift tolerance of 0.01 s
                if abs(x_new - x_old) < RTD_SYNC_TOLERANCE or iterations > RTD_SYNC_MAX_ITERATIONS:
                    # set new sync shift within rtd data for current time window
                    self.df_WLS_rtd.loc[(self.df_WLS_rtd["Timestamp"] >= window_t_start) & (self.df_WLS_rtd["Timestamp"] < window_t_end), "sync_shift_seconds"] = x_new
                    last_sync_shift = x_new
                    if iterations > RTD_SYNC_MAX_ITERATIONS:
                        # non-convergence case
                        max_iterations_count += 1
                        print(f"Warning: Max. number ({RTD_SYNC_MAX_ITERATIONS}) of iterations reached. Optimization was stopped with sync_shift = {x_new:.2f} seconds.")
                    else:
                        print(f"Minimum found at sync_shift = {x_new:.2f} seconds")
                    break

                # evaluate target function at expected minimum
                y_new = f(x_new)
                x.append(x_new)
                y.append(y_new) # x and y have now the length 4
                
                # sort by x values
                pts = sorted(zip(x, y), key=lambda p: p[0])
                x = np.array([p[0] for p in pts])
                y = np.array([p[1] for p in pts])

                # find current minimum (i should always be 1 or 2, as the minimum was already bracketed before)
                i = np.argmin(y)
                x_old = x[i]

                # keep left and right neighbor of current minimum
                if i == 0:  #! not good
                    bracketing_lost_count += 1
                    print("KRISE!!!!!")
                    idx = [0, 1, 2]     # fallback: keep first 3 points
                elif i == len(x) - 1:   #! not good
                    bracketing_lost_count += 1
                    print("KRISE!!!!!")
                    idx = [-3, -2, -1]  # fallback: keep last 3 points
                else:
                    idx = [i-1, i, i+1]
                x = list(x[idx])
                y = list(y[idx])

                iterations += 1

            # sum up the optimization so far
            print(f"Bracketing lost count: {bracketing_lost_count}")
            print(f"Iterations over {RTD_SYNC_MAX_ITERATIONS} count: {max_iterations_count}")

        # save the optimized sync shifts as csv
        self.df_WLS_rtd.to_csv(RTD_SYNC_FILE, columns=["Timestamp", "sync_shift_seconds"], index=False)


    def process_entire_rtd(
        self, 
        altitudes: list=None, 
        translation_cor: bool=True, 
        altitude_cor: bool=True, 
        three_los_per_windvec: bool=False,
        create_sta_file: bool=True
    ):
        """ 
        Use this function for processing the entire rtd data that was loaded into self.df_WLS_rtd.
        Each day is saved into a new csv file in the RTD directory.
        
        Options:
        altitudes -> Define selection of nominal altitudes to be post-processed (selection must be included in raw data as well).
        translation_cor -> Choose wether Vr should be corrected for doppler shift distortion due to translational LIDAR motion.
        altitude_cor -> Choose wether Vr should be interpolated to nominal heights (including platform heave, if delta z is defined).
        three_los_per_windvec -> If enabled, only latest 3 Vr are considered for wind vector reconstruction, leading to a 3x3 LES 
        (!not recommended, more prone to measurement errors!).
        """

        # create output directory if not existing
        timestamp_now = pd.Timestamp.now().strftime("%Y-%m-%d_%H-%M-%S")
        rtd_output_dir = self.output_dir / "RTD" / f"rtd_corrected_{timestamp_now}"
        rtd_output_dir.mkdir(parents=True, exist_ok=True)

        # iterate over days in rtd data
        for date in pd.date_range(start=self.df_WLS_rtd.iloc[0]['Timestamp'].date(), end=self.df_WLS_rtd.iloc[-1]['Timestamp'].date(), freq="D"):
            t_start = date
            t_end = date + pd.Timedelta(days=1)

            # process daily rtd data
            print(f"processing rtd data from {date}...")
            df_correted_daily = self._process_rtd_section(
                t_start=t_start, 
                t_end=t_end, 
                altitudes=altitudes, 
                translation_cor=translation_cor, 
                altitude_cor=altitude_cor, 
                three_los_per_windvec=three_los_per_windvec
            )

            # save into csv file
            print(f"saving corrected rtd data for {date.date()}...")
            df_correted_daily.to_csv(rtd_output_dir / f"{date.date()}.csv", index=False)

        # Create new STA file from the corrected data
        if create_sta_file:
            self.create_sta_from_rtd(rtd_directory=rtd_output_dir)


    def create_sta_from_rtd(
        self,
        rtd_directory: str
    ):
        """
        Generates 10-minute statistical data from corrected RTD data.

        The resulting STA data is saved in the same directory as the RTD data was loaded from.
        """

        print("Generating 10-minute statistics from corrected RTD data...")

        # Load corrected RTD data
        csv_files = sorted(rtd_directory.glob("*.csv"))

        if not csv_files:
            raise FileNotFoundError(
                f"No RTD CSV files found in {self.output_dir}"
            )

        dfs = []

        for file in csv_files:
            df = pd.read_csv(file, parse_dates=["Timestamp"])
            dfs.append(df)

        df_WLS_rtd_cor = (
            pd.concat(dfs, ignore_index=True)
            .set_index("Timestamp")
            .sort_index()
        )

        # Define 10-minute timestamp range
        start_time = df_WLS_rtd_cor.index.min().ceil("10min")
        end_time = df_WLS_rtd_cor.index.max().floor("10min")

        timestamp_10min_range = pd.date_range(
            start=start_time,
            end=end_time,
            freq="10min"
        )

        # Calculate 10-minute statistics
        sta_data = []

        for timestamp_10min in timestamp_10min_range:

            # Select RTD data within the last 10 minutes
            df_rtd_10min = df_WLS_rtd_cor.loc[
                timestamp_10min - pd.Timedelta(minutes=10):
                timestamp_10min
            ]

            dict_10min = {
                "Timestamp": timestamp_10min
            }

            for alt in WLS_ALTITUDES:

                wind_speed = df_rtd_10min[f"{alt}m Wind Speed (m/s)"]
                wind_direction = df_rtd_10min[f"{alt}m Wind Direction (°)"]
                z_wind = df_rtd_10min[f"{alt}m Z-wind (m/s)"]

                if not df_rtd_10min.empty:
                    dict_10min[f"{alt}m Wind Speed (m/s)"] = wind_speed.mean()
                    dict_10min[f"{alt}m Wind Speed Dispersion (m/s)"] = wind_speed.std()
                    dict_10min[f"{alt}m Wind Speed min (m/s)"] = wind_speed.min()
                    dict_10min[f"{alt}m Wind Speed max (m/s)"] = wind_speed.max()
                    dict_10min[f"{alt}m Wind Direction (°)"] = (circular_mean_degree(wind_direction))
                    dict_10min[f"{alt}m Z-wind (m/s)"] = z_wind.mean()
                    dict_10min[f"{alt}m Z-wind Dispersion (m/s)"] = z_wind.std()
                    dict_10min[f"{alt}m Data Availability (%)"] = (100 * wind_speed.notna().sum() / len(df_rtd_10min))

                else:
                    dict_10min[f"{alt}m Wind Speed (m/s)"] = np.nan
                    dict_10min[f"{alt}m Wind Speed Dispersion (m/s)"] = np.nan
                    dict_10min[f"{alt}m Wind Speed min (m/s)"] = np.nan
                    dict_10min[f"{alt}m Wind Speed max (m/s)"] = np.nan
                    dict_10min[f"{alt}m Wind Direction (°)"] = np.nan
                    dict_10min[f"{alt}m Z-wind (m/s)"] = np.nan
                    dict_10min[f"{alt}m Z-wind Dispersion (m/s)"] = np.nan
                    dict_10min[f"{alt}m Data Availability (%)"] = 0

            sta_data.append(dict_10min)

        df_WLS_sta_from_rtd = pd.DataFrame(sta_data)

        # Save generated STA data
        output_file = rtd_directory / sta_from_rtd / f"sta_from_rtd.csv"

        df_WLS_sta_from_rtd.to_csv(output_file, index=False)

        print(f"Generated STA data saved to {output_file}")

        return df_WLS_sta_from_rtd


    def correct_sta_wind_direction(self):
        """
        Corrects WLS statistics wind direction data using
        the mean vessel heading during the corresponding
        10-minute measurement interval.

        The original WLS statistics data remains unchanged.
        Corrected data is saved as a separate CSV file.
        """

        print("Correcting WLS statistics wind direction...")

        # Create copy of original WLS statistics data
        df_WLS_sta_corrected = self.df_WLS_sta.copy()

        # Get yaw dataset and column
        yaw_dataset_name = self.motion_channels["yaw"]["dataset"]
        yaw_column = self.motion_channels["yaw"]["column"]

        df_yaw = self.motion_datasets[yaw_dataset_name]

        # Calculate mean heading within the 10-minute intervals
        mean_heading_10min = []

        for t in df_WLS_sta_corrected.index:

            df_yaw_10min = df_yaw.loc[
                t - pd.Timedelta("10min"):t,
                yaw_column
            ]

            mean_heading = circular_mean_degree(df_yaw_10min)

            mean_heading_10min.append(mean_heading)

        # Add mean heading to corrected WLS statistics data
        df_WLS_sta_corrected["mean_heading_deg"] = mean_heading_10min

        # Correct wind direction for each altitude
        for alt in WLS_ALTITUDES:

            column = f"{alt}m Wind Direction (°)"

            df_WLS_sta_corrected[column] = (
                df_WLS_sta_corrected[column]
                + df_WLS_sta_corrected["mean_heading_deg"]
            ) % 360

        # Create output directory
        output_dir = self.output_dir / "STA"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save corrected data
        timestamp_now = pd.Timestamp.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = output_dir / f"sta_corrected_{timestamp_now}.csv"
        df_WLS_sta_corrected.to_csv(output_file, index=True)

        print(f"Corrected WLS statistics data saved to {output_file}")

        return df_WLS_sta_corrected