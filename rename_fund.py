#!/usr/bin/env python
"""Safely rename a fund across units.csv, transactions.csv, and the
daily_totals.csv history, instead of hand-editing the name in units.csv -
which silently orphans that fund's history column (a new column starts up
under the new name, and the old column just stops updating).

Usage:
    python rename_fund.py "Old Fund Name" "New Fund Name"
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from persistence import resolve_history_path
from transactions import resolve_transactions_path, resolve_units_path


def _rename_in_csv(path: Path, column: str, old: str, new: str) -> bool:
    if not path.exists():
        return False
    df = pd.read_csv(path)
    if column not in df.columns:
        return False
    mask = df[column] == old
    if not mask.any():
        return False
    df.loc[mask, column] = new
    df.to_csv(path, index=False)
    return True


def rename_fund(old: str, new: str) -> list[str]:
    changed = []
    if _rename_in_csv(resolve_units_path(), "fund", old, new):
        changed.append(str(resolve_units_path()))
    if _rename_in_csv(resolve_transactions_path(), "fund", old, new):
        changed.append(str(resolve_transactions_path()))

    history_path = resolve_history_path()
    if history_path.exists():
        df = pd.read_csv(history_path)
        if old in df.columns:
            if new in df.columns:
                # Both columns exist (e.g. rename applied after some history
                # already accrued under the new name) - merge, preferring
                # whichever value each row actually has for the new name.
                df[new] = df[new].combine_first(df[old])
                df = df.drop(columns=[old])
            else:
                df = df.rename(columns={old: new})
            df.to_csv(history_path, index=False)
            changed.append(str(history_path))

    return changed


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('Usage: python rename_fund.py "Old Fund Name" "New Fund Name"')
        sys.exit(1)

    changed_files = rename_fund(sys.argv[1], sys.argv[2])
    if not changed_files:
        print(f"No occurrences of '{sys.argv[1]}' found anywhere.")
    else:
        print(f"Renamed '{sys.argv[1]}' -> '{sys.argv[2]}' in: {', '.join(changed_files)}")
