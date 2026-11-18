import sqlite3

from matching.greedy import build_trace
from reports.ap import average_precision
from reports.diagnostics import build_diagnostics
from reports.store import insert_report
from tasks.inputs import load_task_inputs


def issue_report(db: sqlite3.Connection, task_id: int) -> int:
    inputs = load_task_inputs(db, task_id)
    trace = build_trace(inputs)
    ap = average_precision(trace, len(inputs.truth.rows))
    diagnostics = build_diagnostics(inputs, trace)
    return insert_report(db, trace.task_id, ap, diagnostics)
