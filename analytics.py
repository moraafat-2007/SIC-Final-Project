# ==========================================
# Role: Data Analyst (Person 4)
# ==========================================
# المهام المطلوبة في هذا الملف:
# 1. استيراد مكتبة Pandas.
# 2. قراءة ملف البيانات الوهمي (CSV) الخاص بطلبات الصيانة السابقة.
# 3. تنظيف البيانات (التعامل مع القيم المفقودة) وتجميعها (Group by).
# 4. كتابة دوال تُرجع تقارير جاهزة (مثلاً: أكثر الأعطال شيوعاً، أداء الفنيين).
"""
How the Streamlit app (Person 5) should use this module:

    from analytics import (load_and_clean_data, get_full_data, filter_tickets,
                           get_summary_metrics, get_tickets_over_time, ...)

    df = load_and_clean_data()                   # historical data only
    df = get_full_data(live_tickets=load_tickets())   # historical + tickets created in the app

    view = filter_tickets(df, start_date=d1, end_date=d2,
                          device_types=["Laptop"], priorities=["High"])
    get_summary_metrics(view)                    # every report takes a DataFrame,
    get_average_repair_time(view, by="priority") # so ONE filtered DataFrame feeds ALL charts.

Every report function returns a pandas DataFrame (or a dict for KPI cards) and never
raises on an empty filter result: it returns an empty/zero result instead.
"""

import sys
import warnings
from pathlib import Path

import pandas as pd

# Paths are relative to THIS file, so they work no matter where `streamlit run` is started.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REQUESTS_FILE = DATA_DIR / "maintenance_requests.csv"
TECHNICIANS_FILE = DATA_DIR / "technicians.csv"
SPARE_PARTS_FILE = DATA_DIR / "spare_parts_usage.csv"

# Use the team's shared definitions when available (same values as the app).
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
try:
    from models import DEVICE_ISSUES, MAX_PARTS_PER_TICKET
except ImportError:
    DEVICE_ISSUES, MAX_PARTS_PER_TICKET = {}, 4

try:
    from validation import is_valid_phone       # the team's regex, one rule for the whole project
except ImportError:
    import re

    def is_valid_phone(phone_number):
        return re.match(r"^01[0125][0-9]{8}$", str(phone_number)) is not None

PRIORITIES = ["High", "Normal", "Low"]
STATUSES = ["Pending", "In Progress", "Completed"]

# Same keys as Ticket.to_dict() in models.py
TICKET_COLUMNS = [
    "ticket_id", "device_type", "issue_type", "client_id", "phone_number",
    "description", "priority", "status", "technician_id",
    "creation_time", "resolve_time", "repair_cost", "parts_used_num",
]
# Columns that every report needs. phone_number and description are optional.
REQUIRED_TICKET_COLUMNS = [
    "ticket_id", "creation_time", "device_type", "issue_type", "priority",
    "client_id", "technician_id", "status", "resolve_time", "repair_cost",
    "parts_used_num",
]
OPTIONAL_TICKET_COLUMNS = ["phone_number", "description"]

TECHNICIAN_COLUMNS = ["technician_id", "name", "specialization"]
SPARE_PART_COLUMNS = ["ticket_id", "spare_part_id", "part_name",
                      "quantity_used", "unit_cost", "total_part_cost"]
STRING_COLUMNS = {"ticket_id": str, "client_id": str,
                  "technician_id": str, "phone_number": str}   # keep leading zeros / IDs as text


# =====================================================================
# 1) Loading and cleaning
# =====================================================================

def _clean_category(series, valid_names, report, key):
    """Strip spaces, fix letter case using the official names, count the fixes."""
    original = series.astype(object)
    cleaned = series.astype("string").str.strip()
    if valid_names:
        lookup = {name.lower(): name for name in valid_names}
    else:   # no official list: use the most frequent spelling of each value
        lookup = {}
        for value in cleaned.dropna().value_counts().index:
            lookup.setdefault(str(value).lower(), str(value))
    mapped = cleaned.str.lower().map(lookup)
    cleaned = mapped.where(mapped.notna(), cleaned)
    cleaned = cleaned.astype(object)
    report[key] = int((cleaned.fillna("") != original.fillna("")).sum())
    return cleaned.fillna("Unknown").replace("", "Unknown")


