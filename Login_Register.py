from data_manager import *
from validation import *

def login(email,password):

    users_database = load_users()
    for user in users_database:
        if user.email == email and user.password == password:
            return user
    return None



def register(ID,name,email,password,role,specialization = None):
    users_database = load_users()

    errors = validate_registration(users_database,name,email,password,role,specialization = None)

    if errors:
        return {
            "success": False,
            "message": "Fix The Following Errors.",
            "errors": errors
        }

    # still i need to build the user as his role then save it to data base and return another dict having the user




