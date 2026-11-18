import sqlite3

from reports.model import ReportSnapshot
from reports.store import get_report


def read_report(db: sqlite3.Connection, report_id: int) -> ReportSnapshot:
    return get_report(db, report_id)