def _to_datetime(series):
    """Parse dates; invalid values become NaT (without pandas' format-guessing warning)."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Could not infer format")
        return pd.to_datetime(series, errors="coerce")


def clean_tickets(raw_df, source="historical", return_report=False):
    """Clean a tickets DataFrame (historical CSV or live tickets).

    Cleaning rules (nothing is invented):
    - Drop rows without a ticket_id or without a valid creation_time.
    - Keep one row per ticket_id (first occurrence).
    - Strip spaces and fix letter case of device/issue/priority/status;
      missing categories become "Unknown".
    - Convert dates and numbers; invalid values become missing (NaT / NaN).
    - Missing repair_cost is NOT filled: it is simply left out of cost averages.
    - Negative durations / costs and parts counts outside 0..MAX_PARTS_PER_TICKET
      are treated as data errors (set to missing).
    - phone_valid marks numbers that fail the team's phone regex (rows are kept).
    """
    missing_columns = [c for c in REQUIRED_TICKET_COLUMNS if c not in raw_df.columns]
    if missing_columns:
        raise ValueError("The tickets data is missing required columns: " + ", ".join(missing_columns))

    df = raw_df.copy()
    for column in OPTIONAL_TICKET_COLUMNS:
        if column not in df.columns:
            df[column] = None
    report = {"rows_raw": len(df)}

    # ids and duplicates
    df = df.dropna(subset=["ticket_id"]).copy()
    df["ticket_id"] = df["ticket_id"].astype(str).str.strip()
    df = df[df["ticket_id"] != ""]
    report["rows_without_id_removed"] = report["rows_raw"] - len(df)
    before = len(df)
    df = df.drop_duplicates(subset=["ticket_id"], keep="first").copy()
    report["duplicate_rows_removed"] = before - len(df)

    # text columns
    device_names = list(DEVICE_ISSUES)
    issue_names = sorted({i for issues in DEVICE_ISSUES.values() for i in issues})
    df["device_type"] = _clean_category(df["device_type"], device_names, report, "device_type_fixed")
    df["issue_type"] = _clean_category(df["issue_type"], issue_names, report, "issue_type_fixed")
    df["priority"] = _clean_category(df["priority"], PRIORITIES, report, "priority_fixed")
    df["status"] = _clean_category(df["status"], STATUSES, report, "status_fixed")

    # dates (invalid -> NaT)
    df["creation_time"] = _to_datetime(df["creation_time"])
    df["resolve_time"] = _to_datetime(df["resolve_time"])
    before = len(df)
    df = df[df["creation_time"].notna()].copy()
    report["rows_without_valid_creation_time_removed"] = before - len(df)

    # numbers (invalid -> NaN)
    for column in ["repair_cost", "parts_used_num"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    report["negative_costs_set_missing"] = int((df["repair_cost"] < 0).sum())
    df.loc[df["repair_cost"] < 0, "repair_cost"] = float("nan")
    bad_parts = (df["parts_used_num"] < 0) | (df["parts_used_num"] > MAX_PARTS_PER_TICKET)
    report["invalid_parts_counts_set_missing"] = int(bad_parts.sum())
    df.loc[bad_parts, "parts_used_num"] = float("nan")

    # time from ticket creation until it was resolved (includes the waiting time)
    df["repair_hours"] = (df["resolve_time"] - df["creation_time"]).dt.total_seconds() / 3600
    report["negative_durations_set_missing"] = int((df["repair_hours"] < 0).sum())
    df.loc[df["repair_hours"] < 0, "repair_hours"] = float("nan")

    # phone validation (rows are kept; phone is not used in the statistics)
    df["phone_number"] = df["phone_number"].astype("string").str.strip().astype(object)
    df["phone_valid"] = df["phone_number"].apply(is_valid_phone).astype(bool)
    report["invalid_phone_numbers"] = int((~df["phone_valid"]).sum())

    completed = df["status"].eq("Completed")
    report["completed_without_repair_cost"] = int((completed & df["repair_cost"].isna()).sum())
    report["completed_without_resolve_time"] = int((completed & df["resolve_time"].isna()).sum())

    df["is_completed"] = completed
    df["is_in_progress"] = df["status"].eq("In Progress")
    df["is_pending"] = df["status"].eq("Pending")
    df["source"] = source

    df = df.sort_values("creation_time", kind="stable").reset_index(drop=True)
    report["rows_clean"] = len(df)
    return (df, report) if return_report else df


def load_and_clean_data(file_path=REQUESTS_FILE, return_report=False):
    """Read the historical tickets CSV and clean it (see clean_tickets).

    With return_report=True it returns (DataFrame, cleaning_report_dict).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Could not find {file_path}. Run generate_data.py first.")
    raw = pd.read_csv(file_path, dtype=STRING_COLUMNS)
    return clean_tickets(raw, source="historical", return_report=return_report)


