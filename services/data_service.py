"""
Data loading and processing service.

Handles Excel/CSV file loading, column mapping, paginated preview,
and automatic CSV correction.
"""

import os
import re
import io
import logging
import pandas as pd

logger = logging.getLogger(__name__)


# ── CSV auto-fix helpers ────────────────────────────────────────────

def _detect_encoding(filepath):
    """Try common encodings and return the one that works."""
    for enc in ('utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1'):
        try:
            with open(filepath, encoding=enc) as f:
                f.read(4096)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return 'utf-8'


def _detect_delimiter(filepath, encoding):
    """Sniff the delimiter from the first few lines."""
    with open(filepath, encoding=encoding) as f:
        sample = f.read(8192)
    for delim in (',', ';', '\t', '|'):
        # Pick the one that gives a consistent column count
        lines = sample.strip().split('\n')
        counts = [line.count(delim) for line in lines[:10] if line.strip()]
        if counts and min(counts) > 0 and max(counts) == min(counts):
            return delim
    return ','


def _clean_columns(df):
    """Strip whitespace and invisible chars from column names."""
    df.columns = [
        re.sub(r'[\x00-\x1f\x7f-\x9f]', '', str(c)).strip()
        for c in df.columns
    ]
    # Replace empty column names with Column_N
    df.columns = [
        c if c else f'Column_{i}' for i, c in enumerate(df.columns)
    ]
    return df


def _clean_values(df):
    """Strip whitespace from string cells, drop completely empty rows."""
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({'nan': '', 'None': ''})
    # Drop rows where every cell is empty
    df = df.dropna(how='all').reset_index(drop=True)
    mask = df.apply(lambda row: not all(str(v).strip() == '' for v in row), axis=1)
    df = df[mask].reset_index(drop=True)
    return df


def load_data(filepath):
    """
    Load an Excel or CSV file into a DataFrame.

    For CSV files, auto-detects encoding and delimiter, cleans columns
    and values. Returns (df, fixes) where fixes is a list of strings
    describing what was corrected.
    """
    ext = os.path.splitext(filepath)[1].lower()
    fixes = []

    if ext == '.csv':
        encoding = _detect_encoding(filepath)
        if encoding != 'utf-8':
            fixes.append(f"Encoding corrected: detected {encoding}")
            logger.info("CSV encoding: %s", encoding)

        delimiter = _detect_delimiter(filepath, encoding)
        if delimiter != ',':
            fixes.append(f"Delimiter corrected: detected '{delimiter}'")
            logger.info("CSV delimiter: %s", repr(delimiter))

        df = pd.read_csv(filepath, encoding=encoding, sep=delimiter,
                         skipinitialspace=True, on_bad_lines='warn')

    elif ext in ('.xls', '.xlsx'):
        df = pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # ── Auto-fixes applied to all formats ───────────────────────
    orig_cols = list(df.columns)
    df = _clean_columns(df)
    if list(df.columns) != orig_cols:
        fixes.append("Column names cleaned (whitespace/invisible chars removed)")

    orig_len = len(df)
    df = _clean_values(df)
    dropped = orig_len - len(df)
    if dropped > 0:
        fixes.append(f"Removed {dropped} empty row(s)")

    # Deduplicate column names
    seen = {}
    new_cols = []
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            new_name = f"{c}_{seen[c]}"
            fixes.append(f"Duplicate column '{c}' renamed to '{new_name}'")
            new_cols.append(new_name)
        else:
            seen[c] = 0
            new_cols.append(c)
    df.columns = new_cols

    if len(df) == 0:
        raise ValueError("The file has no usable data rows after cleanup")

    logger.info("Data loaded: %d rows, %d columns, %d fixes",
                len(df), len(df.columns), len(fixes))
    return df, fixes


def get_preview(df, page=0, per_page=10):
    """Return paginated preview data for the DataFrame."""
    total = len(df)
    total_pages = max(1, (total - 1) // per_page + 1)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    end = min(start + per_page, total)
    chunk = df.iloc[start:end]

    return {
        'columns': list(df.columns),
        'rows': [[str(v) for v in row] for row in chunk.values.tolist()],
        'indices': list(range(start, end)),
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    }


def default_placeholder(column_name):
    """Generate a default placeholder name from a column name."""
    return re.sub(r'[^a-z0-9_]', '', column_name.strip().replace(' ', '_').lower())
