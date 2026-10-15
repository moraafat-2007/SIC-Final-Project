from data_manager import *
from validation import *


def login(email, password):
    users_database = load_users()
    for user in users_database:
        if user.email == email and user.password == password:
            return user
    return None


def register(ID, name, email, password, role, specialization=None):
    users_database = load_users()

    errors = validate_registration(users_database, name, email, password, role, specialization=None)

    if errors:
        return {
            "success": False,
            "message": "Fix The Following Errors.",
            "errors": errors
        }

    if role == "Client":
        user = Client(ID, name, email, password)

    elif role == "Technician":
        user = Technician(ID, name, email, password, specialization)

    return {
        "success": True,
        "message": "Registration Success.",
        "user": user
    }

    users_database.append(user)

    save_users(users_database)
