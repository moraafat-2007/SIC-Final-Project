"""JSON persistence and ticket workflows for the RepairOps application."""

import base64
import hashlib
import heapq
import hmac
import json
import os
import secrets
import shutil
import tempfile
import uuid
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

from models import (
    MAX_PARTS_PER_TICKET,
    MAX_TECHNICIAN_WORKLOAD,
    Client,
    DEVICE_ISSUES,
    Manager,
    Technician,
    Ticket,
)
from validation import is_valid_phone


DATA_DIRECTORY = Path(__file__).resolve().parent
USERS_FILE = DATA_DIRECTORY / "users.json"
TICKETS_FILE = DATA_DIRECTORY / "tickets.json"
BRANCHES_FILE = DATA_DIRECTORY / "branches.json"
REQUESTS_FILE = DATA_DIRECTORY / "maintenance_requests.csv"
TECHNICIANS_FILE = DATA_DIRECTORY / "technicians.csv"
PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 310_000
DEFAULT_ADMIN_EMAIL = "admin@repairops.com"
DEFAULT_ADMIN_PASSWORD = "admin123"
PRIORITY_WEIGHTS = {"High": 1, "Normal": 2, "Low": 3}


class TicketQueue:
    """Maintain tickets in priority order with stable ordering for equal priorities."""

    def __init__(self):
        """Initialize an empty priority heap."""
        self.heap = []
        self.counter = 0

    def add_ticket(self, ticket):
        """Add one supported ticket to the priority heap."""
        if not isinstance(ticket, Ticket):
            raise TypeError("TicketQueue accepts Ticket instances.")
        if ticket.priority not in PRIORITY_WEIGHTS:
            raise ValueError(f"Unsupported priority: {ticket.priority}")
        heapq.heappush(
            self.heap,
            (PRIORITY_WEIGHTS[ticket.priority], self.counter, ticket),
        )
        self.counter += 1

    def get_next_ticket(self):
        """Remove and return the highest-priority ticket, or None when empty."""
        if not self.heap:
            return None
        _, _, ticket = heapq.heappop(self.heap)
        ticket.status = "In Progress"
        return ticket

    def get_prioritized_tickets(self):
        """Return a priority-ordered snapshot without modifying this queue."""
        return [entry[2] for entry in sorted(self.heap)]

    def is_empty(self):
        """Return whether this queue contains no tickets."""
        return not self.heap


class TicketHashTable:
    """Index ticket IDs and exact phone numbers for average O(1) lookups."""

    def __init__(self):
        """Initialize ticket-ID and phone-number indexes."""
        self.tickets_by_id = {}
        self.tickets_by_phone = {}

    def insert(self, ticket):
        """Insert or replace a ticket and synchronize both indexes."""
        if not isinstance(ticket, Ticket):
            raise TypeError("TicketHashTable accepts Ticket instances.")
        existing = self.tickets_by_id.get(ticket.ticket_id)
        if existing is not None:
            old_phone = str(existing.phone_number).strip()
            old_tickets = self.tickets_by_phone.get(old_phone, [])
            remaining = [
                item for item in old_tickets if item.ticket_id != ticket.ticket_id
            ]
            if remaining:
                self.tickets_by_phone[old_phone] = remaining
            else:
                self.tickets_by_phone.pop(old_phone, None)

        self.tickets_by_id[ticket.ticket_id] = ticket
        phone = str(ticket.phone_number).strip()
        if phone:
            self.tickets_by_phone.setdefault(phone, []).append(ticket)

    def search_by_id(self, ticket_id):
        """Return the matching ticket by exact ID in average O(1) time."""
        return self.tickets_by_id.get(str(ticket_id).strip())

    def search_by_phone(self, phone_number):
        """Return a copy of tickets matching an exact phone number."""
        return list(self.tickets_by_phone.get(str(phone_number).strip(), ()))


