from data_manager import *

def login(email,password):

    users_database = load_users()
    for user in users_database:
        if user.email == email and user.password == password:
            return user
    return None



def register(ID,name,email,password,role): # still in progress
    users_database = load_users()






# def login_registration():
#     from user import User
#     import sys
#     import helper_functions
#     users = helper_functions.load_users()
#     current_user = None
#
#     print('\n============== Welcome To The  Workshops And Learning Events Planner ==============\n')
#     while True:
#         print('1) Login')
#         print('2) Register')
#         print('3) Exit')
#
#         choice = input('Enter Your Choice').strip()
#
#         if choice == '1':
#             print("\n--- User Login ---")
#
#             email = input('Enter Your Email').strip()
#             password = input('Enter Your Password').strip()
#
#             if email in users and users[email]["password"] == password:
#
#                 data = users[email]
#
#                 current_user = User(
#                     data["name"],
#                     data["PhoneNumber"],
#                     email,
#                     data["gender"],
#                     data["governorate"],
#                     data["password"],
#                     data["age"],
#                     data["national_id"]
#                 )
#
#                 current_user.role = data["role"]
#                 current_user.learning_plan.load_list(data["learning_plan"])
#                 break
#             else:
#                 print("Invalid Email or Password\n")
#
#         elif choice == '2':
#             print("\n--- User Registration ---")
#
#             name = input("Name: ").strip()
#
#             while True:
#                 phone = input("Phone Number: ").strip()
#                 if phone.isdigit():
#                     break
#                 print("Invalid Phone Number! Try again\n")
#
#             while True:
#                 email = input("Email: ").strip()
#                 if email not in users:
#                     break
#                 print("Email Already Exists! Try again\n")
#
#             while True:
#                 gender = input("Gender: ").strip()
#                 if gender.lower() == 'male' or gender.lower() == 'female':
#                     break
#                 print("Sorry We Don't Support That ! Try again or Just Close The Program\n")
#
#             governorate = input("Governorate: ").strip()
#
#             password = input("Password: ").strip()
#
#             while True:
#                 age = input('Age: ').strip()
#                 try:
#                     int(age)
#                     break
#                 except:
#                     print("Invalid Age! Try again\n")
#
#             while True:
#                 national_id = input("National ID: ").strip()
#                 if national_id.isdigit():
#                     break
#                 print("Invalid National ID! Try again\n")
#
#             current_user = User(name, phone, email, gender, governorate, password, age, national_id)
#
#             users[email] = {
#                 "name": current_user.name,
#                 "PhoneNumber": current_user.phone_number,
#                 "gender": current_user.gender,
#                 "governorate": current_user.governorate,
#                 "password": current_user.password,
#                 "age": current_user.age,
#                 "national_id": current_user.national_id,
#                 "role": current_user.role,
#                 "learning_plan": current_user.learning_plan.to_list()
#             }
#             helper_functions.save_users(users)
#             break
#
#         elif choice == '3':
#             print("Exiting application. Goodbye!")
#             sys.exit()
#         else:
#             print('Invalid Input! Try again\n')
#             continue
#
#     return current_user
