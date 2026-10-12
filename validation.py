# ==========================================
# Shared Utilities: Validation Rules
# ==========================================
import re

def is_valid_phone(phone_number):
    """
    يتحقق من أن رقم الهاتف مصري صحيح:
    - يتكون من 11 رقم.
    - يبدأ بـ 010 أو 011 أو 012 أو 015.
    """
    pattern = r"^01[0125][0-9]{8}$"
    if re.match(pattern, str(phone_number)):
        return True
    return False

def is_not_empty(text):
    """
    يتحقق من أن الحقل النصي (مثل اسم العميل أو وصف العطل) ليس فارغاً
    ولا يحتوي على مسافات فقط.
    """
    if not text or str(text).strip() == "":
        return False
    return True

def is_positive_number(value):
    """
    يتحقق من أن القيمة المدخلة (مثل السعر أو الكمية) هي رقم موجب.
    """
    try:
        num = float(value)
        if num > 0:
            return True
        return False
    except ValueError:
        return False

def is_valid_priority(priority):
    """
    يتحقق من أن مستوى الأهمية المدخل من ضمن الخيارات المسموحة فقط.
    """
    allowed_priorities = ["High", "Normal", "Low"]
    if priority in allowed_priorities:
        return True
    return False

def is_valid_email(email):
    """
    يتحقق من صحة صيغة البريد الإلكتروني (بونص إضافي لو احتجتوه).
    """
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if re.match(pattern, str(email)):
        return True
    return False