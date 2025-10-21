import hashlib
from .models import Admin, Employee, EmployeePassword

def authenticate_user(email, password):
    """
    Authenticate user against Admin and Employee tables
    Returns: (user_object, user_type) or (None, None)
    """
    # Try to authenticate as admin first
    try:
        admin = Admin.objects.get(email=email, status='active')
        # Simple password hash check
        if admin.password_hash == simple_hash(password):
            return admin, 'ADMIN'
    except Admin.DoesNotExist:
        pass
    
    # Try to authenticate as employee
    try:
        employee = Employee.objects.get(email=email, status='active')
        # Check if employee has password set
        try:
            employee_password = EmployeePassword.objects.get(employee=employee)
            if employee_password.password_hash == simple_hash(password):
                return employee, employee.role.upper().replace(' ', '_')
        except EmployeePassword.DoesNotExist:
            # If no password set, use default passwords
            if check_employee_default_password(employee, password):
                return employee, employee.role.upper().replace(' ', '_')
    except Employee.DoesNotExist:
        pass
    
    return None, None

def simple_hash(password):
    """Simple hash function for demo purposes"""
    return hashlib.md5(password.encode()).hexdigest()

def check_employee_default_password(employee, password):
    """
    Check employee password using employee_id or phone as default password
    """
    # Default passwords
    default_passwords = [
        employee.employee_id,  # Employee ID as password
        employee.phone,        # Phone as password
        '123456',              # Common default password
        'password'             # Common default password
    ]
    
    return password in default_passwords

def set_employee_password(employee, new_password):
    """Set or update employee password"""
    password_hash = simple_hash(new_password)
    
    try:
        # Update existing password
        employee_password = EmployeePassword.objects.get(employee=employee)
        employee_password.password_hash = password_hash
        employee_password.save()
    except EmployeePassword.DoesNotExist:
        # Create new password record
        EmployeePassword.objects.create(
            employee=employee,
            password_hash=password_hash
        )
    
    return True

def get_user_display_name(user, user_type):
    """Get display name based on user type"""
    if user_type == 'ADMIN':
        return user.name
    else:  # Employee
        return f"{user.first_name} {user.last_name}"