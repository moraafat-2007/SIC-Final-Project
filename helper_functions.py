import json
from models import *


def load_users_from_data_base():
    with open('users_db.json', 'r') as file:
        users_db = json.load(file)
        return users_db


def save_users_to_data_base(users):
    with open('users_db.json', 'w') as file:
        json.dump(users, file, indent=4)


def build_user_from_dict(dict_user):
    role = dict_user["role"]

    if role == "Technician":
        user = Technician(
            dict_user["ID"],
            dict_user["name"],
            dict_user["email"],
            dict_user["password"],
            dict_user["specialization"]
        )

        user.is_available = dict_user["is_available"]
        user.workload = dict_user["workload"]
        user.assigned_tickets = dict_user["assigned_tickets"]

    elif role == "Manager":
        user = Manager(
            dict_user["ID"],
            dict_user["name"],
            dict_user["email"],
            dict_user["password"],
        )

    elif role == "Client":
        user = Client(
            dict_user["ID"],
            dict_user["name"],
            dict_user["email"],
            dict_user["password"]
        )

        user.tickets = dict_user["tickets"]

    return user


def save_tickets_to_data_base(tickets):
    with open('tickets_db', 'w') as file:
        json.dump(tickets, file, indent=4)


def load_tickets_from_database():
    with open('tickets_db', 'r') as file:
        tickets = json.load(file)

    return tickets


def build_ticket_from_dict(dict_ticket):
    my_ticket = Ticket(
        dict_ticket["ticket_id"],
        dict_ticket["category"],
        dict_ticket["client_id"],
        dict_ticket["phone_number"],
        dict_ticket["description"],
        dict_ticket["priority"]
    )
    my_ticket.status = dict_ticket["status"]
    my_ticket.technician_id = dict_ticket["technician_id"]
    my_ticket.creation_time = dict_ticket["creation_time"]

    return my_ticket