def tickets_to_dataframe(tickets):
    """Convert Ticket objects (or dicts) from the app into a raw DataFrame."""
    records = []
    for ticket in tickets or []:
        records.append(ticket.to_dict() if hasattr(ticket, "to_dict") else dict(ticket))
    return pd.DataFrame(records, columns=TICKET_COLUMNS)


def get_full_data(live_tickets=None, historical_path=REQUESTS_FILE, include_historical=True):
    """Historical data + tickets created in the app, cleaned and merged.

    live_tickets: the list returned by data_manager.load_tickets() (Ticket objects).
    The column "source" tells where each row comes from ("historical" / "live").
    """
    frames = []
    if include_historical:
        frames.append(load_and_clean_data(historical_path))
    if live_tickets:
        live = clean_tickets(tickets_to_dataframe(live_tickets), source="live")
        if frames:
            overlap = set(frames[0]["ticket_id"]) & set(live["ticket_id"])
            if overlap:
                warnings.warn(f"{len(overlap)} ticket_id values exist in both historical and live "
                              "data (example: " + sorted(overlap)[0] + "). Use different ID prefixes.")
        if not live.empty:
            frames.append(live)
    frames = [f for f in frames if not f.empty]
    if not frames:
        return clean_tickets(pd.DataFrame(columns=TICKET_COLUMNS))
    return pd.concat(frames, ignore_index=True).sort_values("creation_time", kind="stable").reset_index(drop=True)


# =====================================================================
# 2) Filtering (for the interactive admin dashboard)
# =====================================================================