class UndoStack:
    """Session-local LIFO history of reversible admin actions, bounded to 20."""

    def __init__(self, max_size=20):
        """Create an empty history with a positive maximum size."""
        if not isinstance(max_size, int) or isinstance(max_size, bool) or max_size < 1:
            raise ValueError("Undo stack maximum size must be a positive integer.")
        self.history = []
        self.max_size = max_size

    def push(self, action_type, description, snapshot):
        """Record an admin action and its ticket and technician snapshot."""
        if not isinstance(snapshot, dict):
            raise TypeError("Undo snapshots must be dictionaries.")
        self.history.append(
            {
                "action_type": str(action_type),
                "description": str(description),
                "snapshot": snapshot,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        if len(self.history) > self.max_size:
            self.history.pop(0)

    def pop(self):
        """Remove and return the newest action, or None when the stack is empty."""
        return self.history.pop() if self.history else None

    def peek(self):
        """Return the newest action without removing it, or None if empty."""
        return self.history[-1] if self.history else None

    def get_history(self):
        """Return a newest-first copy of the action history."""
        return list(reversed(self.history))

    def is_empty(self):
        """Return whether this undo stack has no recorded actions."""
        return not self.history


def _read_records(path):
    """Read and validate a JSON list of mapping records from disk."""
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    if not contents.strip():
        return []
    try:
        records = json.loads(contents)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} contains invalid JSON.") from error
    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        raise ValueError(f"{path.name} must contain a JSON array of objects.")
    return records


def _write_records(path, records):
    """Atomically write JSON records so interrupted writes do not corrupt data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as data_file:
            temporary_path = Path(data_file.name)
            json.dump(records, data_file, ensure_ascii=False, indent=2)
            data_file.write("\n")
            data_file.flush()
            os.fsync(data_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _seed_user_records():
    """Create hashed demo accounts used only when the user store needs recovery."""
    demo_passwords = {
        "admin@repairops.com": "admin123",
        "client1@repairops.com": "client123",
        "fatma@repairops.com": "Client@12345",
        "tech1@repairops.com": "tech123",
        "tech2@repairops.com": "tech123",
        "tech3@repairops.com": "tech123",
    }
    accounts = [
        {
            "ID": "ADMIN-001",
            "name": "RepairOps Administrator",
            "email": "admin@repairops.com",
            "role": "Manager",
        },
        {
            "ID": "C-CLIENT001",
            "name": "Ali Mohamed",
            "email": "client1@repairops.com",
            "role": "Client",
            "tickets": [
                "L-DEMO-001",
                "L-DEMO-002",
                "L-DEMO-004",
                "L-DEMO-007",
            ],
        },
        {
            "ID": "C-CLIENT002",
            "name": "Fatma Ibrahim",
            "email": "fatma@repairops.com",
            "role": "Client",
            "tickets": [
                "L-DEMO-003",
                "L-DEMO-005",
                "L-DEMO-006",
                "L-DEMO-008",
                "L-DEMO-009",
            ],
        },
        {
            "ID": "T-TECH001",
            "name": "Ahmed Hassan",
            "email": "tech1@repairops.com",
            "role": "Technician",
            "specialization": "Laptop",
        },
        {
            "ID": "T-TECH002",
            "name": "Omar Samir",
            "email": "tech2@repairops.com",
            "role": "Technician",
            "specialization": "Printer",
        },
        {
            "ID": "T-TECH003",
            "name": "Salma Mostafa",
            "email": "tech3@repairops.com",
            "role": "Technician",
            "specialization": "Phone",
        },
    ]
    for account in accounts:
        account["password"] = hash_password(demo_passwords[account["email"]])
        if account["role"] == "Technician":
            account.update(
                {"is_available": True, "workload": 0, "assigned_tickets": []}
            )
    return accounts


def _seed_ticket_records():
    """Create varied demo requests used only when the ticket store needs recovery."""
    demo_tickets = [
        ("001", "Laptop", "Screen", "C-CLIENT001", "01000000001", "High", "Pending", None, "2026-10-14 09:00:00", None, None),
        ("002", "Laptop", "Battery", "C-CLIENT001", "01000000001", "Normal", "Pending", None, "2026-10-13 11:00:00", None, None),
        ("003", "Printer", "Paper Jam", "C-CLIENT002", "01000000002", "Low", "Pending", None, "2026-10-12 13:00:00", None, None),
        ("004", "Laptop", "Overheating", "C-CLIENT001", "01000000001", "High", "In Progress", "T-TECH001", "2026-10-12 09:00:00", None, None),
        ("005", "Printer", "Ink System", "C-CLIENT002", "01000000002", "Normal", "In Progress", "T-TECH002", "2026-10-11 11:30:00", None, None),
        ("006", "Phone", "Charging Port", "C-CLIENT002", "01000000002", "High", "In Progress", "T-TECH003", "2026-10-10 15:00:00", None, None),
        ("007", "Laptop", "Keyboard", "C-CLIENT001", "01000000001", "Normal", "Completed", "T-TECH001", "2026-10-08 10:00:00", 450.0, "2026-10-09 14:30:00"),
        ("008", "Printer", "Connectivity", "C-CLIENT002", "01000000002", "Low", "Completed", "T-TECH002", "2026-10-06 13:00:00", 120.0, "2026-10-07 09:15:00"),
        ("009", "Phone", "Battery", "C-CLIENT002", "01000000002", "High", "Completed", "T-TECH003", "2026-10-04 09:30:00", 550.0, "2026-10-05 12:45:00"),
    ]
    additional_tickets = [
        ("010", "Laptop", "Battery", "C-CLIENT001", "01000000001", "High", "Pending", None, "2026-10-03 09:00:00", None, None),
        ("011", "Printer", "Connectivity", "C-CLIENT002", "01000000002", "Normal", "Pending", None, "2026-10-02 10:00:00", None, None),
        ("012", "Phone", "Screen", "C-CLIENT001", "01000000001", "High", "Pending", None, "2026-10-01 11:00:00", None, None),
        ("013", "Laptop", "Keyboard", "C-CLIENT002", "01000000002", "Low", "Pending", None, "2026-09-28 12:00:00", None, None),
        ("014", "Printer", "Paper Jam", "C-CLIENT001", "01000000001", "Normal", "Pending", None, "2026-09-25 13:00:00", None, None),
        ("015", "Laptop", "Software", "C-CLIENT001", "01000000001", "Normal", "In Progress", "T-TECH001", "2026-09-20 09:00:00", None, None),
        ("016", "Printer", "Print Quality", "C-CLIENT002", "01000000002", "High", "In Progress", "T-TECH002", "2026-09-18 10:00:00", None, None),
        ("017", "Phone", "Charging Port", "C-CLIENT001", "01000000001", "Normal", "In Progress", "T-TECH003", "2026-09-15 11:00:00", None, None),
        ("018", "Laptop", "Overheating", "C-CLIENT002", "01000000002", "High", "Completed", "T-TECH001", "2026-08-25 09:00:00", 325.0, "2026-08-26 11:00:00"),
        ("019", "Printer", "Ink System", "C-CLIENT001", "01000000001", "Normal", "Completed", "T-TECH002", "2026-08-12 10:00:00", 185.0, "2026-08-12 14:00:00"),
        ("020", "Phone", "Battery", "C-CLIENT002", "01000000002", "High", "Completed", "T-TECH003", "2026-07-22 11:00:00", 610.0, "2026-07-23 13:00:00"),
        ("021", "Laptop", "Screen", "C-CLIENT001", "01000000001", "Normal", "Completed", "T-TECH001", "2026-07-10 09:00:00", 480.0, "2026-07-11 12:00:00"),
        ("022", "Printer", "Connectivity", "C-CLIENT002", "01000000002", "Low", "Completed", "T-TECH002", "2026-06-18 10:00:00", 120.0, "2026-06-18 15:00:00"),
        ("023", "Phone", "Software", "C-CLIENT001", "01000000001", "Normal", "Completed", "T-TECH003", "2026-05-14 11:00:00", 210.0, "2026-05-15 10:00:00"),
        ("024", "Laptop", "Keyboard", "C-CLIENT002", "01000000002", "High", "Completed", "T-TECH001", "2026-04-10 09:00:00", 295.0, "2026-04-11 12:00:00"),
        ("025", "Printer", "Paper Jam", "C-CLIENT001", "01000000001", "Normal", "Completed", "T-TECH002", "2026-03-08 10:00:00", 95.0, "2026-03-08 12:30:00"),
    ]
    demo_tickets.extend(additional_tickets)
    records = []
    for ticket in demo_tickets:
        suffix, device, issue, client_id, phone, priority, status, technician_id, created, cost, resolved = ticket
        records.append(
            {
                "ticket_id": f"L-DEMO-{suffix}",
                "device_type": device,
                "issue_type": issue,
                "client_id": client_id,
                "phone_number": phone,
                "description": f"Demo {device.lower()} repair request for {issue.lower()}.",
                "priority": priority,
                "status": status,
                "technician_id": technician_id,
                "creation_time": created,
                "resolve_time": resolved,
                "repair_cost": cost,
                "parts_used_num": 1 if cost is not None else 0,
                "rating": 5 if cost is not None else None,
                "feedback": "Demo repair completed." if cost is not None else None,
            }
        )
    return records


def _preserve_invalid_store(path):
    """Move a malformed store aside before replacing it with safe seed data."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(
        f"{path.stem}.corrupt-{timestamp}-{uuid.uuid4().hex[:8]}{path.suffix}"
    )
    try:
        shutil.copy2(path, backup_path)
    except OSError as error:
        raise OSError(f"Could not preserve invalid data from {path.name}.") from error
    return backup_path


