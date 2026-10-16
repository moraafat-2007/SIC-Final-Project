import heapq

from models import Ticket

COMPANY_HOTLINE = "0120000-REPAIR (Free Hotline Support)"


class TicketQueue:
    def __init__(self):
        self.heap = []
        self.counter = 0

    def add_ticket(self, ticket: Ticket):
        priority_map = {"High": 1, "Normal": 2, "Low": 3}
        p_weight = priority_map.get(ticket.priority, 2)

        heapq.heappush(self.heap, (p_weight, self.counter, ticket))
        self.counter += 1

    def get_next_ticket(self):
        if self.heap:
            weight, count, ticket = heapq.heappop(self.heap)
            ticket.status = "In Progress"
            return ticket
        return None

    def is_empty(self):
        return len(self.heap) == 0


class TicketHashTable:
    def __init__(self):
        self.tickets_by_id = {}
        self.tickets_by_phone = {}

    def insert(self, ticket: Ticket):
        self.tickets_by_id[ticket.ticket_id] = ticket

        phone = str(ticket.phone_number).strip()
        if phone not in self.tickets_by_phone:
            self.tickets_by_phone[phone] = []
        self.tickets_by_phone[phone].append(ticket)

    def search_by_id(self, ticket_id):
        return self.tickets_by_id.get(ticket_id, None)

    def search_by_phone(self, phone_number):
        return self.tickets_by_phone.get(str(phone_number).strip(), [])

    def search_by_partial_phone(self, last_digits):
        results = []
        last_digits = str(last_digits).strip()
        for phone, tickets in self.tickets_by_phone.items():
            if phone.endswith(last_digits):
                results.extend(tickets)
        return results


class RestockQueue:
    def __init__(self, low_stock_threshold=2):
        self.restock_list = []
        self.threshold = low_stock_threshold

    def check_and_add_part(self, spare_part):
        if spare_part.quantity <= self.threshold:
            if spare_part not in self.restock_list:
                self.restock_list.append(spare_part)
                return True
        return False

    def get_next_restock_order(self):
        if self.restock_list:
            return self.restock_list.pop(0)
        return None

    def is_empty(self):
        return len(self.restock_list) == 0


def get_phone_support_info():
    return {
        "hotline": COMPANY_HOTLINE,
        "message": "Got a simple or software-related issue? Call us directly on our hotline for free instant technical guidance without waiting for an on-site visit!",
        "is_free": True
    }


class AdminManager:
    def __init__(self, ticket_hash_table):
        self.hash_table = ticket_hash_table

    def get_financial_summary(self):
        total_revenue = 0.0
        completed_count = 0

        for ticket_id, ticket in self.hash_table.tickets_by_id.items():
            if ticket.status == "Completed" and getattr(ticket, 'repair_cost', None):
                total_revenue += float(ticket.repair_cost)
                completed_count += 1

        return {
            "total_revenue": total_revenue,
            "completed_tickets_count": completed_count
        }

    def get_all_ratings_and_feedback(self):
        ratings_report = []
        for ticket_id, ticket in self.hash_table.tickets_by_id.items():
            if hasattr(ticket, 'rating') and ticket.rating is not None:
                ratings_report.append({
                    "ticket_id": ticket_id,
                    "client_id": getattr(ticket, 'client_id', 'Unknown'),
                    "technician_id": getattr(ticket, 'technician_id', 'Unassigned'),
                    "rating": ticket.rating,
                    "feedback": getattr(ticket, 'feedback', 'No comment')
                })
        return ratings_report

    def manual_override_assignment(self, ticket, technician):
        ticket.assign_technician(technician.ID)
        if hasattr(technician, 'assign_task'):
            technician.assign_task()
        return f"Ticket #{ticket.ticket_id} has been manually assigned to technician {technician.name} successfully."