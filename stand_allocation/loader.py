"""CSV file loading."""

import csv
from pathlib import Path

from .models import LoadedRow


class DataFileError(Exception):
    """Fatal error with a data file."""
    pass


def load_csv(file_path: Path, required_columns: set[str]) -> list[LoadedRow]:
    """
    Load a CSV file and return raw rows with line numbers.
    
    Args:
        file_path: Path to the CSV file
        required_columns: Column names that must be present in the header
        
    Returns:
        List of LoadedRow objects (header is line 1, first data row is line 2)
        
    Raises:
        DataFileError: If file missing, unreadable, or header invalid
    """
    if not file_path.exists():
        raise DataFileError(f"File not found: {file_path}")
    
    try:
        with open(file_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            
            # Check header
            if reader.fieldnames is None:
                raise DataFileError(f"Empty file or missing header: {file_path}")
            
            present_columns = set(reader.fieldnames)
            missing_columns = required_columns - present_columns
            
            if missing_columns:
                raise DataFileError(
                    f"Missing required columns in {file_path.name}: "
                    f"{', '.join(sorted(missing_columns))}"
                )
            
            # Load rows (line numbering: header = 1, first data row = 2)
            rows = []
            for idx, row in enumerate(reader, start=2):
                # DictReader gives None for missing values in short rows
                rows.append(LoadedRow(row_number=idx, values=row))
            
            return rows
            
    except csv.Error as e:
        raise DataFileError(f"CSV parsing error in {file_path.name}: {e}")
    except OSError as e:
        raise DataFileError(f"Cannot read {file_path}: {e}")
