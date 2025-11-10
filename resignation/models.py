from django.db import models
from hr.models import Employee

class Resignation(models.Model):
    RESIGNATION_STATUS = [
        ('applied', 'Applied'),
        ('under_review', 'Under Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
        ('completed', 'Completed'),
    ]
    
    EXIT_STATUS = [
        ('serving_notice', 'Serving Notice Period'),
        ('notice_completed', 'Notice Period Completed'),
        ('immediate', 'Immediate Exit'),
        ('buyout', 'Notice Period Buyout'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    resignation_date = models.DateField()
    last_working_date = models.DateField()
    reason = models.TextField()
    feedback = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=RESIGNATION_STATUS, default='applied')
    exit_status = models.CharField(max_length=20, choices=EXIT_STATUS, default='serving_notice')
    
    # Approval workflow
    applied_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='resignations_received')
    approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='resignations_approved')
    approved_date = models.DateField(null=True, blank=True)
    
    # Notice period details
    notice_period_days = models.IntegerField(default=60)
    actual_notice_days = models.IntegerField(default=0)
    notice_period_start = models.DateField(null=True, blank=True)
    notice_period_end = models.DateField(null=True, blank=True)
    
    # Exit details
    exit_interview_date = models.DateField(null=True, blank=True)
    exit_interview_conducted_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='exit_interviews')
    exit_interview_notes = models.TextField(blank=True, null=True)
    
    # Financial details
    pending_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    pending_bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_settlement = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'resignation_resignation'
    
    def __str__(self):
        return f"{self.employee} - {self.resignation_date}"

class ResignationChecklist(models.Model):
    resignation = models.ForeignKey(Resignation, on_delete=models.CASCADE)
    task_name = models.CharField(max_length=200)
    department = models.CharField(max_length=100)
    assigned_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    due_date = models.DateField()
    completed = models.BooleanField(default=False)
    completed_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'resignation_checklist'

class ResignationDocument(models.Model):
    resignation = models.ForeignKey(Resignation, on_delete=models.CASCADE)
    document_type = models.CharField(max_length=100)
    document_file = models.FileField(upload_to='resignation_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'resignation_documents'
        
        
class ExitInterview(models.Model):
    resignation = models.OneToOneField(Resignation, on_delete=models.CASCADE)
   
    # Interview details
    interview_date = models.DateField(null=True, blank=True)
    conducted_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='exit_interviews_conducted')
   
    # Interview questions - Reasons for leaving
    reason_for_leaving = models.TextField(blank=True, null=True)
    concerns_shared_prior = models.TextField(blank=True, null=True)
    single_event_responsible = models.TextField(blank=True, null=True)
    new_company_offer = models.TextField(blank=True, null=True)
   
    # Company feedback
    valued_about_company = models.TextField(blank=True, null=True)
    disliked_about_company = models.TextField(blank=True, null=True)
   
    # Management feedback
    relationship_with_manager = models.TextField(blank=True, null=True)
    supervisor_improvement = models.TextField(blank=True, null=True)
   
    # Job feedback
    liked_about_job = models.TextField(blank=True, null=True)
    disliked_about_job = models.TextField(blank=True, null=True)
    job_improvement_suggestions = models.TextField(blank=True, null=True)
   
    # Resources and support
    resources_support = models.TextField(blank=True, null=True)
    employee_morale = models.TextField(blank=True, null=True)
   
    # Performance and goals
    clear_goals = models.TextField(blank=True, null=True)
    performance_feedback = models.TextField(blank=True, null=True)
   
    # Company commitment
    quality_commitment = models.TextField(blank=True, null=True)
    career_development = models.TextField(blank=True, null=True)
   
    # Recommendations
    workplace_recommendations = models.TextField(blank=True, null=True)
    policies_fairness = models.TextField(blank=True, null=True)
   
    # Success qualities
    success_qualities = models.TextField(blank=True, null=True)
    replacement_qualities = models.TextField(blank=True, null=True)
   
    # Compensation and benefits
    compensation_feedback = models.TextField(blank=True, null=True)
   
    # Future considerations
    future_considerations = models.TextField(blank=True, null=True)
    recommend_company = models.TextField(blank=True, null=True)
   
    # Additional comments
    additional_comments = models.TextField(blank=True, null=True)
   
    # Digital signatures
    employee_signature = models.TextField(blank=True, null=True)
    employee_signed_at = models.DateTimeField(null=True, blank=True)
    hr_signature = models.TextField(blank=True, null=True)
    hr_signed_at = models.DateTimeField(null=True, blank=True)
   
    # Status
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
   
    class Meta:
        db_table = 'resignation_exit_interview'
   
    def __str__(self):
        return f"Exit Interview - {self.resignation.employee.employee_id}"
    
    
    
    
class NoDueCertificate(models.Model):
    resignation = models.OneToOneField(Resignation, on_delete=models.CASCADE)
    
    # Employee acceptance
    employee_signature = models.TextField(blank=True, null=True, help_text="Digital signature of employee")
    employee_signed_at = models.DateTimeField(null=True, blank=True)
    employee_ip_address = models.CharField(max_length=100, blank=True, null=True)
    
    # HR approval
    hr_signature = models.TextField(blank=True, null=True, help_text="Digital signature of HR")
    hr_signed_at = models.DateTimeField(null=True, blank=True)
    hr_approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='no_due_certificates_approved')
    
    # Certificate details
    certificate_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    generated_date = models.DateField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    
    # Settlement details
    final_settlement_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    settlement_date = models.DateField(null=True, blank=True)
    settlement_mode = models.CharField(max_length=50, default='Online Transfer', choices=[
        ('online', 'Online Transfer/NEFT'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
    ])
    
    class Meta:
        db_table = 'resignation_no_due_certificate'
    
    def __str__(self):
        return f"No Due Certificate - {self.resignation.employee.employee_id}"
    
    def generate_certificate_number(self):
        if not self.certificate_number:
            self.certificate_number = f"NDC{self.resignation.employee.employee_id}{date.today().strftime('%Y%m%d')}"
        return self.certificate_number
