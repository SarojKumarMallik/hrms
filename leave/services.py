# leave/services.py
from django.utils import timezone
from datetime import datetime, date, timedelta
from django.db import transaction
from decimal import Decimal
from .models import Leave, LeaveBalance, LeaveType, Holiday
from hr.models import Employee
import calendar

class LeaveAccrualService:
    """Handles monthly leave accrual of 1.5 days per month"""
    
    @staticmethod
    def calculate_monthly_accrual(employee, month, year):
        """Calculate monthly accrual of 1.5 days"""
        # Check probation period
        if hasattr(employee, 'probation_end_date') and employee.probation_end_date:
            if employee.probation_end_date > timezone.now().date():
                return Decimal('0')  # No leave during probation
        
        # Check if employee has completed the month
        if employee.date_of_joining:
            joining_date = employee.date_of_joining
            # If joined after the 1st of the month, no accrual for that month
            if joining_date.day > 1 and joining_date.month == month and joining_date.year == year:
                return Decimal('0')
        
        return Decimal('1.5')  # Monthly accrual rate

    @staticmethod
    def process_monthly_accrual_for_all():
        """Process monthly accrual for all active employees"""
        today = timezone.now().date()
        current_month = today.month
        current_year = today.year
        
        # Only process on 1st of each month
        if today.day != 1:
            return
        
        active_employees = Employee.objects.filter(status='active')
        annual_leave_type, created = LeaveType.objects.get_or_create(
            name='annual',
            defaults={'max_days': 18, 'is_active': True}
        )
        
        for employee in active_employees:
            accrual_amount = LeaveAccrualService.calculate_monthly_accrual(
                employee, current_month, current_year
            )
            
            if accrual_amount > 0:
                with transaction.atomic():
                    balance, created = LeaveBalance.objects.get_or_create(
                        employee=employee,
                        leave_type=annual_leave_type,
                        year=current_year,
                        defaults={
                            'total_leaves': accrual_amount,
                            'leaves_remaining': accrual_amount,
                            'leaves_taken': 0,
                            'carry_forward': 0
                        }
                    )
                    
                    if not created:
                        balance.total_leaves += accrual_amount
                        balance.leaves_remaining += accrual_amount
                        balance.save()

class OptionalLeaveService:
    """Manages optional leave rules (4 days/year, use only 2, lose remaining 2)"""
    
    @staticmethod
    def initialize_optional_leave(employee, year):
        """Initialize optional leave balance for the year"""
        optional_leave_type, created = LeaveType.objects.get_or_create(
            name='optional',
            defaults={'max_days': 4, 'is_active': True}
        )
        
        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=optional_leave_type,
            year=year,
            defaults={
                'total_leaves': 4,
                'leaves_remaining': 4,
                'leaves_taken': 0,
                'carry_forward': 0
            }
        )
        return balance
    
    @staticmethod
    def can_use_optional_leave(employee, days_requested, year):
        """Check if employee can use optional leave"""
        try:
            optional_leave_type = LeaveType.objects.get(name='optional')
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=optional_leave_type,
                year=year
            )
            
            # Check if already used 2 days (max allowed)
            if balance.leaves_taken >= 2:
                return False, "Maximum 2 optional leaves allowed per year"
            
            # Check if requested days exceed remaining quota
            remaining_quota = 2 - balance.leaves_taken
            if days_requested > remaining_quota:
                return False, f"Can only use {remaining_quota} more optional leave days"
            
            # Check overall balance
            if days_requested > balance.leaves_remaining:
                return False, f"Insufficient optional leave balance. Available: {balance.leaves_remaining}"
            
            return True, "Can use optional leave"
            
        except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
            return False, "Optional leave balance not found"

