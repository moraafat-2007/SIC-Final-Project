import datetime

class Ticket:
    def __init__(self, ticket_id, name_of_client, phone_number, description, priority="Normal"):
        self.ticket_id = ticket_id
        self.name_of_client = name_of_client
        self.phone_number = phone_number
        self.description = description
        self.priority = priority # مثلاً: High, Normal, Low
        self.status = "Pending"  # الحالة الافتراضية عند إنشاء أي تذكرة
        self.assigned_technician = None # الفني المسؤول (فارغ في البداية)
        self.created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def assign_technician(self, technician_name):
        self.assigned_technician = technician_name
        self.status = "In Progress"

    def complete_ticket(self):
        self.status = "Completed"

    def __str__(self):
        return f"Ticket {self.ticket_id} | Client: {self.name_of_client} | Priority: {self.priority} | Status: {self.status}"


class Technician:
    def __init__(self, technician_id, name, specialization):
        self.technician_id = technician_id
        self.name = name
        self.specialization = specialization
        self.is_available = True
        self.workload = 0  # عدد المهام الحالية للفني

    def assign_task(self):
        self.workload += 1
        if self.workload >= 3: # لو عنده 3 أجهزة، يصبح غير متاح
            self.is_available = False

    def finish_task(self):
        if self.workload > 0:
            self.workload -= 1
        self.is_available = True

    def __str__(self):
        return f"Tech {self.name} ({self.specialization}) | Workload: {self.workload} | Available: {self.is_available}"


class SparePart:
    def __init__(self, part_id, name, quantity, price):
        self.part_id = part_id
        self.name = name
        self.quantity = quantity
        self.price = price

    def use_part(self, amount=1):
        if self.quantity >= amount:
            self.quantity -= amount
            return True
        return False # الكمية لا تكفي

    def restock(self, amount):
        self.quantity += amount

    def __str__(self):
        return f"Part: {self.name} | Qty: {self.quantity} | Price: ${self.price}"