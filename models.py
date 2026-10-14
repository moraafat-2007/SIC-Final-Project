import datetime

#ِNew: Data of the devices and their issues
DEVICE_ISSUES = {
    "Laptop": ["Battery", "Screen", "Overheating", "Keyboard", "Software"],
    "Printer": ["Paper Jam", "Ink System", "Connectivity", "Print Quality"],
    # "AC": ["Gas Leak", "Compressor", "Thermostat", "Noise"],
    # "Router": ["No Signal", "Firmware", "Port Failure", "Slow Speed"],
    "Phone": ["Screen", "Battery", "Charging Port", "Software"]
}
#New: max numbre of spare parts/ ticket is 4
MAX_PARTS_PER_TICKET = 4

class Ticket:
    def __init__(self, ticket_id,device_type, issue_type, client_id, phone_number, description, priority="Normal"):
        self.ticket_id = ticket_id
        self.device_type=device_type    #New: Instide of the category
        self.issue_type=issue_type      #New
        self.client_id = client_id
        self.phone_number = phone_number
        self.description = description
        self.priority = priority  # مثلاً: High, Normal, Low
        self.status = "Pending"  # الحالة الافتراضية عند إنشاء أي تذكرة
        self.technician_id = None  # الفني المسؤول (فارغ في البداية)
        self.creation_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.resolve_time = None  #New: Auto selected when the ticket is completed
        self.repair_cost = None  #New: the cost of the repairing
        self.parts_used_num = 0  #New: number of spare parts used

    def to_dict(self):
        return {
            "ticket_id": self.ticket_id,
            "device_type": self.device_type,  #New: Instide of the category
            "issue_type": self.issue_type,  #New
            "client_id": self.client_id,
            "phone_number": self.phone_number,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "technician_id": self.technician_id,
            "creation_time": self.creation_time,
            "resolve_time": self.resolve_time,  # New
            "repair_cost": self.repair_cost,  # New
            "parts_used_num": self.parts_used_num,  # New
        }

    def assign_technician(self, technician_id):
        self.technician_id = technician_id
        self.status = "In Progress"

    def complete_ticket(self,repait_cost=None,parts_used_num=0):
        #New: Verify that the spare parts are with 0-4
        if not 0 <= parts_used_num <= MAX_PARTS_PER_TICKET:
            raise ValueError(f"parts_used_num must be between 0 and {MAX_PARTS_PER_TICKET}")
        #New: Verify that the repair cost is not negative
        if repair_cost is not None and repair_cost < 0:
            raise ValueError("repair_cost cannot be negative")
 
        self.status = "Completed"
        self.resolve_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")  #New: create the resolve_time as creation_time
        self.repair_cost = repair_cost  #New
        self.parts_used_num = parts_used_num  #New 

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
        return data   ##Was MISSING

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