class CarryForwardService:
    """Handles earned leave carry forward (max 12 days, rest LOST)"""
    
    @staticmethod
    def calculate_carry_forward(employee, current_year):
        """Calculate carry forward from previous year"""
        previous_year = current_year - 1
        
        try:
            annual_leave_type = LeaveType.objects.get(name='annual')
            prev_balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=annual_leave_type,
                year=previous_year
            )
            
            # Calculate carry forward (max 12 days)
            available_carry = prev_balance.leaves_remaining
            carry_forward = min(available_carry, 12)
            
            return carry_forward
            
        except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
            return Decimal('0')
    
    @staticmethod
    def process_carry_forward(employee, current_year):
        """Process carry forward for new year"""
        carry_forward = CarryForwardService.calculate_carry_forward(employee, current_year)
        
        if carry_forward > 0:
            annual_leave_type = LeaveType.objects.get(name='annual')
            
            # Create or update current year balance with carry forward
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                leave_type=annual_leave_type,
                year=current_year,
                defaults={
                    'total_leaves': carry_forward,
                    'leaves_remaining': carry_forward,
                    'leaves_taken': 0,
                    'carry_forward': carry_forward
                }
            )
            
            if not created:
                balance.carry_forward = carry_forward
                balance.leaves_remaining += carry_forward
                balance.total_leaves += carry_forward
                balance.save()
        
        return carry_forward

class ProbationService:
    """Handles probation period restrictions (3 months no leave, salary deduction)"""
    
    @staticmethod
    def calculate_probation_end_date(joining_date):
        """Calculate probation end date (3 months from joining)"""
        if not joining_date:
            return None
        
        # Add 3 months to joining date
        year = joining_date.year
        month = joining_date.month + 3
        if month > 12:
            year += 1
            month -= 12
        
        # Get last day of the month
        last_day = calendar.monthrange(year, month)[1]
        day = min(joining_date.day, last_day)
        
        return date(year, month, day)
    
    @staticmethod
    def is_on_probation(employee):
        """Check if employee is on probation"""
        if not hasattr(employee, 'probation_end_date') or not employee.probation_end_date:
            # Auto-calculate if not set
            if employee.date_of_joining:
                employee.probation_end_date = ProbationService.calculate_probation_end_date(
                    employee.date_of_joining
                )
                employee.save()
            else:
                return False
        
        return timezone.now().date() <= employee.probation_end_date
    
    @staticmethod
    def can_take_leave_during_probation(employee, leave_type):
        """Check if leave can be taken during probation"""
        if not ProbationService.is_on_probation(employee):
            return True, "Not on probation"
        
        # Allow only specific leave types during probation
        allowed_types = ['sick', 'maternity']
        if leave_type.name in allowed_types:
            return True, "Allowed during probation"
        
        return False, "Leave not allowed during probation period (first 3 months)"

class CompOffService:
    """Handles compensatory off for working on holidays"""
    
    @staticmethod
    def earn_comp_off(employee, work_date, reason=""):
        """Earn comp off for working on holiday"""
        # Check if it's actually a holiday for employee's region
        is_holiday = Holiday.objects.filter(
            date=work_date,
            region__name=employee.location
        ).exists()
        
        if not is_holiday:
            return False, "Not a holiday in your region"
        
        # Check if comp off already earned for this date
        existing_comp_off = Leave.objects.filter(
            employee=employee,
            start_date=work_date,
            leave_type__name='comp_off',
            status='approved'
        ).exists()
        
        if existing_comp_off:
            return False, "Comp off already earned for this date"
        
        # Get or create comp off leave type
        comp_off_type, created = LeaveType.objects.get_or_create(
            name='comp_off',
            defaults={'max_days': 30, 'is_active': True}
        )
        
        # Create comp off balance entry
        balance, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=comp_off_type,
            year=work_date.year,
            defaults={
                'total_leaves': 1,
                'leaves_remaining': 1,
                'leaves_taken': 0,
                'carry_forward': 0
            }
        )
        
        if not created:
            balance.total_leaves += 1
            balance.leaves_remaining += 1
            balance.save()
        
        # Create comp off leave record
        comp_off_leave = Leave.objects.create(
            employee=employee,
            leave_type=comp_off_type,
            start_date=work_date,
            end_date=work_date,
            days_requested=1,
            reason=f"Comp off for working on holiday: {reason}",
            status='approved',
            applied_date=timezone.now()
        )
        
        return True, "Comp off earned successfully"