def _as_list(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def filter_tickets(df, start_date=None, end_date=None, device_types=None, issue_types=None,
                   priorities=None, statuses=None, technician_ids=None, client_ids=None,
                   source=None, date_column="creation_time"):
    """Return the tickets that match ALL the given filters (None = no filter).

    Dates may be date / datetime / "YYYY-MM-DD" strings. end_date is inclusive:
    end_date="2026-03-31" includes every ticket created on March 31.
    Other filters accept one value or a list of values.
    """
    if date_column not in ("creation_time", "resolve_time"):
        raise ValueError("date_column must be 'creation_time' or 'resolve_time'.")
    mask = pd.Series(True, index=df.index)

    if start_date is not None:
        mask &= df[date_column] >= pd.Timestamp(start_date)
    if end_date is not None:
        end = pd.Timestamp(end_date)
        end = end + pd.Timedelta(days=1) if end == end.normalize() else end + pd.Timedelta(seconds=1)
        mask &= df[date_column] < end

    for column, values in [("device_type", device_types), ("issue_type", issue_types),
                           ("priority", priorities), ("status", statuses),
                           ("technician_id", technician_ids), ("client_id", client_ids),
                           ("source", source)]:
        values = _as_list(values)
        if values is not None:
            mask &= df[column].isin(values)

    return df.loc[mask].reset_index(drop=True)


def get_date_bounds(df):
    """(first_date, last_date) of creation_time as python dates, or (None, None)."""
    dates = df["creation_time"].dropna()
    if dates.empty:
        return None, None
    return dates.min().date(), dates.max().date()


def get_filter_options(df):
    """Values for the dashboard widgets (selectboxes / multiselects)."""
    def values(column):
        return sorted(df[column].dropna().astype(str).unique().tolist())

    return {
        "device_types": values("device_type"),
        "issue_types": values("issue_type"),
        "priorities": [p for p in PRIORITIES if p in set(df["priority"])] +
                      [p for p in values("priority") if p not in PRIORITIES],
        "statuses": [s for s in STATUSES if s in set(df["status"])] +
                    [s for s in values("status") if s not in STATUSES],
        "technician_ids": values("technician_id"),
        "date_bounds": get_date_bounds(df),
    }


# =====================================================================
# 3) Reports (all take a possibly filtered DataFrame)
# =====================================================================

def _check_columns(df, columns):
    columns = [columns] if isinstance(columns, str) else list(columns)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Unknown column(s) {missing}. Available: {list(df.columns)}")
    return columns


def _ordered_counts(df, column, order):
    counts = df[column].value_counts()
    rows = [(value, int(counts.get(value, 0))) for value in order]
    rows += [(value, int(count)) for value, count in counts.items() if value not in order]
    return pd.DataFrame(rows, columns=[column, "ticket_count"])


def get_summary_metrics(df):
    """Overall counts, completion rate, costs and repair duration (for KPI cards)."""
    total = len(df)
    completed_df = df[df["status"].eq("Completed")]
    costs = pd.to_numeric(completed_df["repair_cost"], errors="coerce")
    durations = pd.to_numeric(completed_df["repair_hours"], errors="coerce")
    completed = len(completed_df)
    return {
        "total_tickets": total,
        "completed_tickets": completed,
        "in_progress_tickets": int(df["status"].eq("In Progress").sum()),
        "pending_tickets": int(df["status"].eq("Pending").sum()),
        "completion_rate_pct": round(completed / total * 100, 2) if total else 0.0,
        "total_repair_cost": round(float(costs.sum()), 2),
        "average_repair_cost": round(float(costs.mean()), 2) if costs.notna().any() else 0.0,
        "average_repair_hours": round(float(durations.mean()), 2) if durations.notna().any() else 0.0,
    }


def get_device_failure_counts(df):
    """Maintenance requests per device type.

    These are request counts, not failure RATES: the data does not say how many
    devices of each type exist.
    """
    return (df.groupby("device_type").size().reset_index(name="ticket_count")
            .sort_values("ticket_count", ascending=False).reset_index(drop=True))


def get_issue_counts(df):
    """Requests for each device/issue combination."""
    return (df.groupby(["device_type", "issue_type"]).size().reset_index(name="ticket_count")
            .sort_values("ticket_count", ascending=False).reset_index(drop=True))


def get_priority_counts(df):
    """Tickets per priority, always in the order High, Normal, Low (zeros included)."""
    return _ordered_counts(df, "priority", PRIORITIES)


def get_status_counts(df):
    """Tickets per status, always in the order Pending, In Progress, Completed."""
    return _ordered_counts(df, "status", STATUSES)


def get_tickets_over_time(df, freq="M"):
    """Number of tickets created per day ("D"), week ("W"), month ("M") or quarter ("Q").

    Periods without tickets appear with 0, so line charts have no gaps.
    """
    if freq not in ("D", "W", "M", "Q"):
        raise ValueError("freq must be one of 'D', 'W', 'M', 'Q'.")
    dates = df["creation_time"].dropna()
    if dates.empty:
        return pd.DataFrame({"period": pd.to_datetime([]), "ticket_count": pd.Series([], dtype=int)})
    counts = dates.dt.to_period(freq).value_counts().sort_index()
    full = pd.period_range(counts.index.min(), counts.index.max(), freq=freq)
    counts = counts.reindex(full, fill_value=0)
    return pd.DataFrame({"period": full.to_timestamp(), "ticket_count": counts.values.astype(int)})


def get_average_repair_time(df, by="device_type"):
    """Completed tickets and repair time (hours) grouped by one or more columns.

    Examples: by="device_type" (default), by="priority", by="issue_type",
    by=["device_type", "issue_type"]. Time = creation_time -> resolve_time.
    """
    by = _check_columns(df, by)
    completed = df[df["status"].eq("Completed")]
    result = (completed.groupby(by)
              .agg(completed_tickets=("ticket_id", "count"),
                   average_repair_hours=("repair_hours", "mean"),
                   median_repair_hours=("repair_hours", "median"))
              .reset_index())
    result[["average_repair_hours", "median_repair_hours"]] = (
        result[["average_repair_hours", "median_repair_hours"]].round(2))
    return (result.sort_values("average_repair_hours", ascending=False, na_position="last")
            .reset_index(drop=True))


def get_cost_summary(df, by="device_type"):
    """Repair cost of completed tickets grouped by one or more columns.

    Tickets whose cost is missing are counted in completed_tickets but not in the averages.
    """
    by = _check_columns(df, by)
    completed = df[df["status"].eq("Completed")]
    result = (completed.groupby(by)
              .agg(completed_tickets=("ticket_id", "count"),
                   tickets_with_cost=("repair_cost", "count"),
                   total_cost=("repair_cost", "sum"),
                   average_cost=("repair_cost", "mean"))
              .reset_index())
    result[["total_cost", "average_cost"]] = result[["total_cost", "average_cost"]].round(2)
    return result.sort_values("total_cost", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------
# Technicians and spare parts (reference files)
# ---------------------------------------------------------------------

def load_technicians(file_path=TECHNICIANS_FILE):
    """Read technicians.csv. Missing file -> empty table (reports still work)."""
    file_path = Path(file_path)
    if not file_path.exists():
        warnings.warn(f"{file_path} not found; technician names will be shown as IDs.")
        return pd.DataFrame(columns=TECHNICIAN_COLUMNS)
    technicians = pd.read_csv(file_path, dtype={"technician_id": str})
    missing = [c for c in TECHNICIAN_COLUMNS if c not in technicians.columns]
    if missing:
        raise ValueError("The technicians CSV is missing columns: " + ", ".join(missing))
    technicians["technician_id"] = technicians["technician_id"].str.strip()
    return technicians[TECHNICIAN_COLUMNS].drop_duplicates("technician_id")


def get_technician_performance(df, technicians_df=None):
    """Workload and speed per technician (only technicians who have tickets in df).

    technicians_df: optional DataFrame; if None, data/technicians.csv is used.
    Pending tickets have no technician and are not counted.
    """
    columns = TECHNICIAN_COLUMNS + ["assigned_tickets", "completed_tickets", "in_progress_tickets",
                                    "completion_rate_pct", "average_repair_hours", "total_repair_cost"]
    assigned = df[df["technician_id"].notna()].copy()
    assigned = assigned[assigned["technician_id"].astype(str).str.strip() != ""]
    if assigned.empty:
        return pd.DataFrame(columns=columns)

    assigned["technician_id"] = assigned["technician_id"].astype(str).str.strip()
    assigned["repair_cost_done"] = assigned["repair_cost"].where(assigned["is_completed"])
    performance = (assigned.groupby("technician_id")
                   .agg(assigned_tickets=("ticket_id", "count"),
                        completed_tickets=("is_completed", "sum"),
                        in_progress_tickets=("is_in_progress", "sum"),
                        average_repair_hours=("repair_hours", "mean"),
                        total_repair_cost=("repair_cost_done", "sum"))
                   .reset_index())
    for column in ["completed_tickets", "in_progress_tickets"]:
        performance[column] = performance[column].astype(int)
    performance["completion_rate_pct"] = (
        performance["completed_tickets"] / performance["assigned_tickets"] * 100).round(1)
    performance["average_repair_hours"] = performance["average_repair_hours"].round(2)
    performance["total_repair_cost"] = performance["total_repair_cost"].round(2)

    technicians = load_technicians() if technicians_df is None else technicians_df
    technicians = technicians[[c for c in TECHNICIAN_COLUMNS if c in technicians.columns]].copy()
    technicians["technician_id"] = technicians["technician_id"].astype(str).str.strip()
    performance = performance.merge(technicians.drop_duplicates("technician_id"),
                                    on="technician_id", how="left")
    if "name" not in performance.columns:
        performance["name"] = None
    if "specialization" not in performance.columns:
        performance["specialization"] = None
    performance["name"] = performance["name"].fillna(performance["technician_id"])
    performance["specialization"] = performance["specialization"].fillna("Unknown")

    return (performance[columns].sort_values("completed_tickets", ascending=False)
            .reset_index(drop=True))


def load_spare_parts(file_path=SPARE_PARTS_FILE):
    """Read spare_parts_usage.csv. Missing file -> empty table (reports still work)."""
    file_path = Path(file_path)
    if not file_path.exists():
        warnings.warn(f"{file_path} not found; spare-parts reports will be empty.")
        return pd.DataFrame(columns=SPARE_PART_COLUMNS)
    parts = pd.read_csv(file_path, dtype={"ticket_id": str, "spare_part_id": str})
    missing = [c for c in SPARE_PART_COLUMNS if c not in parts.columns]
    if missing:
        raise ValueError("The spare-parts CSV is missing columns: " + ", ".join(missing))
    parts["ticket_id"] = parts["ticket_id"].str.strip()
    for column in ["quantity_used", "unit_cost", "total_part_cost"]:
        parts[column] = pd.to_numeric(parts[column], errors="coerce")
    return parts


def get_spare_parts_summary(parts_df=None, tickets_df=None, top_n=None):
    """Total quantity and cost per spare part.

    tickets_df: pass the FILTERED tickets so only parts used in those tickets are counted
                (e.g. a date range or a device type). None = all parts.
    Only historical tickets have spare-part details; live tickets only store parts_used_num.
    """
    columns = ["spare_part_id", "part_name", "tickets_using_part",
               "total_quantity_used", "total_part_cost"]
    parts = load_spare_parts() if parts_df is None else parts_df.copy()
    if tickets_df is not None:
        parts = parts[parts["ticket_id"].isin(tickets_df["ticket_id"])]
    if parts.empty:
        return pd.DataFrame(columns=columns)
    result = (parts.groupby(["spare_part_id", "part_name"])
              .agg(tickets_using_part=("ticket_id", "nunique"),
                   total_quantity_used=("quantity_used", "sum"),
                   total_part_cost=("total_part_cost", "sum"))
              .reset_index()
              .sort_values(["total_quantity_used", "total_part_cost"], ascending=False)
              .reset_index(drop=True))
    return result.head(top_n) if top_n else result


# =====================================================================
# Quick demo:  python analytics.py
# =====================================================================

# if __name__ == "__main__":
#     tickets_df, cleaning_report = load_and_clean_data(return_report=True)

#     print("Cleaning report:")
#     for key, value in cleaning_report.items():
#         print(f"  {key}: {value}")

#     print("\nSummary metrics:")
#     for metric, value in get_summary_metrics(tickets_df).items():
#         print(f"  {metric}: {value}")

#     print("\nRequests by device:")
#     print(get_device_failure_counts(tickets_df))

#     print("\nAverage repair time by priority:")
#     print(get_average_repair_time(tickets_df, by="priority"))

#     print("\nTickets per month:")
#     print(get_tickets_over_time(tickets_df, "M"))

#     print("\nTechnician performance:")
#     print(get_technician_performance(tickets_df).to_string())

#     print("\nTop spare parts:")
#     print(get_spare_parts_summary(tickets_df=tickets_df, top_n=5))

#     first, last = get_date_bounds(tickets_df)
#     view = filter_tickets(tickets_df, start_date=last.replace(day=1), device_types=["Laptop"])
#     print(f"\nFilter example (Laptop tickets since {last.replace(day=1)}): {len(view)} tickets")ابدأ كتابة الكود هنا
