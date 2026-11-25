"""CSV loading — reads raw rows with line numbers, nothing else."""

import csv
from pathlib import Path

from .models import LoadedRow


class DataFileError(Exception):
    """Raised for fatal file-level problems (missing file, bad header)."""
    pass


def load_csv(file_path: Path, required_columns: set[str]) -> list[LoadedRow]:
    """
    Read a CSV and return every data row with its file line number.
    Header = line 1, first data row = line 2.
    Raises DataFileError for missing files or missing required columns.
    """
    if not file_path.exists():
        raise DataFileError(f"File not found: {file_path}")

    try:
        with open(file_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                raise DataFileError(f"Empty file or missing header: {file_path}")

            missing = required_columns - set(reader.fieldnames)
            if missing:
                raise DataFileError(
                    f"Missing required columns in {file_path.name}: "
                    f"{', '.join(sorted(missing))}"
                )

            return [
                LoadedRow(row_number=idx, values=row)
                for idx, row in enumerate(reader, start=2)
            ]

    except csv.Error as e:
        raise DataFileError(f"CSV parsing error in {file_path.name}: {e}")
    except OSError as e:
        raise DataFileError(f"Cannot read {file_path}: {e}")