def _load_or_seed(path, seed_factory, record_loader):
    """Load valid records or preserve and replace missing, empty, or invalid data."""
    invalid = False
    try:
        records = _read_records(path)
    except (OSError, UnicodeError, ValueError):
        records = None
        invalid = path.exists()

    if records:
        try:
            for record in records:
                record_loader(record)
        except (KeyError, TypeError, ValueError):
            invalid = True

    if records is None or not records or invalid:
        if invalid and path.exists():
            _preserve_invalid_store(path)
        records = seed_factory()
        for record in records:
            record_loader(record)
        _write_records(path, records)
    return records


def _ticket_from_record(record):
    """Rebuild a Ticket while retaining persisted lifecycle fields."""
    ticket = Ticket(
        ticket_id=record["ticket_id"],
        device_type=record["device_type"],
        issue_type=record["issue_type"],
        client_id=record["client_id"],
        phone_number=record["phone_number"],
        description=record.get("description", ""),
        priority=record.get("priority", "Normal"),
    )
    for field in (
        "status",
        "technician_id",
        "creation_time",
        "resolve_time",
        "repair_cost",
        "parts_used_num",
        "rating",
        "feedback",
        "technician_notes",
    ):
        if field in record:
            setattr(ticket, field, record[field])
    return ticket


