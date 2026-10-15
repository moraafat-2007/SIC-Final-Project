"""Shared validation rules for RepairOps inputs and model workflows."""

import re

from models import DEVICE_ISSUES


EMAIL_PATTERN = re.compile(
    r"^(?=.{3,254}$)(?=.{1,64}@)"
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)
PHONE_PATTERN = re.compile(r"^01[0125][0-9]{8}$")
ALLOWED_PRIORITIES = ("High", "Normal", "Low")


def is_valid_phone(phone_number):
    """Return whether a value is an Egyptian mobile number in the supported format."""
    return PHONE_PATTERN.fullmatch(str(phone_number or "").strip()) is not None


def is_not_empty(value):
    """Return whether a value is non-null and contains non-whitespace text."""
    return value is not None and bool(str(value or "").strip())


def is_valid_priority(priority):
    """Return whether a priority is one of the supported canonical values."""
    return priority in ALLOWED_PRIORITIES


def is_valid_email_format(email):
    """Validate a conventional email address with a dotted, non-empty domain."""
    return EMAIL_PATTERN.fullmatch(str(email or "").strip()) is not None


def is_new_email(email, users):
    """Return whether an email address is unique among the supplied user objects."""
    normalized_email = str(email or "").strip().casefold()
    return all(user.email.strip().casefold() != normalized_email for user in users)


def is_valid_device_issue(device_type, issue_type):
    """Return whether an issue belongs to the selected device category."""
    return issue_type in DEVICE_ISSUES.get(device_type, ())


def validate_password(password):
    """Return errors for a 12-128-character password with mixed character classes."""
    errors = []
    if not isinstance(password, str) or len(password) < 12:
        errors.append("Password must be at least 12 characters long.")
        return errors
    if len(password) > 128:
        errors.append("Password must not exceed 128 characters.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain a lowercase letter.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain an uppercase letter.")
    if not re.search(r"[0-9]", password):
        errors.append("Password must contain a number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Password must contain a special character.")
    return errors


def validate_ticket_request(device_type, issue_type, phone_number, description, priority):
    """Return all validation errors for a new maintenance ticket."""
    errors = []
    if device_type not in DEVICE_ISSUES:
        errors.append("Select a supported device type.")
    elif not is_valid_device_issue(device_type, issue_type):
        errors.append("Select an issue that belongs to the selected device.")
    if not is_valid_phone(phone_number):
        errors.append("Enter a valid 11-digit Egyptian mobile number.")
    if not is_not_empty(description):
        errors.append("Issue description is required.")
    if not is_valid_priority(priority):
        errors.append("Select a supported priority.")
    return errors


def validate_registration(users, name, email, password, role="Client", specialization=None, ID=None):
    """Validate a new account before data_manager persists it."""
    errors = []
    if not is_not_empty(ID):
        errors.append("User ID is required.")
    if not is_not_empty(name):
        errors.append("Name is required.")
    if not is_valid_email_format(email):
        errors.append("Enter a valid email address.")
    elif not is_new_email(email, users):
        errors.append("An account with this email already exists.")
    errors.extend(validate_password(password))
    if role not in {"Client", "Technician"}:
        errors.append("Only client and technician accounts can be registered.")
    elif role == "Technician":
        if not is_not_empty(specialization):
            errors.append("Technician specialization is required.")
        elif specialization not in DEVICE_ISSUES:
            errors.append("Select a supported technician specialization.")
    if ID is not None and any(user.ID == str(ID) for user in users):
        errors.append("This account ID is already in use.")
    return errors
