# leave/models.py
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from hr.models import Employee

class Region(models.Model):
    """Branch/Region model for location-based holidays"""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    colour = models.CharField(max_length=50, default='blue')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    class Meta:
        ordering = ['name']

class Holiday(models.Model):
    """Regional holidays model"""
    name = models.CharField(max_length=200)
    holiday_type = models.CharField(max_length=200)
    colour = models.CharField(max_length=200)
    date = models.DateField()
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='holidays')
    description = models.TextField(blank=True)
    is_optional = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} - {self.region.name} ({self.date})"
    
    class Meta:
        ordering = ['date']
        unique_together = ['name', 'date', 'region']

class LeaveType(models.Model):
    LEAVE_TYPES = [
        ('casual', 'Casual Leave'),
        ('maternity', 'Maternity Leave'),
        ('comp_off', 'Comp Off'),
        ('sick', 'Sick Leave'),
        ('annual', 'Annual Leave'),
        ('optional', 'Optional Leave'),
        
    ]
    name = models.CharField(max_length=20, choices=LEAVE_TYPES, unique=True)
    max_days = models.IntegerField(default=30)
    is_active = models.BooleanField(default=True)
    accrual_rate = models.DecimalField(max_digits=4, decimal_places=2, default=0)  # 1.5 for monthly
    is_optional = models.BooleanField(default=False)  # For optional leaves
    max_carry_forward = models.IntegerField(default=0)  # 12 for earned leave
    can_use_same_month = models.BooleanField(default=True)  # For monthly accrual rule
    
    # ADD THESE NEW FIELDS FOR STRICT RULES
    accrual_rate = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=0,
        help_text="Monthly accrual rate (e.g., 1.5 for annual leave)"
    )
    is_optional = models.BooleanField(
        default=False,
        help_text="Whether this is an optional leave type"
    )
    max_carry_forward = models.IntegerField(
        default=0,
        help_text="Maximum days that can be carried forward to next year"
    )
    can_use_same_month = models.BooleanField(
        default=True,
        help_text="Whether leave can be used in the same month it's accrued"
    )
    class Meta:
        db_table = 'leave_leavetype'

    def save(self, *args, **kwargs):
        # Set default values based on leave type
        if self.name == 'annual':
            self.accrual_rate = Decimal('1.5')
            self.max_carry_forward = 12
            self.can_use_same_month = False  # Cannot use in same month
        elif self.name == 'optional':
            self.is_optional = True
            self.accrual_rate = Decimal('0.33')  # 4 days per year ≈ 0.33 per month
            self.max_carry_forward = 0  # Optional leaves don't carry forward
        elif self.name == 'sick':
            self.max_carry_forward = 0  # Sick leaves typically don't carry forward
        elif self.name == 'casual':
            self.max_carry_forward = 0  # Casual leaves typically don't carry forward
        elif self.name == 'comp_off':
            self.max_carry_forward = 0  # Comp off typically expires
        
        super().save(*args, **kwargs)

    def __str__(self):
        return dict(self.LEAVE_TYPES)[self.name]
 

class Leave(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('new', 'New'),
    ]
    
    HALF_DAY_CHOICES = [
        ('first_half', 'First Half'),
        ('second_half', 'Second Half'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type = models.ForeignKey('LeaveType', on_delete=models.CASCADE)
    colour = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    
    # CHANGED: IntegerField to DecimalField to support 0.5 days
    days_requested = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        blank=True, 
        null=True
    )
    
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new')
    applied_date = models.DateTimeField(default=timezone.now)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_leaves'
    )

    approved_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # NEW FIELDS: Half-day support
    is_half_day = models.BooleanField(default=False)
    half_day_period = models.CharField(
        max_length=20, 
        choices=HALF_DAY_CHOICES, 
        null=True, 
        blank=True
    )

    def save(self, *args, **kwargs):
        if not self.days_requested:
            if self.is_half_day:
                self.days_requested = Decimal('0.5')
            else:
                self.days_requested = self.get_working_days()
        super().save(*args, **kwargs)

    def get_working_days(self):
        """Calculate working days excluding weekends and holidays"""
        # If it's a half day, return 0.5
        if self.is_half_day:
            return Decimal('0.5')
        
        total_days = (self.end_date - self.start_date).days + 1
        working_days = 0
        current_date = self.start_date
        
        # Get employee's region holidays
        holiday_dates = set()
        if hasattr(self.employee, 'location') and self.employee.location:
            try:
                region = Region.objects.filter(name__iexact=self.employee.location).first()
                if region:
                    holidays = Holiday.objects.filter(
                        region=region,
                        date__gte=self.start_date,
                        date__lte=self.end_date
                    )
                    holiday_dates = set(h.date for h in holidays)
            except:
                pass
        
        # Count working days (excluding weekends and holidays)
        while current_date <= self.end_date:
            # 5 = Saturday, 6 = Sunday
            if current_date.weekday() < 5 and current_date not in holiday_dates:
                working_days += 1
            current_date += timedelta(days=1)
        
        return Decimal(str(working_days))

    def __str__(self):
        half_day_info = ""
        if self.is_half_day:
            period_display = dict(self.HALF_DAY_CHOICES).get(self.half_day_period, '')
            half_day_info = f" ({period_display})"
        return f"{self.employee} - {self.leave_type} ({self.start_date} to {self.end_date}){half_day_info}"

    class Meta:
        ordering = ['-applied_date']

        
class LeaveBalance(models.Model):
    id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    total_leaves = models.IntegerField(default=0)
    leaves_taken = models.IntegerField(default=0)
    leaves_remaining = models.IntegerField(default=0)
    carry_forward = models.IntegerField(default=0)
    year = models.IntegerField(default=2025)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'leave_balances'
        managed = True
        unique_together = ['employee', 'leave_type', 'year']

    def __str__(self):
        return f"{self.employee.first_name} - {self.leave_type.name} ({self.year})"        