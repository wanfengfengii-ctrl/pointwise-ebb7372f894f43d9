import sqlite3

from reports.tie_model import TieMeanSnapshot
from reports.tie_store import get_tie_mean_report


def read_tie_mean(db: sqlite3.Connection, report_id: int) -> TieMeanSnapshot:
    return get_tie_mean_report(db, report_id)
