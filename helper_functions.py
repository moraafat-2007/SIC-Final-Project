import json
from models import *
from validation import *


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

##Modify it to meet the Ticket Class Changes
def build_ticket_from_dict(dict_ticket):
    my_ticket = Ticket(
        ticket_id=dict_ticket["ticket_id"],
        device_type=dict_ticket["device_type"],
        issue_type=dict_ticket["issue_type"],
        client_id=dict_ticket["client_id"],
        phone_number=dict_ticket["phone_number"],
        description=dict_ticket["description"],
        priority=dict_ticket["priority"]
    )

    my_ticket.status = dict_ticket["status"]
    my_ticket.technician_id = dict_ticket["technician_id"]
    my_ticket.creation_time = dict_ticket["creation_time"]
    my_ticket.resolve_time = dict_ticket.get("resolve_time")
    my_ticket.repair_cost = dict_ticket.get("repair_cost")
    my_ticket.parts_used_num = dict_ticket.get("parts_used_num", 0)

    return my_ticket


def validate_registration(users,name,email,password,role,specialization=None):
    errors = []

    if not is_not_empty(name):
        errors.append("Name is required.")




    if not is_not_empty(email):
        errors.append("Email is required.")

    elif not is_valid_email_format(email.strip()):
        errors.append("Invalid email format.")

    elif not is_new_email(email.strip(), users):
        errors.append("This email is already registered.")




    if not is_not_empty(password):
        errors.append("Password is required.")

    elif len(password) < 8:
        errors.append("Password must be at least 8 characters.")




    if role == "Technician":
        if not is_not_empty(specialization):
            errors.append("Specialization is required.")


    return errors
