import pandas as pd
import re
import io
from pathlib import Path


# Timestamp regex for filtering broken RTD lines
TIMESTAMP_PATTERN = re.compile(
    r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}"
)

# Number of header lines in WLS files
HEADER_LINES = 42


def parse_wls_rtd(input_dir, output_file):
    """
    Reads all WLS .rtd files in the input directory,
    removes broken lines, combines the data and saves it as CSV.

    Returns:
        pd.DataFrame: Combined RTD data.
    """

    print("Parsing WLS-RTD data...")

    data = []
    broken_count = 0

    # Iterate through all subdirectories
    for subdirectory in sorted(Path(input_dir).iterdir()):

        if not subdirectory.is_dir() or not subdirectory.name.endswith(".rtd"):
            continue

        file = subdirectory / subdirectory.name

        if not file.exists():
            print(f"File not found: {file}")
            continue

        try:
            clean_lines = []

            # Read file and filter broken lines
            with open(file, "r", encoding="latin1") as f:

                for line_number, line in enumerate(f):

                    # Keep header lines unchanged
                    if line_number < HEADER_LINES:
                        clean_lines.append(line.strip() + "\n")
                        continue

                    # Find all timestamps in the current line
                    matches = list(TIMESTAMP_PATTERN.finditer(line))

                    if matches:
                        # Use the part starting at the last timestamp
                        last_match = matches[-1]

                        clean_lines.append(
                            line[last_match.start():].strip() + "\n"
                        )

                        # Count lines containing a broken preceding part
                        if last_match.start() != 0:
                            broken_count += 1
                            print(
                                f"Warning in {file}: line {line_number} "
                                "contains a broken preceding part."
                            )

                    else:
                        print(
                            f"Warning in {file}: "
                            f"no timestamp found in line {line_number}"
                        )

            # Convert cleaned data into a buffer
            clean_data = "".join(clean_lines)
            buffer = io.StringIO(clean_data)

            # Read cleaned data as CSV
            df_file = pd.read_csv(
                buffer,
                sep="\t",
                skiprows=HEADER_LINES - 1,
                index_col=False
            )

            df_file.columns = df_file.columns.str.strip()

            # Convert timestamp to datetime
            df_file["Timestamp"] = pd.to_datetime(
                df_file["Timestamp"],
                format="%Y/%m/%d %H:%M:%S.%f"
            )

            data.append(df_file)

        except Exception as e:
            print(f"Error while reading {file}: {e}")

    if not data:
        raise ValueError("No WLS RTD data found.")

    # Create output directory if necessary
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Concat data from all files and save as CSV
    df = pd.concat(data, ignore_index=True)
    df.to_csv(output_file, index=False)

    print(f"Number of broken RTD lines: {broken_count}")

    return df


def parse_wls_sta(input_dir, output_file):
    """
    Reads all WLS .sta files in the input directory,
    combines the data and saves it as CSV.

    Returns:
        pd.DataFrame: Combined STA data.
    """

    print("Parsing WLS-STA data...")

    data = []

    # Iterate through all subdirectories
    for subdirectory in sorted(Path(input_dir).iterdir()):

        if not subdirectory.is_dir() or not subdirectory.name.endswith(".sta"):
            continue

        file = subdirectory / subdirectory.name

        if not file.exists():
            print(f"File not found: {file}")
            continue

        try:
            # Read STA file
            df_file = pd.read_csv(
                file,
                sep="\t",
                skiprows=HEADER_LINES - 1,
                encoding="latin1",
                index_col=False
            )

            df_file.columns = df_file.columns.str.strip()

            # Convert timestamp to datetime
            df_file["Timestamp (end of interval)"] = pd.to_datetime(
                df_file["Timestamp (end of interval)"],
                format="%Y/%m/%d %H:%M"
            )

            data.append(df_file)

        except Exception as e:
            print(f"Error while reading {file}: {e}")

    if not data:
        raise ValueError("No WLS STA data found.")

    # Create output directory if necessary
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Concat data from all files and save as CSV
    df = pd.concat(data, ignore_index=True)
    df.to_csv(output_file, index=False)

    return df