def _validate_ticket_record(record):
    """Validate ticket fields required by the lifecycle and operational views."""
    ticket = _ticket_from_record(record)
    if ticket.status not in {"Pending", "In Progress", "Completed"}:
        raise ValueError("Ticket status is not supported.")
    if ticket.device_type not in DEVICE_ISSUES:
        raise ValueError("Ticket device type is not supported.")
    if ticket.issue_type not in DEVICE_ISSUES[ticket.device_type]:
        raise ValueError("Ticket issue does not match its device type.")
    if ticket.priority not in {"High", "Normal", "Low"}:
        raise ValueError("Ticket priority is not supported.")
    if not ticket.ticket_id or not ticket.client_id or not ticket.phone_number:
        raise ValueError("Ticket is missing a required identifier or contact number.")
    return ticket


def _user_from_record(record):
    """Rebuild the supported user subtype, including legacy account fields."""
    user_id = record.get("ID", record.get("id"))
    role = record["role"]
    if user_id is None or not str(user_id).strip() or any(
        not record.get(field) for field in ("name", "email", "password")
    ):
        raise ValueError("A user JSON record is missing required account fields.")
    common = (
        user_id,
        record.get("name", ""),
        record.get("email", ""),
        record.get("password", ""),
    )
    if role == "Manager":
        user = Manager(*common)
    elif role == "Technician":
        user = Technician(
            *common,
            record.get("specialization", "General"),
        )
        user.is_available = record.get("is_available", True)
        user.workload = record.get("workload", 0)
        user.assigned_tickets = list(record.get("assigned_tickets", []))
    elif role == "Client":
        user = Client(*common)
        user.tickets = list(record.get("tickets", []))
    else:
        raise ValueError(f"Unsupported user role in JSON: {role}")
    return user


