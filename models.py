import datetime


class Ticket:
    def __init__(self, ticket_id, category, client_id, phone_number, description, priority="Normal"):
        self.ticket_id = ticket_id
        self.category = category
        self.client_id = client_id
        self.phone_number = phone_number
        self.description = description
        self.priority = priority  # مثلاً: High, Normal, Low
        self.status = "Pending"  # الحالة الافتراضية عند إنشاء أي تذكرة
        self.technician_id = None  # الفني المسؤول (فارغ في البداية)
        self.creation_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self):
        return {
            "ticket_id": self.ticket_id,
            "category": self.category,
            "client_id": self.client_id,
            "phone_number": self.phone_number,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "technician_id": self.technician_id,
            "creation_time": self.creation_time,
        }

    def assign_technician(self, technician_id):
        self.technician_id = technician_id
        self.status = "In Progress"

    def complete_ticket(self):
        self.status = "Completed"

    def __str__(self):
        return f"Ticket {self.ticket_id} | Client ID: {self.client_id} | Technician ID: {self.technician_id}| Priority: {self.priority} | Status: {self.status}"


class User:
    def __init__(self, ID, name, email, password, role):
        self.ID = ID
        self.name = name
        self.email = email
        self.password = password
        self.role = role

    def to_dict(self):
        data = {
            "ID": self.ID,
            "name": self.name,
            "email": self.email,
            "password": self.password,
            "role": self.role
        }
        return data


class Technician(User):
    def __init__(self, ID, name, email, password, specialization):
        super().__init__(ID, name, email, password, role="Technician")

        self.specialization = specialization
        self.is_available = True
        self.workload = 0
        self.assigned_tickets = []  # tickets assigned to this technician

    def to_dict(self):

        data = super().to_dict()

        data.update({
            "specialization": self.specialization,
            "is_available": self.is_available,
            "workload": self.workload,
            "assigned_tickets": self.assigned_tickets
        })

        return data

    def assign_task(self):
        self.workload += 1
        if self.workload >= 3:  # لو عنده 3 أجهزة، يصبح غير متاح
            self.is_available = False

    def finish_task(self):
        if self.workload > 0:
            self.workload -= 1
        self.is_available = True

    def __str__(self):
        return f"Tech {self.name} ({self.specialization}) | Workload: {self.workload} | Available: {self.is_available}"


class Manager(User):
    def __init__(self, ID, name, email, password):
        super().__init__(ID, name, email, password, role="Manager")

    def to_dict(self):
        return super().to_dict()


class Client(User):
    def __init__(self, ID, name, email, password):
        super().__init__(ID, name, email, password, role="Client")

        self.tickets = []  # tickets created by the client

    def to_dict(self):
        data = super().to_dict()
        data.update({
            "tickets": self.tickets
        })

    def open_new_ticket(self):
        pass

# class SparePart:
#     def __init__(self, part_id, name, quantity, price):
#         self.part_id = part_id
#         self.name = name
#         self.quantity = quantity
#         self.price = price
#
#     def use_part(self, amount=1):
#         if self.quantity >= amount:
#             self.quantity -= amount
#             return True
#         return False # الكمية لا تكفي
#
#     def restock(self, amount):
#         self.quantity += amount
#
#     def __str__(self):
#         return f"Part: {self.name} | Qty: {self.quantity} | Price: ${self.price}"
