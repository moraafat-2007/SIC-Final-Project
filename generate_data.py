
"""
Generate synthetic HISTORICAL data for the Maintenance Requests project.

Run from anywhere (paths are relative to this file, not to the terminal folder):
    python generate_data.py

Output files (in the data/ folder next to this file):
    data/maintenance_requests.csv   one row per ticket (columns = Ticket.to_dict() keys)
    data/technicians.csv            technician_id, name, specialization
    data/spare_parts_usage.csv      one row per (ticket, spare part), with quantity_used

The data is SYNTHETIC (coursework) but follows realistic rules:
  * demand: Friday is quiet, business-hours peaks, slow growth over the year,
    laptops overheat more in summer;
  * priority depends on how urgent the issue usually is;
  * urgent tickets are assigned and solved faster; more parts = longer repair;
    about 10% of repairs wait for customer approval / part delivery (long tail);
  * technicians only get devices of their specialization, and never more than
    MAX_ACTIVE_TICKETS_PER_TECH tickets "In Progress" (same rule as the app);
  * repair cost = labor + cost of the parts used;
  * status is decided by the export time (SNAPSHOT): unfinished work is recent;
  * each client keeps the same phone number.
The file is reproducible: the same SEED always gives the same CSV files.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR 
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Use the SAME devices/issues as the app (models.py) so the data always matches it.
sys.path.insert(0, str(BASE_DIR))
try:
    from models import DEVICE_ISSUES, MAX_PARTS_PER_TICKET
except ImportError:  # models.py not found -> fallback copy
    DEVICE_ISSUES = {
        "Laptop": ["Battery", "Screen", "Overheating", "Keyboard", "Software"],
        "Printer": ["Paper Jam", "Ink System", "Connectivity", "Print Quality"],
        "Phone": ["Screen", "Battery", "Charging Port", "Software"],
    }
    MAX_PARTS_PER_TICKET = 4

# -----------------------------
# Configuration
# -----------------------------
SEED = 42
NUM_TICKETS = 1000
NUM_CLIENTS = 300
START = pd.Timestamp("2025-10-01")
END = pd.Timestamp("2026-09-30")
# "Now" of the historical export. Fixed (not datetime.now()) so the data is reproducible.
SNAPSHOT = END + pd.Timedelta(hours=23, minutes=59)
# H = historical. A different prefix from live tickets avoids duplicate ticket IDs.
TICKET_ID_PREFIX = "H-"
MAX_ACTIVE_TICKETS_PER_TECH = 3     # same rule as Technician.assign_task in models.py
INJECT_DIRTY_DATA = True            # False -> perfectly clean data

PRIORITIES = ["High", "Normal", "Low"]
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"   # same as Ticket.creation_time

# Egypt work week: Friday is the quietest day. Python weekday(): Mon=0 ... Sun=6
DAY_WEIGHTS = {0: 1.2, 1: 1.1, 2: 1.0, 3: 0.9, 4: 0.3, 5: 0.7, 6: 1.2}
# Requests arrive mostly in business hours: lunch peak and evening peak
HOUR_WEIGHTS = {8: 2, 9: 4, 10: 7, 11: 8, 12: 8, 13: 7, 14: 5, 15: 5,
                16: 6, 17: 7, 18: 6, 19: 5, 20: 3, 21: 1}
DEVICE_WEIGHT = {"Laptop": 0.40, "Phone": 0.35, "Printer": 0.25}
SUMMER = {6: 1.6, 7: 1.9, 8: 1.9, 9: 1.6}

PRIORITY_RESOLVE_FACTOR = {"High": 0.55, "Normal": 1.0, "Low": 1.6}   # urgent = faster
ASSIGN_DELAY_MEDIAN_MIN = {"High": 20, "Normal": 60, "Low": 180}      # minutes to get a technician

# Each technician specializes in one device type.
TECHNICIANS = [
    {"technician_id": "T001", "name": "Ahmed Hassan", "specialization": "Laptop"},
    {"technician_id": "T002", "name": "Mona Ali", "specialization": "Laptop"},
    {"technician_id": "T003", "name": "Omar Samir", "specialization": "Printer"},
    {"technician_id": "T004", "name": "Nour Adel", "specialization": "Printer"},
    {"technician_id": "T005", "name": "Salma Mostafa", "specialization": "Phone"},
    {"technician_id": "T006", "name": "Youssef Khaled", "specialization": "Phone"},
]

# part_id -> (part name, unit cost). LP006 / PR005 / PH005 were added for realism.
PART_INFO = {
    "LP001": ("Laptop Battery", 650), "LP002": ("Laptop Screen", 1200),
    "LP003": ("Keyboard", 350), "LP004": ("Cooling Fan", 250),
    "LP005": ("Charging Adapter", 500), "LP006": ("Thermal Paste", 80),
    "PR001": ("Paper Roller", 300), "PR002": ("Ink Cartridge", 450),
    "PR003": ("Print Head", 900), "PR004": ("USB Cable", 150),
    "PR005": ("Fuser Unit", 700),
    "PH001": ("Phone Battery", 400), "PH002": ("Phone Screen", 850),
    "PH003": ("Charging Port", 300), "PH004": ("Charging Cable", 120),
    "PH005": ("Adhesive Kit", 40),
}

# One entry per (device, issue):
#   w      relative frequency of the issue inside its device
#   urg    urgency 0-1 (higher = more likely High priority)
#   med    median work hours      labor  typical labor fee (EGP)
#   parts  parts that can be used (most likely first)
#   n      probability of using 0,1,2,3,4 parts (units)
#   texts  sample customer descriptions
ISSUE_SPECS = {
    ("Laptop", "Battery"): dict(w=25, urg=.5, med=18, labor=150, parts=["LP001", "LP005"], n=[.15, .65, .20, 0, 0],
                                texts=["Laptop battery drains within an hour", "Laptop shuts down when unplugged"]),
    ("Laptop", "Screen"): dict(w=15, urg=.6, med=36, labor=250, parts=["LP002"], n=[.1, .9, 0, 0, 0],
                               texts=["Cracked laptop screen", "Screen flickers and shows vertical lines"]),
    ("Laptop", "Overheating"): dict(w=20, urg=.7, med=24, labor=200, parts=["LP004", "LP006"], n=[.1, .4, .5, 0, 0],
                                    month_factor=SUMMER,
                                    texts=["Laptop gets very hot and the fan is loud",
                                           "Laptop shuts down by itself after heavy use"]),
    ("Laptop", "Keyboard"): dict(w=10, urg=.3, med=24, labor=120, parts=["LP003"], n=[.1, .9, 0, 0, 0],
                                 texts=["Several keys are not responding", "Keyboard keys stuck after a liquid spill"]),
    ("Laptop", "Software"): dict(w=30, urg=.3, med=6, labor=150, parts=[], n=[1, 0, 0, 0, 0],
                                 texts=["Windows will not boot", "Laptop is very slow and needs a system reinstall"]),
    ("Printer", "Paper Jam"): dict(w=30, urg=.3, med=4, labor=80, parts=["PR001"], n=[.5, .4, .1, 0, 0],
                                   texts=["Paper keeps jamming inside the printer", "Printer pulls several sheets at once"]),
    ("Printer", "Ink System"): dict(w=30, urg=.3, med=10, labor=100, parts=["PR002", "PR003"], n=[.1, .6, .25, .05, 0],
                                    texts=["Printer says the ink cartridge is not recognized",
                                           "Ink is leaking inside the printer"]),
    ("Printer", "Connectivity"): dict(w=25, urg=.4, med=8, labor=100, parts=["PR004"], n=[.7, .3, 0, 0, 0],
                                      texts=["Printer is not detected over Wi-Fi", "Computer cannot find the printer by USB"]),
    ("Printer", "Print Quality"): dict(w=15, urg=.15, med=14, labor=120, parts=["PR002", "PR003", "PR005", "PR001"],
                                       n=[.15, .35, .3, .15, .05],
                                       texts=["Printed pages have lines and faded text",
                                              "Colors are wrong in printed documents"]),
    ("Phone", "Screen"): dict(w=40, urg=.6, med=24, labor=150, parts=["PH002", "PH005"], n=[.05, .5, .45, 0, 0],
                              texts=["Cracked phone screen", "Touch does not respond in some areas"]),
    ("Phone", "Battery"): dict(w=25, urg=.5, med=18, labor=100, parts=["PH001", "PH005"], n=[.1, .55, .35, 0, 0],
                               texts=["Phone battery drains very fast", "Phone turns off at 30 percent"]),
    ("Phone", "Charging Port"): dict(w=20, urg=.7, med=20, labor=120, parts=["PH003", "PH004"], n=[.15, .6, .25, 0, 0],
                                     texts=["Phone does not charge unless the cable is held", "Charging port is loose"]),
    ("Phone", "Software"): dict(w=15, urg=.3, med=5, labor=100, parts=[], n=[1, 0, 0, 0, 0],
                                texts=["Phone is stuck on the boot logo", "Apps keep crashing after an update"]),
}

rng = np.random.default_rng(SEED)


def validate_configuration():
    """Fail early, with a clear message, if the settings do not match models.py."""
    pairs = [(d, i) for d, issues in DEVICE_ISSUES.items() for i in issues]
    missing = [p for p in pairs if p not in ISSUE_SPECS]
    if missing:
        raise KeyError(
            f"models.DEVICE_ISSUES has issues that ISSUE_SPECS does not know: {missing}. "
            "Add them to ISSUE_SPECS (and technicians / parts for any new device)."
        )
    for device in DEVICE_ISSUES:
        if device not in DEVICE_WEIGHT:
            raise KeyError(f"Add '{device}' to DEVICE_WEIGHT.")
        if not any(t["specialization"] == device for t in TECHNICIANS):
            raise KeyError(f"Add at least one technician for '{device}' in TECHNICIANS.")
    for pair in pairs:
        spec = ISSUE_SPECS[pair]
        if len(spec["n"]) != 5 or abs(sum(spec["n"]) - 1) > 1e-9:
            raise ValueError(f"'n' of {pair} must have 5 values that sum to 1.")
        unknown = [p for p in spec["parts"] if p not in PART_INFO]
        if unknown:
            raise KeyError(f"Unknown part ids in {pair}: {unknown}")
    return pairs


def generate_technicians():
    """Create the technician reference table."""
    return pd.DataFrame(TECHNICIANS)


def make_clients():
    """Each client has ONE phone number; some clients open many tickets."""
    prefixes = rng.choice(["010", "011", "012", "015"], NUM_CLIENTS * 3, p=[.4, .2, .3, .1])
    phones = []
    for prefix in prefixes:
        phone = str(prefix) + f"{rng.integers(0, 10 ** 8):08d}"
        if phone not in phones:
            phones.append(phone)
        if len(phones) == NUM_CLIENTS:
            break
    client_ids = [f"C{i:03d}" for i in range(1, NUM_CLIENTS + 1)]
    weights = rng.gamma(0.6, 1.0, NUM_CLIENTS)
    return client_ids, phones, weights / weights.sum()


def make_creation_times():
    """Random creation times with weekday, hour and growth patterns."""
    days = pd.date_range(START, END, freq="D")
    trend = np.linspace(0.8, 1.2, len(days))           # the business grows over the year
    day_w = np.array([DAY_WEIGHTS[d.weekday()] for d in days]) * trend
    day_idx = rng.choice(len(days), NUM_TICKETS, p=day_w / day_w.sum())
    hour_keys = list(HOUR_WEIGHTS)
    hour_p = np.array([HOUR_WEIGHTS[h] for h in hour_keys], dtype=float)
    hours = rng.choice(hour_keys, NUM_TICKETS, p=hour_p / hour_p.sum())
    times = (days[day_idx]
             + pd.to_timedelta(hours, unit="h")
             + pd.to_timedelta(rng.integers(0, 60, NUM_TICKETS), unit="m")
             + pd.to_timedelta(rng.integers(0, 60, NUM_TICKETS), unit="s"))
    return times.sort_values()


def month_probabilities(pairs):
    """Probability of every (device, issue) pair for each month (seasonality)."""
    device_total = sum(DEVICE_WEIGHT[d] for d in DEVICE_ISSUES)
    issue_share = {}
    for device, issue in pairs:
        total = sum(ISSUE_SPECS[(device, i)]["w"] for i in DEVICE_ISSUES[device])
        issue_share[(device, issue)] = ISSUE_SPECS[(device, issue)]["w"] / total
    probs = {}
    for month in range(1, 13):
        w = np.array([
            DEVICE_WEIGHT[d] / device_total
            * issue_share[(d, i)]
            * ISSUE_SPECS[(d, i)].get("month_factor", {}).get(month, 1.0)
            for d, i in pairs])
        probs[month] = w / w.sum()
    return probs


def allocate_parts(candidates, units):
    """Spread `units` parts over the candidate parts -> {part_id: quantity}."""
    if units == 0 or not candidates:
        return {}
    weights = np.array([1 / (k + 1) for k in range(len(candidates))])
    distinct = [str(p) for p in rng.choice(
        candidates, size=min(units, len(candidates)), replace=False, p=weights / weights.sum())]
    quantities = {part_id: 1 for part_id in distinct}
    for _ in range(units - len(distinct)):          # extra units: more of the main part
        quantities[distinct[0]] += 1
    return quantities


def generate_tickets():
    """Generate maintenance tickets and spare-parts usage rows."""
    pairs = validate_configuration()
    month_probs = month_probabilities(pairs)
    creation_times = make_creation_times()
    client_ids, phones, client_weights = make_clients()

    skill = {}   # < 1 = faster technician, > 1 = slower
    for device in DEVICE_ISSUES:
        for k, tech in enumerate([t for t in TECHNICIANS if t["specialization"] == device]):
            skill[tech["technician_id"]] = [0.85, 1.15][k % 2]
    active_load = {t["technician_id"]: 0 for t in TECHNICIANS}

    ticket_rows, usage_rows = [], []
    for number, created_at in enumerate(creation_times, start=1):
        ticket_id = f"{TICKET_ID_PREFIX}{number:04d}"
        device_type, issue_type = pairs[rng.choice(len(pairs), p=month_probs[created_at.month])]
        spec = ISSUE_SPECS[(device_type, issue_type)]

        # priority depends on how urgent this kind of issue usually is
        p_high = 0.05 + 0.45 * spec["urg"]
        p_low = 0.45 - 0.35 * spec["urg"]
        priority = str(rng.choice(PRIORITIES, p=[p_high, 1 - p_high - p_low, p_low]))

        # technician of the right specialization (some are faster than others)
        matching = [t for t in TECHNICIANS if t["specialization"] == device_type]
        chosen_tech = matching[rng.choice(len(matching), p=[0.55, 0.45] if len(matching) == 2 else None)]

        # parts needed by this repair
        units = min(int(rng.choice(5, p=spec["n"])), MAX_PARTS_PER_TICKET)
        quantities = allocate_parts(spec["parts"], units)
        parts_used_num = sum(quantities.values())

        # timeline: assignment delay + work time
        assign_hours = (ASSIGN_DELAY_MEDIAN_MIN[priority] / 60) * np.exp(0.7 * rng.standard_normal())
        work_hours = (spec["med"] * PRIORITY_RESOLVE_FACTOR[priority] * skill[chosen_tech["technician_id"]]
                      * (1 + 0.2 * parts_used_num) * np.exp(0.45 * rng.standard_normal()))
        if rng.random() < 0.10:   # some repairs wait for customer approval or part delivery
            work_hours += rng.uniform(12, 120)
        total_hours = float(np.clip(assign_hours + work_hours, 0.5, 240))
        assigned_at = created_at + pd.Timedelta(hours=float(assign_hours))
        resolved_at = created_at + pd.Timedelta(hours=total_hours)

        # status follows from the export time: unfinished tickets are recent ones
        if resolved_at <= SNAPSHOT:
            status = "Completed"
        elif assigned_at <= SNAPSHOT:
            status = "In Progress"
        else:
            status = "Pending"

        technician_id = None
        resolve_time = None
        repair_cost = None
        ticket_parts_used = 0

        if status == "In Progress":
            free = [t for t in matching if active_load[t["technician_id"]] < MAX_ACTIVE_TICKETS_PER_TECH]
            if free:
                chosen_tech = min(free, key=lambda t: active_load[t["technician_id"]])
                technician_id = chosen_tech["technician_id"]
                active_load[technician_id] += 1
            else:
                status = "Pending"      # nobody free: the ticket waits (as the app would do)

        elif status == "Completed":
            technician_id = chosen_tech["technician_id"]
            resolve_time = resolved_at.strftime(TIME_FORMAT)
            ticket_parts_used = parts_used_num
            labor = spec["labor"] * np.exp(0.25 * rng.standard_normal()) * (1.1 if priority == "High" else 1.0)
            labor = round(labor / 5) * 5
            parts_cost = sum(PART_INFO[p][1] * q for p, q in quantities.items())
            repair_cost = float(labor + parts_cost)
            for part_id, quantity in quantities.items():
                part_name, unit_cost = PART_INFO[part_id]
                usage_rows.append({
                    "ticket_id": ticket_id,
                    "spare_part_id": part_id,
                    "part_name": part_name,
                    "quantity_used": quantity,
                    "unit_cost": unit_cost,
                    "total_part_cost": unit_cost * quantity,
                })

        client = int(rng.choice(NUM_CLIENTS, p=client_weights))
        ticket_rows.append({
            "ticket_id": ticket_id,
            "device_type": device_type,
            "issue_type": issue_type,
            "client_id": client_ids[client],
            "phone_number": phones[client],
            "description": str(rng.choice(spec["texts"])),
            "priority": priority,
            "status": status,
            "technician_id": technician_id,
            "creation_time": created_at.strftime(TIME_FORMAT),
            "resolve_time": resolve_time,
            "repair_cost": repair_cost,
            "parts_used_num": ticket_parts_used,
        })

    tickets_df = pd.DataFrame(ticket_rows)
    usage_df = pd.DataFrame(usage_rows, columns=[
        "ticket_id", "spare_part_id", "part_name", "quantity_used", "unit_cost", "total_part_cost"])
    return tickets_df, usage_df


def inject_dirty_data(tickets_df):
    """Add realistic data problems so the cleaning step in analytics.py has work to do."""
    df = tickets_df.copy()
    completed = df.index[df["status"] == "Completed"]

    def pick(frac, pool=None):
        pool = df.index if pool is None else pool
        return rng.choice(pool, int(frac * len(pool)), replace=False)

    df.loc[pick(0.03, completed), "repair_cost"] = np.nan       # forgotten cost on finished tickets
    df.loc[pick(0.015), "issue_type"] = np.nan                  # issue not recorded
    df.loc[pick(0.01), "description"] = np.nan                  # empty description

    for i in pick(0.02):                                        # inconsistent text: case / spaces
        value = df.at[i, "device_type"]
        df.at[i, "device_type"] = [value.lower() + " ", value.upper(), " " + value][int(rng.integers(0, 3))]

    for i in pick(0.02):                                        # invalid phone numbers
        phone = df.at[i, "phone_number"]
        df.at[i, "phone_number"] = [phone[:9], phone + "7", "03" + phone[2:], phone[:5] + "abc" + phone[8:]][
            int(rng.integers(0, 4))]

    duplicates = df.loc[pick(0.012)]                            # duplicated rows
    df = pd.concat([df, duplicates]).sort_values("creation_time", kind="stable")
    return df.reset_index(drop=True)


def main():
    technicians_df = generate_technicians()
    tickets_df, usage_df = generate_tickets()
    if INJECT_DIRTY_DATA:
        tickets_df = inject_dirty_data(tickets_df)

    technicians_path = OUTPUT_DIR / "technicians.csv"
    tickets_path = OUTPUT_DIR / "maintenance_requests.csv"
    usage_path = OUTPUT_DIR / "spare_parts_usage.csv"

    technicians_df.to_csv(technicians_path, index=False)
    tickets_df.to_csv(tickets_path, index=False)
    usage_df.to_csv(usage_path, index=False)

    print("Synthetic data generated successfully.")
    print(f"Tickets: {len(tickets_df)} -> {tickets_path}")
    print(f"Technicians: {len(technicians_df)} -> {technicians_path}")
    print(f"Spare-parts usage rows: {len(usage_df)} -> {usage_path}")
    unique = tickets_df.drop_duplicates("ticket_id")
    print("\nTicket status counts:")
    print(unique["status"].value_counts())
    print("\nDevice counts:")
    print(unique["device_type"].str.strip().str.title().value_counts())


if __name__ == "__main__":
    main()