def save_users(users):
    """Serialize application users to users.json."""
    _write_records(USERS_FILE, [user.to_dict() for user in users])


def load_users():
    """Load user accounts from users.json."""
    records = _load_or_seed(USERS_FILE, _seed_user_records, _user_from_record)
    return [_user_from_record(record) for record in records]


def save_tickets(tickets):
    """Serialize live tickets to tickets.json."""
    _write_records(TICKETS_FILE, [ticket.to_dict() for ticket in tickets])


def load_tickets():
    """Load live tickets from tickets.json."""
    records = _load_or_seed(
        TICKETS_FILE, _seed_ticket_records, _validate_ticket_record
    )
    return [_ticket_from_record(record) for record in records]


def save_branches(branches):
    """Persist branch records after validating their map coordinates."""
    records = []
    for branch in branches:
        record = dict(branch)
        try:
            latitude = float(record["latitude"])
            longitude = float(record["longitude"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Every branch needs valid latitude and longitude.") from error
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Branch coordinates are outside valid map ranges.")
        if not record.get("name") or not record.get("city") or not record.get("address"):
            raise ValueError("Every branch needs a name, city, and address.")
        record["latitude"] = latitude
        record["longitude"] = longitude
        records.append(record)
    _write_records(BRANCHES_FILE, records)


def load_branches():
    """Load configured branch locations, returning an empty list if not configured."""
    records = _load_or_seed(BRANCHES_FILE, list, _validate_branch_record)
    return [_validate_branch_record(branch) for branch in records]


def _validate_branch_record(branch):
    """Validate a branch record and normalize its geographic coordinates."""
    try:
        latitude = float(branch["latitude"])
        longitude = float(branch["longitude"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Branch record contains invalid map coordinates.") from error
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Branch coordinates are outside valid map ranges.")
    if not all(branch.get(field) for field in ("name", "city", "address")):
        raise ValueError("Branch record needs a name, city, and address.")
    return {**branch, "latitude": latitude, "longitude": longitude}


def build_ticket_index(tickets=None):
    """Build and return the exact-ID and exact-phone lookup index."""
    ticket_list = load_tickets() if tickets is None else list(tickets)
    index = TicketHashTable()
    for ticket in ticket_list:
        index.insert(ticket)
    return index


def sync_technician_workloads(users, tickets):
    """Reconcile technician workload fields with currently active ticket assignments."""
    active_by_technician = {}
    for ticket in tickets:
        if ticket.status == "In Progress" and ticket.technician_id:
            active_by_technician.setdefault(ticket.technician_id, []).append(
                ticket.ticket_id
            )
    changed = False
    for user in users:
        if isinstance(user, Technician):
            assigned_tickets = active_by_technician.get(user.ID, [])
            workload = len(assigned_tickets)
            is_available = workload < MAX_TECHNICIAN_WORKLOAD
            changed |= (
                user.assigned_tickets != assigned_tickets
                or user.workload != workload
                or user.is_available != is_available
            )
            user.assigned_tickets = assigned_tickets
            user.workload = workload
            user.is_available = is_available
    return changed


def get_prioritized_tickets(tickets=None):
    """Return pending tickets by High, Normal, Low priority, then other statuses."""
    ticket_list = load_tickets() if tickets is None else list(tickets)
    queue = TicketQueue()
    other_tickets = []
    for ticket in ticket_list:
        if ticket.status == "Pending":
            queue.add_ticket(ticket)
        else:
            other_tickets.append(ticket)
    return queue.get_prioritized_tickets() + other_tickets


def process_next_ticket(tickets=None, users=None):
    """Assign the highest-priority ticket to an available matching technician."""
    ticket_list = load_tickets() if tickets is None else list(tickets)
    user_list = load_users() if users is None else list(users)
    sync_technician_workloads(user_list, ticket_list)
    queue = TicketQueue()
    for ticket in ticket_list:
        if ticket.status == "Pending":
            queue.add_ticket(ticket)
    for ticket in queue.get_prioritized_tickets():
        technician = next(
            (
                user
                for user in user_list
                if isinstance(user, Technician)
                and user.is_available
                and user.workload < MAX_TECHNICIAN_WORKLOAD
                and user.specialization == ticket.device_type
            ),
            None,
        )
        if technician is None:
            continue
        ticket.assign_technician(technician.ID)
        technician.assign_task(ticket.ticket_id)
        save_tickets(ticket_list)
        save_users(user_list)
        return ticket
    return None


# Historical and live ticket analytics.

PRIORITIES = ["High", "Normal", "Low"]

STATUSES = ["Pending", "In Progress", "Completed"]

TICKET_COLUMNS = [
    "ticket_id", "device_type", "issue_type", "client_id", "phone_number",
    "description", "priority", "status", "technician_id",
    "creation_time", "resolve_time", "repair_cost", "parts_used_num",
]

REQUIRED_TICKET_COLUMNS = [
    "ticket_id", "creation_time", "device_type", "issue_type", "priority",
    "client_id", "technician_id", "status", "resolve_time", "repair_cost",
    "parts_used_num",
]

OPTIONAL_TICKET_COLUMNS = ["phone_number", "description"]

TECHNICIAN_COLUMNS = ["technician_id", "name", "specialization"]

STRING_COLUMNS = {"ticket_id": str, "client_id": str,
                  "technician_id": str, "phone_number": str}

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
    cleaned = mapped.where(mapped.notna(), "Unknown")
    cleaned = cleaned.astype(object)
    report[key] = int((cleaned.fillna("") != original.fillna("")).sum())
    return cleaned.fillna("Unknown").replace("", "Unknown")

def _namespace_ticket_ids(series, source):
    """Apply a stable historical or live prefix without duplicating an existing prefix."""
    prefix = {"historical": "H-", "live": "L-"}.get(source)
    if prefix is None:
        return series
    normalized = series.astype(str).str.strip()
    expected = normalized.str.upper().str.startswith(prefix)
    canonical = normalized.where(~expected, prefix + normalized.str.slice(len(prefix)))
    return canonical.where(expected, prefix + normalized)

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
    df["ticket_id"] = _namespace_ticket_ids(df["ticket_id"], source)
    report["rows_without_id_removed"] = report["rows_raw"] - len(df)
    before = len(df)
    df = df.drop_duplicates(subset=["ticket_id"], keep="first").copy()
    report["duplicate_rows_removed"] = before - len(df)

    # text columns
    device_names = list(DEVICE_ISSUES)
    issue_names = sorted({i for issues in DEVICE_ISSUES.values() for i in issues})
    df["device_type"] = _clean_category(df["device_type"], device_names, report, "device_type_fixed")
    df["issue_type"] = _clean_category(df["issue_type"], issue_names, report, "issue_type_fixed")
    valid_issue = df.apply(
        lambda row: row["issue_type"] in DEVICE_ISSUES.get(row["device_type"], ()),
        axis=1,
    )
    report["issues_not_matching_device_set_unknown"] = int((~valid_issue).sum())
    df.loc[~valid_issue, "issue_type"] = "Unknown"
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
        raise FileNotFoundError(f"Could not find historical ticket data: {file_path}.")
    raw = pd.read_csv(file_path, dtype=STRING_COLUMNS)
    return clean_tickets(raw, source="historical", return_report=return_report)

def tickets_to_dataframe(tickets):
    """Convert Ticket objects (or dicts) from the app into a raw DataFrame."""
    records = []
    for ticket in tickets or []:
        records.append(ticket.to_dict() if hasattr(ticket, "to_dict") else dict(ticket))
    return pd.DataFrame(records, columns=TICKET_COLUMNS)

def get_full_data(
    live_tickets=None,
    historical_path=REQUESTS_FILE,
    include_historical=True,
    historical_data=None,
):
    """Return cleaned historical data combined with live application tickets.

    live_tickets: the list returned by data_manager.load_tickets() (Ticket objects).
    The column "source" tells where each row comes from ("historical" / "live").
    historical_data: optional already-cleaned historical DataFrame, useful for
        applications that cache the CSV at startup.
    """
    frames = []
    if include_historical:
        if historical_data is not None:
            frames.append(historical_data.copy())
        elif Path(historical_path).exists():
            frames.append(load_and_clean_data(historical_path))
        else:
            warnings.warn(
                f"Historical ticket data is unavailable: {historical_path}.",
                RuntimeWarning,
                stacklevel=2,
            )
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

def _as_list(value):
    """Normalize a scalar or sequence filter into a list, preserving None."""
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
    required_columns = {
        date_column, "device_type", "issue_type", "priority", "status",
        "technician_id", "client_id", "source",
    }
    missing = sorted(required_columns.difference(df.columns))
    if missing:
        raise ValueError("The tickets data is missing filter columns: " + ", ".join(missing))
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


def hash_password(password):
    """Return a salted PBKDF2-SHA256 password representation."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return (
        f"{PASSWORD_HASH_PREFIX}${PASSWORD_HASH_ITERATIONS}"
        f"${salt_text}${digest_text}"
    )


def verify_password(password, stored_password):
    """Verify a salted password hash or a legacy plaintext credential."""
    if not isinstance(password, str) or not isinstance(stored_password, str):
        return False
    if not stored_password.startswith(f"{PASSWORD_HASH_PREFIX}$"):
        return hmac.compare_digest(password, stored_password)

    try:
        _, iterations, salt_text, expected_text = stored_password.split("$", 3)
        iteration_count = int(iterations)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
        if not 100_000 <= iteration_count <= 2_000_000:
            return False
        if len(salt) < 16 or len(expected) != hashlib.sha256().digest_size:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iteration_count,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def login(email, password):
    """Authenticate by email and upgrade valid plaintext credentials."""
    users_database = load_users()
    normalized_email = str(email or "").strip().casefold()
    for user in users_database:
        if (
            user.email.strip().casefold() == normalized_email
            and verify_password(password, user.password)
        ):
            if not user.password.startswith(f"{PASSWORD_HASH_PREFIX}$"):
                user.password = hash_password(password)
                save_users(users_database)
            return user
    return None


def register(ID, name, email, password, role, specialization=None):
    """Validate, hash, persist, and return a client or technician account."""
    from validation import validate_registration

    users_database = load_users()
    errors = validate_registration(
        users_database,
        name,
        email,
        password,
        role,
        specialization=specialization,
        ID=ID,
    )
    if errors:
        return {
            "success": False,
            "message": "Please correct the following errors.",
            "errors": errors,
        }

    password_hash = hash_password(password)
    if role == "Technician":
        user = Technician(
            ID,
            name.strip(),
            email.strip(),
            password_hash,
            specialization.strip(),
        )
    else:
        user = Client(ID, name.strip(), email.strip(), password_hash)
    users_database.append(user)
    save_users(users_database)
    return {
        "success": True,
        "message": "Registration successful.",
        "user": user,
    }


def bootstrap_system():
    """Initialize JSON stores, hash legacy passwords, and ensure a default manager."""
    users_database = load_users()
    credentials_updated = False
    for user in users_database:
        if not user.password.startswith(f"{PASSWORD_HASH_PREFIX}$"):
            user.password = hash_password(user.password)
            credentials_updated = True

    matching_admin = next(
        (
            user
            for user in users_database
            if user.email.strip().casefold() == DEFAULT_ADMIN_EMAIL.casefold()
        ),
        None,
    )
    if matching_admin is not None:
        if not isinstance(matching_admin, Manager):
            raise ValueError(
                "The default administrator email belongs to a non-manager account."
            )
        workload_updated = sync_technician_workloads(
            users_database, load_tickets()
        )
        if credentials_updated or workload_updated:
            save_users(users_database)
        return False

    existing_ids = {user.ID for user in users_database}
    admin_id = "ADMIN-001"
    suffix = 1
    while admin_id in existing_ids:
        suffix += 1
        admin_id = f"ADMIN-{suffix:03d}"
    users_database.append(
        Manager(
            ID=admin_id,
            name="RepairOps Administrator",
            email=DEFAULT_ADMIN_EMAIL,
            password=hash_password(DEFAULT_ADMIN_PASSWORD),
        )
    )
    sync_technician_workloads(users_database, load_tickets())
    save_users(users_database)
    return True


def change_password(user_id, current_password, new_password):
    """Validate and persist a new password after verifying the current one."""
    from validation import validate_password

    users_database = load_users()
    user = next((item for item in users_database if item.ID == user_id), None)
    if user is None:
        message = "Account was not found."
        return {"success": False, "message": message, "errors": [message]}
    if not verify_password(current_password, user.password):
        message = "Current password is incorrect."
        return {"success": False, "message": message, "errors": [message]}
    errors = validate_password(new_password)
    if errors:
        return {
            "success": False,
            "message": "Please choose a stronger password.",
            "errors": errors,
        }
    if verify_password(new_password, user.password):
        message = "New password must differ from the current password."
        return {"success": False, "message": message, "errors": [message]}
    user.password = hash_password(new_password)
    save_users(users_database)
    return {
        "success": True,
        "message": "Password updated successfully.",
        "errors": [],
    }


def admin_reset_password(
    manager_email,
    manager_password,
    target_identifier,
    new_password,
):
    """Reset an account password after authenticating an authorized manager."""
    from validation import validate_password

    users_database = load_users()
    manager_email = str(manager_email or "").strip().casefold()
    manager = next(
        (
            user
            for user in users_database
            if isinstance(user, Manager)
            and user.email.strip().casefold() == manager_email
        ),
        None,
    )
    if manager is None or not verify_password(manager_password, manager.password):
        message = "Manager authentication failed."
        return {"success": False, "message": message, "errors": [message]}

    identifier = str(target_identifier or "").strip().casefold()
    target = next(
        (
            user
            for user in users_database
            if user.ID.casefold() == identifier
            or user.email.strip().casefold() == identifier
        ),
        None,
    )
    if target is None:
        message = "The account ID or email was not found."
        return {"success": False, "message": message, "errors": [message]}

    errors = validate_password(new_password)
    if errors:
        return {
            "success": False,
            "message": "Please choose a stronger password.",
            "errors": errors,
        }
    if verify_password(new_password, target.password):
        message = "The new password must differ from the current password."
        return {"success": False, "message": message, "errors": [message]}

    target.password = hash_password(new_password)
    save_users(users_database)
    return {
        "success": True,
        "message": f"Password reset successfully for {target.email}.",
        "errors": [],
    }
