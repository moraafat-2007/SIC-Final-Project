# RepairOps

RepairOps is a role-based repair operations app built with Streamlit. It
combines client ticket intake, technician work management, priority-based
dispatch, a live repair board, historical reporting, and a map of configured
branch locations.

## Run the application

Install the runtime dependencies and launch Streamlit from the project folder:

```powershell
python -m pip install streamlit pandas plotly pydeck
streamlit run app.py
```

On first launch, RepairOps provisions the default manager account:

- Email: `admin@repairops.com`
- Password: `admin123`

Change the default password after signing in. Newly registered accounts require
a 12-character password with uppercase and lowercase letters, a number, and a
special character. Passwords are stored as salted PBKDF2-SHA256 hashes.

Demo client account:

- Email: `client1@repairops.com`
- Password: `client123`

Demo technician accounts:

- Laptop — `tech1@repairops.com` / `tech123`
- Printer — `tech2@repairops.com` / `tech123`
- Phone — `tech3@repairops.com` / `tech123`

If a user, ticket, or branch JSON store is missing, empty, or invalid, the app
initializes valid demo records. Invalid files are preserved with a
`.corrupt-<timestamp>-<id>` suffix before recovery. Demo passwords above are
provided for local demonstration; `users.json` stores salted PBKDF2-SHA256
hashes rather than readable plaintext passwords. The Auth Portal's password
reset flow requires manager authentication and enforces password validation.

## Workspaces

1. **Auth Portal** — manager sign-in and client registration.
2. **Client Portal** — submit device-specific tickets and securely track requests.
3. **Admin Dashboard** — priority search, KPIs, Kanban repair board, technician
   availability, priority dispatch, manual ticket assignment, and repair completion.
4. **Analytics & Reports** — interactive status and volume charts, filters, and
   technician performance tables.
5. **Technician Portal** — review assigned jobs, claim matching pending tickets,
   record repair costs, parts, and diagnostic notes, and review completed work.
6. **Branch & Project Map** — map and operational details for configured locations.

## System architecture

- `app.py` provides role-based navigation, Streamlit pages, and dashboard actions.
- `models.py` defines ticket and account models, device/issue catalogs, and
  lifecycle validation.
- `data_manager.py` owns JSON persistence, authentication, password hashing,
  ticket indexing, priority dispatch, technician workload synchronization, and
  historical-data cleaning and analytics.
- `validation.py` centralizes email, phone, registration, password, and
  ticket-request validation.
- `users.json`, `tickets.json`, and `branches.json` persist operational data;
  CSV files provide historical reporting inputs.

## Navigation and reporting

- A session-local previous-page control is available throughout the navigation
  flow; managers can also undo their latest ticket assignment or completion.
- Managers can use automatic priority dispatch, which selects an available
  technician whose specialization matches the ticket, or manually assign any
  pending ticket to a selected technician.
- Technicians can review jobs matching their device specialization, claim
  priority-ordered pending tickets while below the three-ticket capacity, and
  complete active repairs with revenue, parts, and diagnosis notes.
- Technician repair history includes resolution details, ratings, and feedback
  when those values are available.
- Analytics reports show readable technician headings, export filtered results
  as CSV, and summarize the historical data-cleaning checks.
- Historical CSV files are cleaned in memory for analytics; the source files
  are not rewritten.

The application does not generate large synthetic CSV datasets. JSON demo
records are initialized only when their store is missing, empty, or invalid.
The branch map displays configured locations with interactive details, and
managers can add further locations from the map workspace.

## Persistence and analytics sources

- `users.json` — manager, client, and technician accounts.
- `tickets.json` — live tickets submitted through the application.
- `branches.json` — branch/project locations and map details.
- `maintenance_requests.csv` and `technicians.csv` — optional historical
  analytics inputs. They are read and cleaned for reporting, and are never
  generated or rewritten by the app.

Historical ticket identifiers receive an `H-` namespace and live identifiers
receive an `L-` namespace during analytics normalization. Live search uses the
ticket hash index for exact ticket-ID and phone-number lookups; the priority
queue orders open tickets High, Normal, then Low.

The historical analytics pipeline normalizes category spelling and whitespace,
checks device/issue compatibility, converts date and numeric columns, flags
invalid phone numbers, removes duplicate ticket IDs and rows with invalid
creation dates, and treats negative costs, invalid parts counts, and negative
repair durations as missing values. The source CSV remains unchanged; the
analytics view, cleaning summary, and CSV export use the cleaned DataFrame.
