"""Five-page Streamlit application for RepairOps ticket operations."""

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
)
from models import DEVICE_ISSUES, MAX_TECHNICIAN_WORKLOAD, Technician
from validation import is_valid_phone, validate_ticket_request


st.set_page_config(
    page_title="RepairOps | Service Command",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _apply_theme():
    """Apply the shared dark cyber dashboard theme to all application pages."""
    st.markdown(
        """
        <style>
        :root { color-scheme: dark; }
        .stApp { background: #0f172a; color: #e2e8f0; }
        [data-testid="stHeader"] { background: rgba(15, 23, 42, .88); }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #111c31 0%, #0b1220 100%);
            border-right: 1px solid rgba(148, 163, 184, .14);
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #cbd5e1; }
        h1, h2, h3 { color: #f8fafc; letter-spacing: -.025em; }
        div[data-testid="stMetric"] {
            background: linear-gradient(145deg, #1e293b, #192437);
            border: 1px solid rgba(148, 163, 184, .13);
            border-radius: 16px;
            padding: 18px 20px;
            box-shadow: 0 12px 28px rgba(0, 0, 0, .14);
        }
        div[data-testid="stMetricLabel"] { color: #94a3b8; }
        div[data-testid="stMetricValue"] { color: #f8fafc; }
        div[data-testid="stForm"], div[data-testid="stExpander"] {
            border-color: rgba(148, 163, 184, .18);
            border-radius: 14px;
        }
        .hero-kicker { color: #38bdf8; font-size: .78rem; font-weight: 750;
            letter-spacing: .17em; text-transform: uppercase; }
        .hero-title { color: #f8fafc; font-size: 2.1rem; font-weight: 780;
            letter-spacing: -.045em; margin: .18rem 0 .25rem; }
        .hero-subtitle { color: #94a3b8; margin: 0 0 1.2rem; }
        .ticket-card {
            background: linear-gradient(145deg, #1e293b, #172235);
            border: 1px solid rgba(148, 163, 184, .15);
            border-radius: 14px; padding: 15px; margin: 0 0 12px;
            box-shadow: 0 8px 18px rgba(0,0,0,.12);
        }
        .ticket-id { color: #38bdf8; font-size: .78rem; font-weight: 750; }
        .ticket-title { color: #f8fafc; font-weight: 700; margin: 5px 0; }
        .ticket-meta { color: #a8b6ca; font-size: .86rem; line-height: 1.6; }
        .badge { display: inline-block; padding: 3px 9px; margin-top: 8px;
            border-radius: 999px; font-size: .72rem; font-weight: 700; }
        .badge-high { color: #fecaca; background: rgba(239,68,68,.16); }
        .badge-normal { color: #bae6fd; background: rgba(14,165,233,.16); }
        .badge-low { color: #bbf7d0; background: rgba(34,197,94,.15); }
        .section-label { color: #7dd3fc; font-size: .77rem; font-weight: 750;
            letter-spacing: .12em; text-transform: uppercase; margin: .4rem 0 .8rem; }
        div.stButton > button[kind="primary"] {
            background: #0284c7; border: 1px solid #38bdf8; border-radius: 10px;
        }
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
    """Cache the cleaned historical CSV for analytics page reruns."""
    if not REQUESTS_FILE.exists():
        return None
    return load_and_clean_data()


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


def _admin_dashboard():
    """Render live operations KPIs, priority search, Kanban, and assignments."""
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
        st.markdown('<div class="section-label">Priority dispatch</div>', unsafe_allow_html=True)
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
                selected = process_next_ticket(tickets, users)
                if selected is None:
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
                ticket.complete_ticket(repair_cost, parts_used)
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
    historical = _historical_data()
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
                    marker={"colors": ["#f97316", "#38bdf8", "#22c55e"]},
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
            font={"color": "#cbd5e1"},
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
            color_discrete_sequence=["#38bdf8"],
        )
        area.update_traces(fillcolor="rgba(56,189,248,.16)", line={"width": 3})
        area.update_layout(
            height=340,
            margin={"l": 10, "r": 10, "t": 15, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#cbd5e1"},
            xaxis_title=None,
            yaxis_title="Tickets",
            hovermode="x unified",
        )
        area.update_xaxes(gridcolor="rgba(148,163,184,.12)")
        area.update_yaxes(gridcolor="rgba(148,163,184,.12)")
        st.plotly_chart(area, width="stretch")

    st.markdown('<div class="section-label">Technician workload & performance</div>', unsafe_allow_html=True)
    technicians = get_technician_performance(filtered)
    if technicians.empty:
        st.info("No assigned tickets are present in this filter.")
    else:
        st.dataframe(
            technicians,
            width="stretch",
            hide_index=True,
            column_config={
                "completion_rate_pct": st.column_config.ProgressColumn(
                    "Completion rate", min_value=0, max_value=100, format="%.1f%%"
                )
            },
        )


def _branch_map_page(user):
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

    if user.role == "Manager":
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


def _account_sidebar(user):
    """Render signed-in identity, navigation, password change, and logout controls."""
    st.markdown("### REPAIROPS")
    st.caption("SERVICE COMMAND · 01")
    st.markdown("---")
    st.markdown(f"**{html.escape(user.name)}**")
    st.caption(f"{user.role} · {html.escape(user.email)}")
    if user.role == "Manager":
        pages = [
            "Admin Dashboard",
            "Analytics & Reports",
            "Branch & Project Map",
        ]
    elif user.role == "Client":
        pages = ["Client Portal", "Branch & Project Map"]
    else:
        pages = ["Branch & Project Map"]
    page = st.radio("Workspace", pages, label_visibility="collapsed")
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
        st.rerun()
    return page


def main():
    """Bootstrap persistence and route the session to its authorized workspace."""
    _apply_theme()
    admin_created = bootstrap_system()
    user = _logged_in_user()
    if user is None:
        st.sidebar.markdown("### REPAIROPS")
        st.sidebar.caption("SERVICE COMMAND · 01")
        page = "Auth Portal"
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Five connected workspaces**")
        st.sidebar.caption("Authentication · Client service · Admin operations")
        st.sidebar.caption("Analytics · Branch locations")
    else:
        page = _account_sidebar(user)

    if page == "Auth Portal":
        _auth_portal(admin_created)
    elif page == "Client Portal" and user is not None and user.role == "Client":
        _client_portal(user)
    elif page == "Admin Dashboard" and user is not None and user.role == "Manager":
        _admin_dashboard()
    elif page == "Analytics & Reports" and user is not None and user.role == "Manager":
        _analytics_page()
    elif page == "Branch & Project Map" and user is not None:
        _branch_map_page(user)
    else:
        st.error("This workspace is not available for the current account.")


main()
