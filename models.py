"""Domain models and shared repair catalog for the RepairOps application."""

import datetime
import math


DEVICE_ISSUES = {
    "Laptop": ["Battery", "Screen", "Overheating", "Keyboard", "Software"],
    "Printer": ["Paper Jam", "Ink System", "Connectivity", "Print Quality"],
    "Phone": ["Screen", "Battery", "Charging Port", "Software"],
}
MAX_PARTS_PER_TICKET = 4
MAX_TECHNICIAN_WORKLOAD = 3


class Ticket:
    """Represent a maintenance request and its lifecycle.

    Args:
        ticket_id: Stable ticket identifier.
        device_type: Supported device category.
        issue_type: Issue within the selected device category.
        client_id: Identifier of the ticket owner.
        phone_number: Client contact number.
        description: Free-text description of the issue.
        priority: One of High, Normal, or Low.
    """

    def __init__(
        self,
        ticket_id,
        device_type,
        issue_type,
        client_id,
        phone_number,
        description,
        priority="Normal",
    ):
        """Initialize a pending ticket and its lifecycle metadata."""
        self.ticket_id = str(ticket_id)
        self.device_type = device_type
        self.issue_type = issue_type
        self.client_id = str(client_id)
        self.phone_number = str(phone_number)
        self.description = description
        self.priority = priority
        self.status = "Pending"
        self.technician_id = None
        self.creation_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.resolve_time = None
        self.repair_cost = None
        self.parts_used_num = 0
        self.rating = None
        self.feedback = None

    def to_dict(self):
        """Serialize the ticket into a JSON-compatible mapping."""
        return {
            "ticket_id": self.ticket_id,
            "device_type": self.device_type,
            "issue_type": self.issue_type,
            "client_id": self.client_id,
            "phone_number": self.phone_number,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "technician_id": self.technician_id,
            "creation_time": self.creation_time,
            "resolve_time": self.resolve_time,
            "repair_cost": self.repair_cost,
            "parts_used_num": self.parts_used_num,
            "rating": self.rating,
            "feedback": self.feedback,
        }

    def assign_technician(self, technician_id):
        """Assign this ticket and transition it to In Progress."""
        if self.status != "Pending":
            raise ValueError("Only pending tickets can be assigned.")
        if not technician_id:
            raise ValueError("A technician ID is required.")
        self.technician_id = str(technician_id)
        self.status = "In Progress"

    def complete_ticket(self, repair_cost=None, parts_used_num=0):
        """Complete an active ticket after validating cost and part quantities."""
        if self.status != "In Progress":
            raise ValueError("Only in-progress tickets can be completed.")
        try:
            numeric_parts = float(parts_used_num)
        except (TypeError, ValueError) as error:
            raise ValueError("Parts used must be a whole number.") from error
        if not math.isfinite(numeric_parts) or not numeric_parts.is_integer():
            raise ValueError("Parts used must be a whole number.")
        normalized_parts = int(numeric_parts)
        if not 0 <= normalized_parts <= MAX_PARTS_PER_TICKET:
            raise ValueError(
                f"Parts used must be between 0 and {MAX_PARTS_PER_TICKET}."
            )
        if repair_cost is not None:
            try:
                repair_cost = float(repair_cost)
            except (TypeError, ValueError) as error:
                raise ValueError("Repair cost must be a number.") from error
            if not math.isfinite(repair_cost) or repair_cost < 0:
                raise ValueError("Repair cost must be finite and non-negative.")

        self.status = "Completed"
        self.resolve_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repair_cost = repair_cost
        self.parts_used_num = normalized_parts

    def __str__(self):
        """Return a concise human-readable ticket summary."""
        return (
            f"Ticket {self.ticket_id} | Client ID: {self.client_id} | "
            f"Technician ID: {self.technician_id} | Priority: {self.priority} | "
            f"Status: {self.status}"
        )


class User:
    """Store credentials and common identity fields for an application user."""

    def __init__(self, ID, name, email, password, role):
        """Initialize common user identity and authentication fields."""
        self.ID = str(ID)
        self.name = name
        self.email = email
        self.password = password
        self.role = role

    def to_dict(self):
        """Serialize common user fields for persistence."""
        return {
            "ID": self.ID,
            "name": self.name,
            "email": self.email,
            "password": self.password,
            "role": self.role,
        }


class Technician(User):
    """Represent a technician with a device specialization and active workload."""

    def __init__(self, ID, name, email, password, specialization):
        """Initialize technician account and an empty active-work list."""
        super().__init__(ID, name, email, password, role="Technician")
        self.specialization = specialization
        self.is_available = True
        self.workload = 0
        self.assigned_tickets = []

    def to_dict(self):
        """Serialize technician identity, specialization, and workload."""
        data = super().to_dict()
        data.update(
            {
                "specialization": self.specialization,
                "is_available": self.is_available,
                "workload": self.workload,
                "assigned_tickets": self.assigned_tickets,
            }
        )
        return data

    def assign_task(self, ticket_id=None):
        """Add one active assignment and update availability."""
        if ticket_id is not None and ticket_id in self.assigned_tickets:
            return
        if self.workload >= MAX_TECHNICIAN_WORKLOAD or not self.is_available:
            raise ValueError("Technician is not available.")
        self.workload += 1
        if ticket_id is not None:
            self.assigned_tickets.append(ticket_id)
        self.is_available = self.workload < MAX_TECHNICIAN_WORKLOAD

    def finish_task(self, ticket_id=None):
        """Release an assignment and update availability without underflow."""
        if ticket_id is not None and ticket_id not in self.assigned_tickets:
            return
        if self.workload > 0:
            self.workload -= 1
        if ticket_id is not None:
            self.assigned_tickets.remove(ticket_id)
        self.is_available = self.workload < MAX_TECHNICIAN_WORKLOAD

    def __str__(self):
        """Return a concise human-readable technician summary."""
        return (
            f"Tech {self.name} ({self.specialization}) | Workload: {self.workload} | "
            f"Available: {self.is_available}"
        )


class Manager(User):
    """Represent a user authorized to manage tickets and operational settings."""

    def __init__(self, ID, name, email, password):
        """Initialize a manager account."""
        super().__init__(ID, name, email, password, role="Manager")


class Client(User):
    """Represent a customer and the identifiers of their submitted tickets."""

    def __init__(self, ID, name, email, password):
        """Initialize a customer account with no submitted requests."""
        super().__init__(ID, name, email, password, role="Client")
        self.tickets = []

    def to_dict(self):
        """Serialize the client and their ticket identifiers."""
        data = super().to_dict()
        data["tickets"] = self.tickets
        return data

    def open_new_ticket(
        self,
        ticket_id,
        device_type,
        issue_type,
        phone_number,
        description,
        priority="Normal",
    ):
        """Create a ticket for this client and record its identifier."""
        if device_type not in DEVICE_ISSUES or issue_type not in DEVICE_ISSUES[device_type]:
            raise ValueError("The issue must belong to the selected device type.")
        if priority not in {"High", "Normal", "Low"}:
            raise ValueError("Priority must be High, Normal, or Low.")
        ticket = Ticket(
            ticket_id=ticket_id,
            device_type=device_type,
            issue_type=issue_type,
            client_id=self.ID,
            phone_number=phone_number,
            description=description,
            priority=priority,
        )
        self.tickets.append(ticket.ticket_id)
        return ticket