class YearEndService:
    """Handles year-end processing and automatic loss of excess leaves"""
    
    @staticmethod
    def process_year_end():
        """Process year-end for all employees"""
        current_year = timezone.now().year
        next_year = current_year + 1
        
        employees = Employee.objects.filter(status='active')
        
        for employee in employees:
            YearEndService.process_employee_year_end(employee, current_year, next_year)
    
    @staticmethod
    def process_employee_year_end(employee, current_year, next_year):
        """Process year-end for a single employee"""
        with transaction.atomic():
            # Process annual leave carry forward
            carry_forward = CarryForwardService.process_carry_forward(employee, next_year)
            
            # Reset optional leaves (lose remaining - max use 2 out of 4)
            try:
                optional_leave_type = LeaveType.objects.get(name='optional')
                optional_balance = LeaveBalance.objects.get(
                    employee=employee,
                    leave_type=optional_leave_type,
                    year=current_year
                )
                # Optional leaves don't carry forward - they're lost
                optional_balance.leaves_remaining = 0
                optional_balance.save()
                
                # Initialize next year's optional leaves
                OptionalLeaveService.initialize_optional_leave(employee, next_year)
                
            except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
                # Initialize if not exists
                OptionalLeaveService.initialize_optional_leave(employee, next_year)
            
            # Reset sick leaves (typically don't carry forward)
            try:
                sick_leave_type = LeaveType.objects.get(name='sick')
                sick_balance = LeaveBalance.objects.get(
                    employee=employee,
                    leave_type=sick_leave_type,
                    year=current_year
                )
                sick_balance.leaves_remaining = 0
                sick_balance.save()
            except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
                pass
            
            # Reset comp off (typically don't carry forward)
            try:
                comp_off_type = LeaveType.objects.get(name='comp_off')
                comp_off_balance = LeaveBalance.objects.get(
                    employee=employee,
                    leave_type=comp_off_type,
                    year=current_year
                )
                comp_off_balance.leaves_remaining = 0
                comp_off_balance.save()
            except (LeaveType.DoesNotExist, LeaveBalance.DoesNotExist):
                pass

class LeaveValidationService:
    """Centralized leave validation service"""
    
    @staticmethod
    def validate_leave_application(employee, leave_type, start_date, end_date, days_requested):
        """Validate leave application against all business rules"""
        errors = []
        warnings = []
        
        current_year = start_date.year
        
        # 1. Check probation period
        if ProbationService.is_on_probation(employee):
            can_take, message = ProbationService.can_take_leave_during_probation(employee, leave_type)
            if not can_take:
                errors.append(message)
        
        # 2. Check optional leave restrictions
        if leave_type.name == 'optional':
            can_use, message = OptionalLeaveService.can_use_optional_leave(
                employee, float(days_requested), current_year
            )
            if not can_use:
                errors.append(message)
        
        # 3. Check balance
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=current_year
            )
            
            if balance.leaves_remaining < days_requested:
                errors.append(
                    f"Insufficient {leave_type.name} balance. "
                    f"Available: {balance.leaves_remaining}, Requested: {days_requested}"
                )
                
        except LeaveBalance.DoesNotExist:
            errors.append(f"No leave balance found for {leave_type.name}")
        
        # 4. Check if applying for same month accrual (for annual leave)
        if leave_type.name == 'annual' and start_date.month == timezone.now().month:
            warnings.append("Note: You are applying for leave in the same month as accrual")
        
        return len(errors) == 0, errors, warnings

    @staticmethod
    def deduct_leave_balance(employee, leave_type, days, year):
        """Deduct leave balance after approval"""
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=year
            )
            
            if balance.leaves_remaining >= days:
                balance.leaves_taken += days
                balance.leaves_remaining -= days
                balance.save()
                return True
            return False
            
        except LeaveBalance.DoesNotExist:
            return False

# Utility function to initialize leave balances for new employee
def initialize_employee_leave_balances(employee, year):
    """Initialize all leave balances for a new employee"""
    leave_types = LeaveType.objects.filter(is_active=True)
    
    for leave_type in leave_types:
        defaults = {
            'total_leaves': 0,
            'leaves_remaining': 0,
            'leaves_taken': 0,
            'carry_forward': 0
        }
        
        # Set initial values based on leave type
        if leave_type.name == 'annual':
            # New employees start with 0 annual leaves (accrual starts next month)
            pass
        elif leave_type.name == 'optional':
            defaults['total_leaves'] = 4
            defaults['leaves_remaining'] = 4
        elif leave_type.name == 'sick':
            defaults['total_leaves'] = 12  # Example: 12 sick leaves per year
            defaults['leaves_remaining'] = 12
        elif leave_type.name == 'casual':
            defaults['total_leaves'] = 6   # Example: 6 casual leaves per year
            defaults['leaves_remaining'] = 6
        
        LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=leave_type,
            year=year,
            defaults=defaults
        )