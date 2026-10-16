"""Role-based Streamlit application for RepairOps ticket operations."""

import html
import uuid

import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_manager import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    admin_reset_password,
    UndoStack,
    bootstrap_system,
    build_ticket_index,
    change_password,
    filter_tickets,
    get_full_data,
    get_summary_metrics,
    get_technician_performance,
    get_tickets_over_time,
    get_prioritized_tickets,
    load_and_clean_data,
    load_branches,
    load_tickets,
    load_users,
    login,
    process_next_ticket,
    register,
    REQUESTS_FILE,
    save_branches,
    save_tickets,
    save_users,
    sync_technician_workloads,
    TICKETS_FILE,
    TicketQueue,
)
from models import (
    DEVICE_ISSUES,
    MAX_PARTS_PER_TICKET,
    MAX_TECHNICIAN_WORKLOAD,
    Technician,
)
from validation import is_valid_phone, validate_ticket_request


st.set_page_config(
    page_title="RepairOps | Service Command",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _apply_theme():
    """Apply the shared baby-blue and dark navy dashboard theme."""
    st.markdown(
        """
        <style>
        :root { color-scheme: dark; }
        .stApp { background: #0B132B; color: #E2E8F0; } /* Deep Dark Navy */
        [data-testid="stHeader"] { background: rgba(11, 19, 43, 0.9); }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #1C2541 0%, #0B132B 100%);
            border-right: 1px solid #3A506B;
        }
        h1, h2, h3 { color: #89CFF0; letter-spacing: -.02em; } /* Baby Blue Text */
        div[data-testid="stMetric"] {
            background: linear-gradient(145deg, #1C2541, #131B33);
            border-left: 5px solid #89CFF0; /* Baby Blue Accent border */
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4);
        }
        div[data-testid="stMetricValue"] { color: #FFFFFF; font-weight: bold; }
        .hero-kicker { color: #89CFF0; font-size: 0.85rem; font-weight: 800; letter-spacing: 0.15em; }
        .hero-title { color: #FFFFFF; font-size: 2.2rem; font-weight: 800; }
        .ticket-card {
            background: linear-gradient(145deg, #1C2541, #131B33);
            border: 1px solid #3A506B; border-radius: 12px; padding: 15px; margin-bottom: 12px;
        }
        .ticket-id { color: #89CFF0; font-weight: 800; }
        div.stButton > button[kind="primary"] {
            background: #1C2541; border: 1px solid #89CFF0; color: #89CFF0; border-radius: 8px; font-weight: bold;
        }
        div.stButton > button[kind="primary"]:hover {
            background: #89CFF0; color: #0B132B;
        }
        .section-label { color: #89CFF0; font-size: 0.8rem; font-weight: bold; text-transform: uppercase; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _hero(title, subtitle, kicker="REPAIR OPERATIONS"):
    """Render a consistent page heading."""
    st.markdown(
        f'<div class="hero-kicker">{html.escape(kicker)}</div>'
        f'<div class="hero-title">{html.escape(title)}</div>'
        f'<div class="hero-subtitle">{html.escape(subtitle)}</div>',
        unsafe_allow_html=True,
    )


def _ticket_card(ticket):
    """Render one escaped ticket card for a Kanban column."""
    priority_class = {
        "High": "badge-high",
        "Normal": "badge-normal",
        "Low": "badge-low",
    }.get(ticket.priority, "badge-normal")
    assigned = ticket.technician_id or "Unassigned"
    st.markdown(
        f'<div class="ticket-card">'
        f'<div class="ticket-id">{html.escape(ticket.ticket_id)}</div>'
        f'<div class="ticket-title">{html.escape(ticket.device_type)} · '
        f'{html.escape(ticket.issue_type)}</div>'
        f'<div class="ticket-meta">{html.escape(ticket.description)}</div>'
        f'<div class="ticket-meta">Technician: {html.escape(assigned)}</div>'
        f'<span class="badge {priority_class}">{html.escape(ticket.priority)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _status_label(status):
    """Map persisted lifecycle states to the labels used in the repair board."""
    return "Open" if status == "Pending" else status


def _logged_in_user():
    """Resolve the signed-in user's current persisted account record."""
    user_id = st.session_state.get("repairops_user_id")
    if not user_id:
        return None
    return next((user for user in load_users() if user.ID == user_id), None)


@st.cache_data(show_spinner=False)
def _historical_data():
    """Cache cleaned historical tickets together with their quality report."""
    if not REQUESTS_FILE.exists():
        return None
    return load_and_clean_data(return_report=True)


@st.cache_resource(max_entries=4, show_spinner=False)
def _cached_ticket_index(modified_ns, file_size):
    """Build a read-only hash index once per persisted live-ticket file version."""
    return build_ticket_index(load_tickets())


def _ticket_index():
    """Return the cached O(1) ticket lookup index for the current JSON version."""
    file_state = TICKETS_FILE.stat()
    return _cached_ticket_index(file_state.st_mtime_ns, file_state.st_size)


def _auth_portal(admin_created=False):
    """Render secure client login and registration forms."""
    _hero("Welcome to RepairOps", "Sign in to follow repairs or register a client account.")
    if admin_created:
        st.success("The default manager account has been provisioned.")
    login_tab, register_tab = st.tabs(["Sign in", "Create client account"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email address")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            user = login(email, password)
            if user is None:
                st.error("Email or password is incorrect.")
            else:
                st.session_state["repairops_user_id"] = user.ID
                st.success(f"Signed in as {user.name}.")
                st.rerun()
        with st.expander("Default manager access"):
            st.code(f"{DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")
            st.caption("Change the default password after your first sign-in.")

    with st.expander("🔑 Forgot / Reset Password"):
        st.caption(
            "For account safety, password resets require manager authentication. "
            "Passwords remain stored as salted hashes."
        )
        with st.form("admin_password_reset_form"):
            manager_email = st.text_input("Manager email")
            manager_password = st.text_input(
                "Manager password", type="password"
            )
            target_account = st.text_input("User ID or email to reset")
            new_password = st.text_input(
                "New password", type="password", key="reset_new_password"
            )
            confirm_password = st.text_input(
                "Confirm new password",
                type="password",
                key="reset_confirm_password",
            )
            reset_submitted = st.form_submit_button(
                "Reset account password",
                type="primary",
            )
        if reset_submitted:
            if new_password != confirm_password:
                st.error("The new passwords do not match.")
            else:
                result = admin_reset_password(
                    manager_email,
                    manager_password,
                    target_account,
                    new_password,
                )
                if result["success"]:
                    st.success(result["message"])
                else:
                    for error in result["errors"]:
                        st.error(error)

    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email address", key="register_email")
            password = st.text_input("Password", type="password", key="register_password")
            confirmation = st.text_input(
                "Confirm password", type="password", key="register_confirmation"
            )
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            if password != confirmation:
                st.error("The passwords do not match.")
            else:
                result = register(
                    ID=f"CLIENT-{uuid.uuid4().hex[:10].upper()}",
                    name=name,
                    email=email,
                    password=password,
                    role="Client",
                )
                if result["success"]:
                    st.success("Your client account is ready. Sign in to continue.")
                else:
                    for error in result["errors"]:
                        st.error(error)
        st.caption(
            "Use at least 12 characters with uppercase, lowercase, a number, "
            "and a special character."
        )


def _client_portal(user):
    """Let a client create tickets and track only their own requests."""
    _hero("Client Portal", "Submit a repair request and follow its progress.")
    tickets = load_tickets()
    user_tickets = [ticket for ticket in tickets if ticket.client_id == user.ID]
    create_tab, track_tab = st.tabs(["New repair request", "Track a request"])

    with create_tab:
        with st.form("new_ticket_form"):
            device = st.selectbox("Device type", list(DEVICE_ISSUES))
            issue = st.selectbox("Issue category", DEVICE_ISSUES[device])
            phone = st.text_input("Mobile number", placeholder="01XXXXXXXXX")
            priority = st.selectbox("Priority", ["Normal", "High", "Low"])
            description = st.text_area(
                "Describe the issue", placeholder="Include useful symptoms or context."
            )
            submitted = st.form_submit_button("Submit repair request", type="primary")
        if submitted:
            errors = validate_ticket_request(
                device, issue, phone, description, priority
            )
            if errors:
                for error in errors:
                    st.error(error)
            else:
                ticket_id = f"L-{uuid.uuid4().hex[:10].upper()}"
                ticket = user.open_new_ticket(
                    ticket_id, device, issue, phone, description.strip(), priority
                )
                tickets.append(ticket)
                save_tickets(tickets)
                users = load_users()
                saved_client = next(item for item in users if item.ID == user.ID)
                saved_client.tickets = list(
                    dict.fromkeys([*saved_client.tickets, ticket.ticket_id])
                )
                save_users(users)
                st.success(f"Request submitted. Your ticket ID is {ticket.ticket_id}.")

    with track_tab:
        st.caption("Search by your ticket ID or the phone number on your account.")
        query = st.text_input("Ticket ID or mobile number", key="client_track_query")
        if query.strip():
            index = _ticket_index()
            matches = (
                [index.search_by_id(query)]
                if not is_valid_phone(query)
                else index.search_by_phone(query)
            )
            matches = [
                ticket
                for ticket in matches
                if ticket is not None
                and ticket.client_id == user.ID
                and (not is_valid_phone(query) or ticket.phone_number == query.strip())
            ]
            if matches:
                for ticket in matches:
                    st.info(
                        f"{ticket.ticket_id} · {_status_label(ticket.status)} · "
                        f"{ticket.device_type} / {ticket.issue_type} · {ticket.priority}"
                    )
            else:
                st.warning("No matching request was found for your account.")

        st.markdown('<div class="section-label">Your recent requests</div>', unsafe_allow_html=True)
        if not user_tickets:
            st.info("You have not submitted any repair requests yet.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Ticket ID": ticket.ticket_id,
                            "Device": ticket.device_type,
                            "Issue": ticket.issue_type,
                            "Priority": ticket.priority,
                            "Status": _status_label(ticket.status),
                            "Created": ticket.creation_time,
                        }
                        for ticket in user_tickets
                    ]
                ),
                width="stretch",
                hide_index=True,
            )


def _capture_admin_snapshot(ticket, users):
    """Capture ticket lifecycle and technician assignment state before an action."""
    return {
        "ticket": {
            "ticket_id": ticket.ticket_id,
            "status": ticket.status,
            "technician_id": ticket.technician_id,
            "repair_cost": ticket.repair_cost,
            "parts_used_num": ticket.parts_used_num,
            "resolve_time": ticket.resolve_time,
            "technician_notes": ticket.technician_notes,
        },
        "technicians": [
            {
                "technician_id": user.ID,
                "workload": user.workload,
                "is_available": user.is_available,
                "assigned_tickets": list(user.assigned_tickets),
            }
            for user in users
            if isinstance(user, Technician)
        ],
    }


def _restore_admin_snapshot(action, tickets, users):
    """Restore the ticket and technician state stored in an undo action."""
    snapshot = action["snapshot"]
    ticket_state = snapshot["ticket"]
    ticket = next(
        (item for item in tickets if item.ticket_id == ticket_state["ticket_id"]),
        None,
    )
    if ticket is None:
        raise ValueError(
            f"Ticket {ticket_state['ticket_id']} for the last action was not found."
        )

    for field in (
        "status",
        "technician_id",
        "repair_cost",
        "parts_used_num",
        "resolve_time",
        "technician_notes",
    ):
        if field in ticket_state:
            setattr(ticket, field, ticket_state[field])

    technicians_by_id = {
        user.ID: user for user in users if isinstance(user, Technician)
    }
    for technician_state in snapshot["technicians"]:
        technician = technicians_by_id.get(technician_state["technician_id"])
        if technician is None:
            continue
        technician.workload = technician_state["workload"]
        technician.is_available = technician_state["is_available"]
        technician.assigned_tickets = list(technician_state["assigned_tickets"])
    return ticket


def _admin_dashboard():
    """Render live operations KPIs, priority search, Kanban, and assignments."""
    if not isinstance(st.session_state.get("undo_stack"), UndoStack):
        st.session_state["undo_stack"] = UndoStack()
    _hero("Service Command", "Monitor incoming work, dispatch repairs, and close tickets.")
    tickets = load_tickets()
    users = load_users()
    sync_technician_workloads(users, tickets)
    index = _ticket_index()
    all_data = get_full_data(live_tickets=tickets)
    metrics = get_summary_metrics(all_data)

    search_col, active_col, revenue_col, repair_col = st.columns([2.2, 1, 1, 1])
    with search_col:
        st.markdown('<div class="section-label">Quick ticket lookup</div>', unsafe_allow_html=True)
        search = st.text_input(
            "Search by ticket ID or exact phone number",
            placeholder="e.g. L-AB12CD34 or 01XXXXXXXXX",
            label_visibility="collapsed",
            key="admin_ticket_search",
        )
    active_count = sum(
        ticket.status in {"Pending", "In Progress"} for ticket in tickets
    )
    active_col.metric("Active tickets", f"{active_count:,}")
    revenue_col.metric("Total revenue", f"${metrics['total_repair_cost']:,.0f}")
    repair_col.metric("Avg. repair hours", f"{metrics['average_repair_hours']:.1f} h")
    if search.strip():
        result = (
            index.search_by_phone(search)
            if is_valid_phone(search)
            else [index.search_by_id(search)]
        )
        result = [ticket for ticket in result if ticket is not None]
        if result:
            for ticket in result:
                st.info(
                    f"{ticket.ticket_id} · {ticket.device_type} · "
                    f"{_status_label(ticket.status)} · {ticket.phone_number}"
                )
        else:
            st.warning("No ticket matched that ID or exact phone number.")

    st.markdown("---")
    undo_col, action_info_col = st.columns([1, 3])
    with undo_col:
        undo_stack = st.session_state["undo_stack"]
        undo_available = not undo_stack.is_empty()
        if st.button(
            "↶ Restore Last Admin Action",
            disabled=not undo_available,
            width="stretch",
        ):
            last_action = undo_stack.peek()
            try:
                ticket = _restore_admin_snapshot(last_action, tickets, users)
                sync_technician_workloads(users, tickets)
                save_tickets(tickets)
                save_users(users)
            except (KeyError, TypeError, ValueError) as error:
                st.error(f"Could not undo the last action: {error}")
            else:
                undo_stack.pop()
                st.success(f"Undid: {last_action['description']}")
                st.rerun()
    with action_info_col:
        last_action = st.session_state["undo_stack"].peek()
        st.caption(
            f"{len(st.session_state['undo_stack'].history)} reversible "
            f"{'action' if len(st.session_state['undo_stack'].history) == 1 else 'actions'}"
            + (
                f" · Latest: {last_action['description']}"
                if last_action is not None
                else ""
            )
        )

    st.markdown("---")
    board_col, staff_col = st.columns([2.3, 1])
    with board_col:
        st.markdown('<div class="section-label">Repair board · priority ordered</div>', unsafe_allow_html=True)
        prioritized = get_prioritized_tickets(tickets)
        columns = st.columns(3)
        for column, status in zip(columns, ("Pending", "In Progress", "Completed")):
            with column:
                matching = [ticket for ticket in prioritized if ticket.status == status]
                st.subheader(f"{_status_label(status)} · {len(matching)}")
                if not matching:
                    st.caption("No tickets in this lane.")
                for ticket in matching:
                    _ticket_card(ticket)

    with staff_col:
        st.markdown('<div class="section-label">Technician availability</div>', unsafe_allow_html=True)
        technicians = [user for user in users if isinstance(user, Technician)]
        if technicians:
            for technician in technicians:
                active_ids = technician.assigned_tickets
                status = "Active" if active_ids else "Idle"
                st.markdown(
                    f"**{html.escape(technician.name)}** · {status}  \n"
                    f"{html.escape(technician.specialization)} · "
                    f"{len(active_ids)}/{MAX_TECHNICIAN_WORKLOAD} active"
                )
                if active_ids:
                    st.caption("Assignments: " + ", ".join(active_ids))
                st.divider()
        else:
            st.info("Add a technician account below to enable dispatch.")

        with st.expander("Add technician"):
            with st.form("add_technician_form"):
                tech_name = st.text_input("Full name", key="tech_name")
                tech_email = st.text_input("Email", key="tech_email")
                specialization = st.selectbox(
                    "Specialization", list(DEVICE_ISSUES), key="tech_specialization"
                )
                tech_password = st.text_input(
                    "Temporary password", type="password", key="tech_password"
                )
                add_tech = st.form_submit_button("Create technician")
            if add_tech:
                result = register(
                    ID=f"TECH-{uuid.uuid4().hex[:8].upper()}",
                    name=tech_name,
                    email=tech_email,
                    password=tech_password,
                    role="Technician",
                    specialization=specialization,
                )
                if result["success"]:
                    st.success("Technician account created.")
                    st.rerun()
                else:
                    for error in result["errors"]:
                        st.error(error)

    st.markdown("---")
    action_col, complete_col = st.columns(2)
    with action_col:
        st.markdown(
            '<div class="section-label">Manual Ticket Assignment</div>',
            unsafe_allow_html=True,
        )
        pending_for_manual = [
            ticket for ticket in tickets if ticket.status == "Pending"
        ]
        available_technicians = [
            user for user in users if isinstance(user, Technician)
        ]
        if pending_for_manual and available_technicians:
            with st.form("manual_ticket_assignment_form"):
                selected_manual_ticket_id = st.selectbox(
                    "Pending ticket",
                    [ticket.ticket_id for ticket in pending_for_manual],
                )
                selected_technician_id = st.selectbox(
                    "Technician",
                    [user.ID for user in available_technicians],
                    format_func=lambda technician_id: next(
                        (
                            f"{user.name} · {user.specialization} "
                            f"({user.workload}/{MAX_TECHNICIAN_WORKLOAD})"
                            for user in available_technicians
                            if user.ID == technician_id
                        ),
                        technician_id,
                    ),
                )
                manual_assign = st.form_submit_button(
                    "Assign Manually",
                    type="primary",
                )
            if manual_assign:
                ticket = next(
                    (
                        item
                        for item in tickets
                        if item.ticket_id == selected_manual_ticket_id
                    ),
                    None,
                )
                technician = next(
                    (
                        item
                        for item in available_technicians
                        if item.ID == selected_technician_id
                    ),
                    None,
                )
                if ticket is None or technician is None:
                    st.error("The selected ticket or technician is no longer available.")
                else:
                    st.session_state["undo_stack"].push(
                        action_type="manual_assignment",
                        description=(
                            f"Manually assigned {ticket.ticket_id} "
                            f"to {technician.name}"
                        ),
                        snapshot=_capture_admin_snapshot(ticket, users),
                    )
                    try:
                        ticket.assign_technician(technician.ID)
                        sync_technician_workloads(users, tickets)
                        save_tickets(tickets)
                        save_users(users)
                    except (OSError, TypeError, ValueError) as error:
                        _restore_admin_snapshot(
                            st.session_state["undo_stack"].peek(),
                            tickets,
                            users,
                        )
                        st.session_state["undo_stack"].pop()
                        st.error(f"Could not assign the ticket: {error}")
                    else:
                        st.success(
                            f"Ticket {ticket.ticket_id} assigned to "
                            f"{technician.name}."
                        )
                        st.rerun()
        elif not pending_for_manual:
            st.caption("There are no pending tickets to assign.")
        else:
            st.caption("Create a technician account before assigning tickets.")

        st.markdown(
            '<div class="section-label">Priority dispatch</div>',
            unsafe_allow_html=True,
        )
        assignable = [
            ticket
            for ticket in prioritized
            if ticket.status == "Pending"
            and any(
                isinstance(user, Technician)
                and user.is_available
                and user.specialization == ticket.device_type
                for user in users
            )
        ]
        if assignable:
            if st.button("Assign next highest-priority ticket", type="primary"):
                ticket_to_assign = assignable[0]
                st.session_state["undo_stack"].push(
                    action_type="assignment",
                    description=f"Assigned ticket {ticket_to_assign.ticket_id}",
                    snapshot=_capture_admin_snapshot(ticket_to_assign, users),
                )
                selected = process_next_ticket(tickets, users)
                if selected is None:
                    st.session_state["undo_stack"].pop()
                    st.error("No pending ticket has a matching available technician.")
                else:
                    st.success(f"{selected.ticket_id} assigned to a technician.")
                    st.rerun()
        else:
            st.caption("No open ticket currently has an available matching technician.")

    with complete_col:
        st.markdown('<div class="section-label">Complete repair</div>', unsafe_allow_html=True)
        active_tickets = [ticket for ticket in tickets if ticket.status == "In Progress"]
        if active_tickets:
            with st.form("complete_ticket_form"):
                selected_id = st.selectbox(
                    "In-progress ticket",
                    [ticket.ticket_id for ticket in active_tickets],
                )
                repair_cost = st.number_input(
                    "Repair revenue ($)", min_value=0.0, step=10.0
                )
                parts_used = st.number_input(
                    "Parts used", min_value=0, max_value=4, step=1
                )
                complete = st.form_submit_button("Mark completed", type="primary")
            if complete:
                ticket = next(
                    ticket for ticket in tickets if ticket.ticket_id == selected_id
                )
                st.session_state["undo_stack"].push(
                    action_type="completion",
                    description=f"Completed ticket {ticket.ticket_id}",
                    snapshot=_capture_admin_snapshot(ticket, users),
                )
                try:
                    ticket.complete_ticket(repair_cost, parts_used)
                except ValueError as error:
                    st.session_state["undo_stack"].pop()
                    st.error(str(error))
                    return
                sync_technician_workloads(users, tickets)
                save_tickets(tickets)
                save_users(users)
                st.success(f"{ticket.ticket_id} marked as completed.")
                st.rerun()
        else:
            st.caption("There are no in-progress repairs to close.")


def _analytics_page():
    """Render interactive status, volume, and technician performance reports."""
    _hero("Analytics & Reports", "Explore historical and live repair performance.")
    historical_result = _historical_data()
    if historical_result is None:
        historical, cleaning_report = None, {}
    else:
        historical, cleaning_report = historical_result
    live_tickets = load_tickets()
    data = get_full_data(
        live_tickets=live_tickets,
        include_historical=historical is not None,
        historical_data=historical,
    )
    if data.empty:
        st.info("No historical or live ticket data is available.")
        return

    start, end = data["creation_time"].min().date(), data["creation_time"].max().date()
    date_range = st.date_input(
        "Creation date range",
        value=(start, end),
        min_value=start,
        max_value=end,
    )
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    priorities = filter_col1.multiselect(
        "Priority", ["High", "Normal", "Low"], default=["High", "Normal", "Low"]
    )
    devices = filter_col2.multiselect(
        "Device", sorted(data["device_type"].dropna().unique()), default=None
    )
    statuses = filter_col3.multiselect(
        "Status",
        ["Pending", "In Progress", "Completed"],
        default=["Pending", "In Progress", "Completed"],
    )
    start_date, end_date = date_range if len(date_range) == 2 else (start, end)
    filtered = filter_tickets(
        data,
        start_date=start_date,
        end_date=end_date,
        priorities=priorities,
        device_types=devices or None,
        statuses=statuses,
    )
    metrics = get_summary_metrics(filtered)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Tickets in view", f"{metrics['total_tickets']:,}")
    metric_cols[1].metric("Resolved rate", f"{metrics['completion_rate_pct']:.1f}%")
    metric_cols[2].metric("Avg. repair time", f"{metrics['average_repair_hours']:.1f} h")
    metric_cols[3].metric("Repair revenue", f"${metrics['total_repair_cost']:,.0f}")
    csv_data = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Export Cleaned Report (CSV)",
        data=csv_data,
        file_name="repairops_analytics.csv",
        mime="text/csv",
    )
    with st.expander("Historical data quality and cleaning details"):
        if not cleaning_report:
            st.info("No historical CSV data is available for cleaning.")
        else:
            quality_metrics = st.columns(4)
            quality_metrics[0].metric("Source rows", cleaning_report["rows_raw"])
            quality_metrics[1].metric("Clean rows", cleaning_report["rows_clean"])
            quality_metrics[2].metric(
                "Duplicate rows removed",
                cleaning_report["duplicate_rows_removed"],
            )
            quality_metrics[3].metric(
                "Rows without valid dates removed",
                cleaning_report["rows_without_valid_creation_time_removed"],
            )
            quality_labels = {
                "rows_without_id_removed": "Rows without a ticket ID removed",
                "device_type_fixed": "Device categories normalized",
                "issue_type_fixed": "Issue categories normalized",
                "issues_not_matching_device_set_unknown": (
                    "Device and issue mismatches set to Unknown"
                ),
                "priority_fixed": "Priority values normalized",
                "status_fixed": "Status values normalized",
                "negative_costs_set_missing": "Negative repair costs cleared",
                "invalid_parts_counts_set_missing": "Invalid parts counts cleared",
                "negative_durations_set_missing": "Negative repair durations cleared",
                "invalid_phone_numbers": "Invalid phone numbers flagged",
                "completed_without_repair_cost": (
                    "Completed tickets missing repair cost"
                ),
                "completed_without_resolve_time": (
                    "Completed tickets missing resolution time"
                ),
            }
            quality_rows = [
                {
                    "Cleaning check": label,
                    "Rows affected": cleaning_report[key],
                }
                for key, label in quality_labels.items()
                if key in cleaning_report
            ]
            st.dataframe(
                pd.DataFrame(quality_rows),
                width="stretch",
                hide_index=True,
            )

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown('<div class="section-label">Repair status overview</div>', unsafe_allow_html=True)
        status_counts = filtered["status"].value_counts().reindex(
            ["Pending", "In Progress", "Completed"], fill_value=0
        )
        donut = go.Figure(
            data=[
                go.Pie(
                    labels=["Open", "In Progress", "Completed"],
                    values=status_counts.values,
                    hole=0.68,
                    marker={"colors": ["#FBBF24", "#7DD3FC", "#34D399"]},
                    textinfo="label+percent",
                    hovertemplate="%{label}: %{value} tickets<extra></extra>",
                )
            ]
        )
        donut.update_layout(
            height=340,
            margin={"l": 10, "r": 10, "t": 15, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#D8E8F5"},
            showlegend=False,
        )
        st.plotly_chart(donut, width="stretch")

    with chart_right:
        st.markdown('<div class="section-label">Repair volume trend</div>', unsafe_allow_html=True)
        frequency = st.selectbox(
            "Trend interval", ["Daily", "Weekly", "Monthly", "Quarterly"], index=2
        )
        freq_code = {"Daily": "D", "Weekly": "W", "Monthly": "M", "Quarterly": "Q"}[
            frequency
        ]
        volume = get_tickets_over_time(filtered, freq=freq_code)
        area = px.area(
            volume,
            x="period",
            y="ticket_count",
            markers=True,
            color_discrete_sequence=["#7DD3FC"],
        )
        area.update_traces(fillcolor="rgba(125,211,252,.16)", line={"width": 3})
        area.update_layout(
            height=340,
            margin={"l": 10, "r": 10, "t": 15, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#D8E8F5"},
            xaxis_title=None,
            yaxis_title="Tickets",
            hovermode="x unified",
        )
        area.update_xaxes(gridcolor="rgba(148,200,230,.16)")
        area.update_yaxes(gridcolor="rgba(148,200,230,.16)")
        st.plotly_chart(area, width="stretch")

    st.markdown('<div class="section-label">Technician workload & performance</div>', unsafe_allow_html=True)
    technicians = get_technician_performance(filtered)
    if technicians.empty:
        st.info("No assigned tickets are present in this filter.")
    else:
        technician_report = technicians.rename(
            columns={
                "technician_id": "Technician ID",
                "name": "Technician",
                "specialization": "Device specialty",
                "assigned_tickets": "Assigned tickets",
                "completed_tickets": "Completed tickets",
                "in_progress_tickets": "In-progress tickets",
                "completion_rate_pct": "Completion rate",
                "average_repair_hours": "Average repair hours",
                "total_repair_cost": "Total repair revenue",
            }
        )
        st.dataframe(
            technician_report,
            width="stretch",
            hide_index=True,
            column_config={
                "Completion rate": st.column_config.ProgressColumn(
                    "Completion rate", min_value=0, max_value=100, format="%.1f%%"
                ),
                "Average repair hours": st.column_config.NumberColumn(
                    "Average repair hours", format="%.2f h"
                ),
                "Total repair revenue": st.column_config.NumberColumn(
                    "Total repair revenue", format="$%.2f"
                ),
            },
        )


def _technician_portal(user):
    """Render a technician workbench for assigned jobs, self-assignment, and history."""
    _hero(
        "Technician Workbench",
        "Manage assigned repair jobs, claim specialized pending tickets, and record completed services.",
    )
    tickets = load_tickets()
    users = load_users()
    technician = next(
        (
            account
            for account in users
            if isinstance(account, Technician) and account.ID == user.ID
        ),
        None,
    )
    if technician is None:
        st.error("The technician account could not be loaded. Please sign in again.")
        return

    sync_technician_workloads(users, tickets)
    completed_tickets = [
        ticket
        for ticket in tickets
        if ticket.technician_id == technician.ID and ticket.status == "Completed"
    ]
    active_tickets = [
        ticket
        for ticket in tickets
        if ticket.technician_id == technician.ID and ticket.status == "In Progress"
    ]
    metrics = st.columns(4)
    metrics[0].metric(
        "Active Assignments",
        f"{len(technician.assigned_tickets)} / {MAX_TECHNICIAN_WORKLOAD}",
    )
    metrics[1].metric("Completed Repairs", f"{len(completed_tickets):,}")
    metrics[2].metric("Specialization", technician.specialization)
    metrics[3].metric(
        "Status",
        "Available" if technician.is_available else "At Capacity",
    )

    st.markdown(
        '<div class="section-label">Active assigned repairs · In Progress</div>',
        unsafe_allow_html=True,
    )
    if not active_tickets:
        st.info("You have no active repair assignments.")
    for ticket in active_tickets:
        with st.container():
            st.markdown(
                f'<div class="ticket-card">'
                f'<div class="ticket-id">{html.escape(ticket.ticket_id)}</div>'
                f'<div class="ticket-title">{html.escape(ticket.device_type)} · '
                f'{html.escape(ticket.issue_type)}</div>'
                f'<div class="ticket-meta">Priority: {html.escape(ticket.priority)}'
                f' · Client: {html.escape(ticket.client_id)}</div>'
                f'<div class="ticket-meta">Contact: {html.escape(ticket.phone_number)}</div>'
                f'<div class="ticket-meta">{html.escape(ticket.description or "No description provided.")}</div>'
                f'<div class="ticket-meta">Created: {html.escape(str(ticket.creation_time))}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            with st.form(f"technician_complete_{ticket.ticket_id}"):
                repair_cost = st.number_input(
                    "Repair Revenue ($)",
                    min_value=0.0,
                    step=10.0,
                    key=f"technician_revenue_{ticket.ticket_id}",
                )
                parts_used_num = st.number_input(
                    "Parts Used",
                    min_value=0,
                    max_value=MAX_PARTS_PER_TICKET,
                    step=1,
                    key=f"technician_parts_{ticket.ticket_id}",
                )
                notes = st.text_area(
                    "Technician Diagnosis / Notes",
                    value=ticket.technician_notes or "",
                    key=f"technician_notes_{ticket.ticket_id}",
                )
                submitted = st.form_submit_button(
                    "Mark Ticket as Completed",
                    type="primary",
                )
            if submitted:
                try:
                    ticket.complete_ticket(repair_cost, parts_used_num)
                    ticket.technician_notes = notes.strip() or None
                    sync_technician_workloads(users, tickets)
                    save_tickets(tickets)
                    save_users(users)
                except (OSError, TypeError, ValueError) as error:
                    st.error(f"Could not complete ticket {ticket.ticket_id}: {error}")
                else:
                    st.success(f"Ticket {ticket.ticket_id} marked as completed.")
                    st.rerun()

    st.markdown(
        '<div class="section-label">Self-assignment · Specialized pending tickets</div>',
        unsafe_allow_html=True,
    )
    queue = TicketQueue()
    for ticket in tickets:
        if (
            ticket.status == "Pending"
            and ticket.device_type == technician.specialization
        ):
            queue.add_ticket(ticket)
    pending_tickets = queue.get_prioritized_tickets()
    if len(technician.assigned_tickets) >= MAX_TECHNICIAN_WORKLOAD:
        st.caption(
            f"You have reached the maximum capacity ({MAX_TECHNICIAN_WORKLOAD} active tickets). "
            "Complete an active ticket to claim new work."
        )
    elif not technician.is_available:
        st.caption("You are currently unavailable to claim additional work.")
    elif not pending_tickets:
        st.info("There are no pending tickets for your specialization.")
    else:
        for ticket in pending_tickets:
            with st.container():
                st.markdown(
                    f'<div class="ticket-card">'
                    f'<div class="ticket-id">{html.escape(ticket.ticket_id)}</div>'
                    f'<div class="ticket-title">{html.escape(ticket.device_type)} · '
                    f'{html.escape(ticket.issue_type)}</div>'
                    f'<div class="ticket-meta">Priority: {html.escape(ticket.priority)}'
                    f' · Created: {html.escape(str(ticket.creation_time))}</div>'
                    f'<div class="ticket-meta">{html.escape(ticket.description or "No description provided.")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Accept & Claim Ticket",
                    key=f"claim_ticket_{ticket.ticket_id}",
                    type="primary",
                ):
                    try:
                        if (
                            ticket.status != "Pending"
                            or ticket.device_type != technician.specialization
                        ):
                            raise ValueError(
                                "This ticket is no longer available for your specialization."
                            )
                        if (
                            not technician.is_available
                            or len(technician.assigned_tickets) >= MAX_TECHNICIAN_WORKLOAD
                        ):
                            raise ValueError(
                                "You cannot claim more work while unavailable or at capacity."
                            )
                        ticket.assign_technician(technician.ID)
                        sync_technician_workloads(users, tickets)
                        save_tickets(tickets)
                        save_users(users)
                    except (OSError, TypeError, ValueError) as error:
                        st.error(f"Could not claim ticket {ticket.ticket_id}: {error}")
                    else:
                        st.success(f"Ticket {ticket.ticket_id} assigned to you.")
                        st.rerun()

    st.markdown(
        '<div class="section-label">Repair history & ratings</div>',
        unsafe_allow_html=True,
    )
    if not completed_tickets:
        st.info("Completed repairs will appear here.")
    else:
        history = pd.DataFrame(
            [
                {
                    "Ticket ID": ticket.ticket_id,
                    "Device": ticket.device_type,
                    "Issue": ticket.issue_type,
                    "Created": ticket.creation_time,
                    "Resolved": ticket.resolve_time,
                    "Cost ($)": ticket.repair_cost,
                    "Parts": ticket.parts_used_num,
                    "Rating": ticket.rating,
                    "Feedback": ticket.feedback,
                }
                for ticket in sorted(
                    completed_tickets,
                    key=lambda item: str(item.resolve_time or ""),
                    reverse=True,
                )
            ]
        )
        st.dataframe(history, width="stretch", hide_index=True)


def _branch_map_page(user=None):
    """Show configured branch coordinates and let managers maintain real locations."""
    _hero("Branch & Project Map", "Map verified operational locations and branch details.")
    branches = load_branches()
    if branches:
        map_data = pd.DataFrame(
            [
                {
                    "latitude": branch["latitude"],
                    "longitude": branch["longitude"],
                    "name": html.escape(branch["name"]),
                    "city": html.escape(branch["city"]),
                    "address": html.escape(branch["address"]),
                    "project": html.escape(branch.get("project", "")),
                    "status": html.escape(branch.get("status", "Active")),
                }
                for branch in branches
            ]
        )
        map_view = pdk.ViewState(
            latitude=float(map_data["latitude"].mean()),
            longitude=float(map_data["longitude"].mean()),
            zoom=5,
            pitch=25,
        )
        map_layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_data,
            get_position="[longitude, latitude]",
            get_fill_color="[0, 210, 255, 210]",
            get_line_color="[56, 189, 248, 255]",
            get_radius=100,
            radius_min_pixels=7,
            radius_max_pixels=22,
            line_width_min_pixels=2,
            pickable=True,
            auto_highlight=True,
        )
        st.pydeck_chart(
            pdk.Deck(
                map_style=None,
                initial_view_state=map_view,
                layers=[map_layer],
                tooltip={
                    "html": (
                        "<b>{name}</b><br/>"
                        "{address}<br/>"
                        "{city} · {status}<br/>"
                        "{project}"
                    ),
                    "style": {
                        "backgroundColor": "#1E293B",
                        "color": "#E2E8F0",
                    },
                },
            ),
            width="stretch",
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Branch": branch["name"],
                        "City": branch["city"],
                        "Address": branch["address"],
                        "Project": branch.get("project", ""),
                        "Operational status": branch.get("status", "Active"),
                    }
                    for branch in branches
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info(
            "No verified branch locations are configured. A manager can add known "
            "coordinates below; no locations are invented or displayed by default."
        )

    if user is not None and user.role == "Manager":
        with st.expander("Add a verified location", expanded=not branches):
            with st.form("branch_form"):
                name = st.text_input("Branch or project name")
                city = st.text_input("City")
                address = st.text_input("Street address")
                project = st.text_input("Operational details")
                status = st.selectbox("Status", ["Active", "Planned", "Under maintenance"])
                latitude_text = st.text_input(
                    "Latitude", placeholder="Verified decimal degrees, -90 to 90"
                )
                longitude_text = st.text_input(
                    "Longitude", placeholder="Verified decimal degrees, -180 to 180"
                )
                submitted = st.form_submit_button("Save location", type="primary")
            if submitted:
                if not name.strip() or not city.strip() or not address.strip():
                    st.error("Branch name, city, and street address are required.")
                else:
                    try:
                        latitude = float(latitude_text)
                        longitude = float(longitude_text)
                    except ValueError:
                        st.error("Enter valid verified latitude and longitude values.")
                    else:
                        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                            st.error("Coordinates must be within valid latitude and longitude ranges.")
                            return
                        branches.append(
                            {
                                "name": name.strip(),
                                "city": city.strip(),
                                "address": address.strip(),
                                "project": project.strip(),
                                "status": status,
                                "latitude": latitude,
                                "longitude": longitude,
                            }
                        )
                        save_branches(branches)
                        st.success("Verified location saved.")
                        st.rerun()


def _restore_previous_workspace(pages):
    """Restore the newest page in the current role's navigation history."""
    history = [
        page
        for page in st.session_state.get("page_history", [])
        if page in pages
    ]
    if history:
        previous_page = history.pop()
        st.session_state["page_history"] = history
        st.session_state["current_workspace"] = previous_page
        st.session_state["workspace_selection"] = previous_page
        st.rerun()


def _workspace_navigation(pages, label):
    """Render role-scoped navigation with a session-local previous-page action."""
    pages = list(pages)
    history = [
        page
        for page in st.session_state.get("page_history", [])
        if page in pages
    ]
    current_page = st.session_state.get("current_workspace")
    if current_page not in pages:
        current_page = pages[0]
        history = []
        st.session_state["current_workspace"] = current_page
        st.session_state["workspace_selection"] = current_page
    elif st.session_state.get("workspace_selection") not in pages:
        st.session_state["workspace_selection"] = current_page
    st.session_state["page_history"] = history

    selected_page = st.sidebar.radio(
        label,
        pages,
        label_visibility="collapsed",
        key="workspace_selection",
    )
    if selected_page != current_page:
        history.append(current_page)
        st.session_state["page_history"] = history
        st.session_state["current_workspace"] = selected_page
    st.sidebar.button(
        "↩️ Back to Previous Page",
        disabled=not history,
        width="stretch",
        key="workspace_back_button",
        on_click=_restore_previous_workspace,
        args=(tuple(pages),),
    )
    return selected_page


def _account_sidebar(user):
    """Render signed-in identity, navigation, password change, and logout controls."""
    if user.role == "Manager":
        pages = [
            "Admin Dashboard",
            "Analytics & Reports",
            "Branch & Project Map",
        ]
    elif user.role == "Client":
        pages = ["Client Portal", "Branch & Project Map"]
    elif user.role == "Technician":
        pages = ["Technician Portal", "Branch & Project Map"]
    else:
        pages = ["Branch & Project Map"]
    with st.sidebar:
        st.markdown("### REPAIROPS")
        st.caption("SERVICE COMMAND · 01")
        st.markdown("---")
        st.markdown(f"**{html.escape(user.name)}**")
        st.caption(f"{user.role} · {html.escape(user.email)}")
        page = _workspace_navigation(pages, "Workspace")
        with st.expander("Change password"):
            with st.form("change_password_form"):
                current = st.text_input("Current password", type="password")
                new = st.text_input("New password", type="password")
                confirmation = st.text_input("Confirm new password", type="password")
                update = st.form_submit_button("Update password")
            if update:
                if new != confirmation:
                    st.error("The new passwords do not match.")
                else:
                    result = change_password(user.ID, current, new)
                    if result["success"]:
                        st.success(result["message"])
                    else:
                        for error in result["errors"]:
                            st.error(error)
        st.markdown("---")
        if st.button("Sign out", width="stretch"):
            st.session_state.pop("repairops_user_id", None)
            st.session_state["current_workspace"] = None
            st.session_state["page_history"] = []
            st.rerun()
    return page


def main():
    """Bootstrap persistence and route the session to its authorized workspace."""
    if not isinstance(st.session_state.get("undo_stack"), UndoStack):
        st.session_state["undo_stack"] = UndoStack()
    _apply_theme()
    admin_created = bootstrap_system()
    user = _logged_in_user()
    if user is None:
        st.sidebar.markdown("### REPAIROPS")
        st.sidebar.caption("SERVICE COMMAND · 01")
        st.sidebar.markdown("---")
        page = _workspace_navigation(
            ["Auth Portal", "Our Branches"],
            "Navigation",
        )
    else:
        page = _account_sidebar(user)

    if page == "Auth Portal":
        _auth_portal(admin_created)
    elif page == "Our Branches" and user is None:
        _branch_map_page(user=None)
    elif page == "Client Portal" and user is not None and user.role == "Client":
        _client_portal(user)
    elif page == "Technician Portal" and user is not None and user.role == "Technician":
        _technician_portal(user)
    elif page == "Admin Dashboard" and user is not None and user.role == "Manager":
        _admin_dashboard()
    elif page == "Analytics & Reports" and user is not None and user.role == "Manager":
        _analytics_page()
    elif page == "Branch & Project Map" and user is not None:
        _branch_map_page(user)
    else:
        st.error("This workspace is not available for the current account.")


main()
