from helper_functions import *


def save_users(users):
    users_db = []

    for user in users:
        users_db.append(user.to_dict())

    save_users_to_data_base(users_db)


def load_users():
    users_dict = load_users_from_data_base()

    users_obj = []

    for user in users_dict:
        users_obj.append(build_user_from_dict(user))

    return users_obj


def save_tickets(tickets):
    tickets_db = []

    for ticket in tickets:
        tickets_db.append(ticket.to_dict())

    save_tickets_to_data_base(tickets_db)


def load_tickets():
    tickets_dict = load_tickets_from_database()

    tickets_obj = []

    for ticket in tickets_dict:
        tickets_obj.append(build_ticket_from_dict(ticket))
