from django.utils import timezone
from django.db import models

class Admin(models.Model):
    admin_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    role = models.CharField(max_length=100)
    profile_picture = models.CharField(max_length=255)
    password_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=8)  # 'active' or 'inactive'
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = True  
        db_table = 'hr_admin' 

class Employee(models.Model):
    id = models.AutoField(primary_key=True)
    employee_id = models.CharField(max_length=200)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    department = models.CharField(max_length=50)
    designation = models.CharField(max_length=50)
    role = models.CharField(
        max_length=20,
        choices=[('Employee','Employee'),('Manager','Manager'),('HR','HR'),('Admin','Admin'),('Super Admin','Super Admin')]
    )
    date_of_joining = models.DateField()
    reporting_manager = models.CharField(max_length=100)
    reporting_manager_id = models.CharField(max_length=50, blank=True, null=True)  # New field
    status = models.CharField(
        max_length=8,
        choices=[('active','active'), ('inactive','inactive')]
    )
    profile_picture = models.ImageField(upload_to="employees/", blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    location = models.CharField(max_length=145, blank=True, null=True)

    # Bank fields
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    ifsc_code = models.CharField(max_length=11, blank=True, null=True)
    probation_end_date = models.DateField(null=True,blank=True)
    
    class Meta:
        managed = True 
        db_table = 'hr_employee' 
    def save(self, *args, **kwargs):
        # Auto-calculate probation end date if not set and joining date exists
        if self.date_of_joining and not self.probation_end_date:
            from leave.services import ProbationService
            self.probation_end_date = ProbationService.calculate_probation_end_date(self.date_of_joining)
        
        if not self.created_at:
            self.created_at = timezone.now()
        self.updated_at = timezone.now()
        
        super().save(*args, **kwargs)   
    def _str_(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"
    
class EmployeePassword(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, primary_key=True)
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'hr_employeepassword' 
        
    def __str__(self):
        return f"Password for {self.employee.email}"


class EmployeeDocument(models.Model):
    DOCUMENT_TYPES = [
        ('educational', 'Educational Certificate'),
        ('pan', 'PAN Card'),
        ('aadhaar', 'Aadhaar Card'),
        ('passbook', 'Bank Passbook'),
        ('offer_letter', 'Offer Letter'),
        ('salary_slip', 'Salary Slip'),
        ('bank_statement', 'Bank Statement'),
        ('experience_letter', 'Experience/Relieving Letter'),
    ]
    
    id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    document_number = models.CharField(max_length=100, blank=True, null=True)  # For PAN, Aadhaar
    file = models.FileField(upload_to="employee_documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        managed = True
        db_table = 'hr_employee_documents'

    def __str__(self):
        return f"{self.employee.employee_id} - {self.get_document_type_display()}"    