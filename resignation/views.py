from django.shortcuts import render, redirect, get_object_or_404
from django.db import models
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from datetime import date, timedelta
from datetime import date, timedelta, datetime
from django.utils import timezone
from .models import ExitInterview, NoDueCertificate, Resignation, ResignationChecklist, ResignationDocument
from hr.models import Employee
from django.template.loader import render_to_string
from xhtml2pdf import pisa
import io

def resignation_dashboard(request):
    """Comprehensive resignation dashboard with WOW features"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    
    # Statistics
    total_resignations = Resignation.objects.count()
    pending_resignations = Resignation.objects.filter(status='applied').count()
    active_notice = Resignation.objects.filter(exit_status='serving_notice').count()
    completed_this_month = Resignation.objects.filter(
        status='completed',
        created_at__month=date.today().month,
        created_at__year=date.today().year
    ).count()
    
    # Recent resignations with employee details
    recent_resignations = Resignation.objects.select_related('employee').order_by('-created_at')[:10]
    
    # For employees, show only their resignation
    my_resignation = None
    if user_role == 'EMPLOYEE':
        try:
            employee = Employee.objects.get(email=user_email)
            my_resignation = Resignation.objects.filter(employee=employee).first()
        except Employee.DoesNotExist:
            pass
    
    context = {
        'total_resignations': total_resignations,
        'pending_resignations': pending_resignations,
        'active_notice': active_notice,
        'completed_this_month': completed_this_month,
        'recent_resignations': recent_resignations,
        'my_resignation': my_resignation,
        'user_role': user_role,
        'today_date': date.today(),
    }
    return render(request, 'resignation/dashboard.html', context)

def submit_resignation(request):
    """Employee submits resignation with automatic calculations"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(email=request.session.get('user_email'))
            resignation_date = request.POST.get('resignation_date')
            last_working_date = request.POST.get('last_working_date')
            reason = request.POST.get('reason')
            
            # Convert dates
            resignation_date_obj = datetime.strptime(resignation_date, '%Y-%m-%d').date()
            last_working_date_obj = datetime.strptime(last_working_date, '%Y-%m-%d').date()
            
            # Calculate notice period with safe default
            notice_days = (last_working_date_obj - resignation_date_obj).days
            
            # Use employee's notice period or default to 60 days
            employee_notice_period = getattr(employee, 'notice_period_days', 60)
            if employee_notice_period is None:
                employee_notice_period = 60
                
            actual_notice_days = min(notice_days, employee_notice_period)
            
            # Get reporting manager safely - FIXED VERSION
            applied_to = None
            if hasattr(employee, 'reporting_manager_id') and employee.reporting_manager_id:
                try:
                    applied_to = Employee.objects.get(employee_id=employee.reporting_manager_id)
                except Employee.DoesNotExist:
                    pass
            
            # If no reporting manager found, try to get from reporting_manager field
            if not applied_to and hasattr(employee, 'reporting_manager') and employee.reporting_manager:
                try:
                    # Try to find manager by name (fallback)
                    manager_name = employee.reporting_manager
                    if ' (' in manager_name:
                        manager_name = manager_name.split(' (')[0]
                    
                    # Try to find by first name and last name
                    name_parts = manager_name.split(' ')
                    if len(name_parts) >= 2:
                        applied_to = Employee.objects.filter(
                            first_name=name_parts[0],
                            last_name=name_parts[1],
                            status='active'
                        ).first()
                except:
                    pass
            
            # Final fallback - get any HR/Admin user
            if not applied_to:
                try:
                    applied_to = Employee.objects.filter(
                        role__in=['HR', 'ADMIN', 'SUPER ADMIN'],
                        status='active'
                    ).first()
                except:
                    applied_to = None
            
            resignation = Resignation(
                employee=employee,
                resignation_date=resignation_date_obj,
                last_working_date=last_working_date_obj,
                reason=reason,
                applied_to=applied_to,  # This should now be an Employee object or None
                notice_period_days=employee_notice_period,
                actual_notice_days=actual_notice_days,
                notice_period_start=resignation_date_obj,
                notice_period_end=last_working_date_obj
            )
            resignation.save()
            
            # Auto-create comprehensive checklist
            create_resignation_checklist(resignation)
            
            messages.success(request, '🎉 Resignation submitted successfully! HR will review your application.')
            return redirect('resignation:dashboard')
            
        except Exception as e:
            messages.error(request, f'Error submitting resignation: {str(e)}')
            print(f"Resignation submission error: {str(e)}")  # For debugging
    
    # GET request - show form
    try:
        employee = Employee.objects.get(email=request.session.get('user_email'))
        # Safe defaults for notice period
        employee_notice_period = getattr(employee, 'notice_period_days', 60)
        if employee_notice_period is None:
            employee_notice_period = 60
            
        min_date = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        max_date = (date.today() + timedelta(days=employee_notice_period)).strftime('%Y-%m-%d')
    except Employee.DoesNotExist:
        min_date = date.today().strftime('%Y-%m-%d')
        max_date = (date.today() + timedelta(days=60)).strftime('%Y-%m-%d')
        employee_notice_period = 60
    
    context = {
        'min_date': min_date,
        'max_date': max_date,
        'notice_period': employee_notice_period,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/submit_resignation.html', context)

def create_resignation_checklist(resignation):
    """Auto-create comprehensive exit checklist"""
    checklist_items = [
        {'task': 'Exit Interview Scheduling', 'department': 'HR', 'days': 2},
        {'task': 'Knowledge Transfer Documentation', 'department': 'Department', 'days': 7},
        {'task': 'Project Handover', 'department': 'Department', 'days': 5},
        {'task': 'Laptop & Asset Return', 'department': 'IT', 'days': 1},
        {'task': 'ID Card Surrender', 'department': 'HR', 'days': 1},
        {'task': 'Email Account Deactivation', 'department': 'IT', 'days': 0},
        {'task': 'Access Card Deactivation', 'department': 'Admin', 'days': 0},
        {'task': 'Final Salary Processing', 'department': 'Finance', 'days': 3},
        {'task': 'Experience Letter Preparation', 'department': 'HR', 'days': 5},
        {'task': 'Clear Dues from Departments', 'department': 'Finance', 'days': 2},
    ]
    
    for item in checklist_items:
        ResignationChecklist.objects.create(
            resignation=resignation,
            task_name=item['task'],
            department=item['department'],
            due_date=resignation.last_working_date - timedelta(days=item['days'])
        )

def all_resignations(request):
    """View all resignations with advanced filters"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignations = Resignation.objects.select_related('employee', 'applied_to', 'approved_by').all()
    
    # Advanced filters
    status_filter = request.GET.get('status')
    department_filter = request.GET.get('department')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if status_filter:
        resignations = resignations.filter(status=status_filter)
    if department_filter:
        resignations = resignations.filter(employee__department=department_filter)
    if date_from:
        resignations = resignations.filter(resignation_date__gte=date_from)
    if date_to:
        resignations = resignations.filter(resignation_date__lte=date_to)
    
    # Search
    search_query = request.GET.get('search')
    if search_query:
        resignations = resignations.filter(
            Q(employee__first_name__icontains=search_query) |
            Q(employee__last_name__icontains=search_query) |
            Q(employee__employee_id__icontains=search_query) |
            Q(reason__icontains=search_query)
        )
    
    context = {
        'resignations': resignations.order_by('-created_at'),
        'status_choices': Resignation.RESIGNATION_STATUS,
        'departments': Employee.objects.values_list('department', flat=True).distinct(),
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/all_resignations.html', context)

def my_resignation(request):
    """Employee views their own resignation"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    try:
        employee = Employee.objects.get(email=request.session.get('user_email'))
        resignation = Resignation.objects.filter(employee=employee).first()
        checklist = ResignationChecklist.objects.filter(resignation=resignation) if resignation else []
        documents = ResignationDocument.objects.filter(resignation=resignation) if resignation else []
    except Employee.DoesNotExist:
        resignation = None
        checklist = []
        documents = []
    
    context = {
        'resignation': resignation,
        'checklist': checklist,
        'documents': documents,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/my_resignation.html', context)

def resignation_detail(request, resignation_id):
    """Detailed view of resignation with full workflow"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignation = get_object_or_404(
        Resignation.objects.select_related('employee', 'applied_to', 'approved_by', 'exit_interview_conducted_by'),
        id=resignation_id
    )
    checklist = ResignationChecklist.objects.filter(resignation=resignation).select_related('assigned_to')
    documents = ResignationDocument.objects.filter(resignation=resignation)
    
    # Check permissions
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    
    if user_role == 'EMPLOYEE' and resignation.employee.email != user_email:
        messages.error(request, 'You can only view your own resignation details.')
        return redirect('access_denied')
    
    context = {
        'resignation': resignation,
        'checklist': checklist,
        'documents': documents,
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
        'today_date': date.today(),
    }
    return render(request, 'resignation/resignation_detail.html', context)

def approve_resignation(request, resignation_id):
    """Approve/reject resignation with workflow"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        resignation = get_object_or_404(Resignation, id=resignation_id)
        action = request.POST.get('action')
        remarks = request.POST.get('remarks', '')
        
        try:
            approver = Employee.objects.get(email=request.session.get('user_email'))
            
            if action == 'approve':
                resignation.status = 'accepted'
                resignation.approved_by = approver
                resignation.approved_date = date.today()
                resignation.feedback = remarks
                messages.success(request, '✅ Resignation approved successfully!')
                
            elif action == 'reject':
                resignation.status = 'rejected'
                resignation.feedback = remarks
                messages.success(request, '❌ Resignation rejected!')
            
            elif action == 'schedule_exit':
                interview_date = request.POST.get('interview_date')
                if interview_date:
                    resignation.exit_interview_date = interview_date
                    resignation.exit_interview_conducted_by = approver
                    messages.success(request, '📅 Exit interview scheduled!')
            
            resignation.save()
            
        except Exception as e:
            messages.error(request, f'Error processing resignation: {str(e)}')
    
    return redirect('resignation:resignation_detail', resignation_id=resignation_id)

def update_checklist(request, checklist_id):
    """Update checklist item status"""
    if not request.session.get('user_authenticated'):
        return JsonResponse({'success': False, 'error': 'Not authenticated'})
    
    if request.method == 'POST':
        try:
            checklist_item = get_object_or_404(ResignationChecklist, id=checklist_id)
            completed = request.POST.get('completed') == 'true'
            remarks = request.POST.get('remarks', '')
            
            checklist_item.completed = completed
            checklist_item.completed_date = date.today() if completed else None
            checklist_item.remarks = remarks
            checklist_item.save()
            
            return JsonResponse({'success': True, 'completed': completed})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'})

def resignation_analytics(request):
    """Advanced analytics for resignations"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    # Monthly trends
    current_year = date.today().year
    monthly_data = []
    for month in range(1, 13):
        count = Resignation.objects.filter(
            created_at__year=current_year,
            created_at__month=month
        ).count()
        monthly_data.append(count)
    
    # Department-wise analysis
    dept_data = []
    departments = Employee.objects.values_list('department', flat=True).distinct()
    for dept in departments:
        if dept:
            count = Resignation.objects.filter(employee__department=dept).count()
            dept_data.append({'department': dept, 'count': count})
    
    # Reason analysis
    reasons = Resignation.objects.values('reason').annotate(count=models.Count('id')).order_by('-count')[:10]
    
    # Calculate totals for templates
    total_reasons = sum(reason['count'] for reason in reasons)
    total_dept_count = sum(dept['count'] for dept in dept_data)
    
    context = {
        'monthly_data': monthly_data,
        'dept_data': dept_data,
        'reasons': reasons,
        'total_reasons': total_reasons,
        'total_dept_count': total_dept_count,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/analytics.html', context)


def no_due_certificate(request, resignation_id):
    """Generate and manage No Due Certificate"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignation = get_object_or_404(Resignation, id=resignation_id)
    
    # Get or create No Due Certificate
    no_due_cert, created = NoDueCertificate.objects.get_or_create(
        resignation=resignation,
        defaults={
            'final_settlement_amount': resignation.final_settlement,
            'settlement_date': resignation.last_working_date,
        }
    )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'employee_sign':
            # Employee digital signature
            signature_data = request.POST.get('signature_data')
            if signature_data:
                no_due_cert.employee_signature = signature_data
                no_due_cert.employee_signed_at = timezone.now()
                no_due_cert.employee_ip_address = get_client_ip(request)
                no_due_cert.save()
                messages.success(request, '✅ Digital signature submitted successfully!')
                
        elif action == 'hr_approve':
            # HR approval and signature
            if request.session.get('user_role') in ['HR', 'ADMIN', 'SUPER_ADMIN']:
                signature_data = request.POST.get('hr_signature_data')
                if signature_data:
                    try:
                        hr_employee = Employee.objects.get(email=request.session.get('user_email'))
                        no_due_cert.hr_signature = signature_data
                        no_due_cert.hr_signed_at = timezone.now()
                        no_due_cert.hr_approved_by = hr_employee
                        no_due_cert.is_completed = True
                        no_due_cert.generate_certificate_number()
                        no_due_cert.save()
                        messages.success(request, '✅ No Due Certificate approved and completed!')
                    except Employee.DoesNotExist:
                        messages.error(request, 'HR employee not found.')
        
        elif action == 'update_settlement':
            # Update settlement details
            settlement_amount = request.POST.get('settlement_amount')
            settlement_date = request.POST.get('settlement_date')
            settlement_mode = request.POST.get('settlement_mode')
            
            if settlement_amount:
                no_due_cert.final_settlement_amount = settlement_amount
            if settlement_date:
                no_due_cert.settlement_date = settlement_date
            if settlement_mode:
                no_due_cert.settlement_mode = settlement_mode
            no_due_cert.save()
            messages.success(request, 'Settlement details updated!')
        
        return redirect('resignation:no_due_certificate', resignation_id=resignation_id)
    
    context = {
        'resignation': resignation,
        'no_due_cert': no_due_cert,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/no_due_certificate.html', context)

def download_no_due_certificate(request, resignation_id):
    """Download No Due Certificate as PDF"""
    resignation = get_object_or_404(Resignation, id=resignation_id)
    no_due_cert = get_object_or_404(NoDueCertificate, resignation=resignation)
    
    context = {
        'resignation': resignation,
        'no_due_cert': no_due_cert,
    }
    
    # Render HTML template
    html_string = render_to_string('resignation/certificate_pdf.html', context)
    
    # Create PDF
    result = io.BytesIO()
    pdf = pisa.CreatePDF(io.StringIO(html_string), dest=result)
    
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        filename = f"no_due_certificate_{resignation.employee.employee_id}_{date.today()}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    else:
        return HttpResponse('Error generating PDF: ' + str(pdf.err))

def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def exit_interview(request, resignation_id):
    """Exit Interview form with digital signature"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    resignation = get_object_or_404(Resignation, id=resignation_id)
    
    # Get or create Exit Interview
    exit_interview_obj, created = ExitInterview.objects.get_or_create(
        resignation=resignation
    )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save_interview':
            # Save all interview responses
            exit_interview_obj.reason_for_leaving = request.POST.get('reason_for_leaving')
            exit_interview_obj.concerns_shared_prior = request.POST.get('concerns_shared_prior')
            exit_interview_obj.single_event_responsible = request.POST.get('single_event_responsible')
            exit_interview_obj.new_company_offer = request.POST.get('new_company_offer')
            exit_interview_obj.valued_about_company = request.POST.get('valued_about_company')
            exit_interview_obj.disliked_about_company = request.POST.get('disliked_about_company')
            exit_interview_obj.relationship_with_manager = request.POST.get('relationship_with_manager')
            exit_interview_obj.supervisor_improvement = request.POST.get('supervisor_improvement')
            exit_interview_obj.liked_about_job = request.POST.get('liked_about_job')
            exit_interview_obj.disliked_about_job = request.POST.get('disliked_about_job')
            exit_interview_obj.job_improvement_suggestions = request.POST.get('job_improvement_suggestions')
            exit_interview_obj.resources_support = request.POST.get('resources_support')
            exit_interview_obj.employee_morale = request.POST.get('employee_morale')
            exit_interview_obj.clear_goals = request.POST.get('clear_goals')
            exit_interview_obj.performance_feedback = request.POST.get('performance_feedback')
            exit_interview_obj.quality_commitment = request.POST.get('quality_commitment')
            exit_interview_obj.career_development = request.POST.get('career_development')
            exit_interview_obj.workplace_recommendations = request.POST.get('workplace_recommendations')
            exit_interview_obj.policies_fairness = request.POST.get('policies_fairness')
            exit_interview_obj.success_qualities = request.POST.get('success_qualities')
            exit_interview_obj.replacement_qualities = request.POST.get('replacement_qualities')
            exit_interview_obj.compensation_feedback = request.POST.get('compensation_feedback')
            exit_interview_obj.future_considerations = request.POST.get('future_considerations')
            exit_interview_obj.recommend_company = request.POST.get('recommend_company')
            exit_interview_obj.additional_comments = request.POST.get('additional_comments')
            
            # Set interview date if conducted by HR
            if request.session.get('user_role') in ['HR', 'ADMIN', 'SUPER_ADMIN']:
                exit_interview_obj.interview_date = date.today()
                try:
                    exit_interview_obj.conducted_by = Employee.objects.get(email=request.session.get('user_email'))
                except Employee.DoesNotExist:
                    pass
            
            exit_interview_obj.save()
            messages.success(request, '✅ Exit Interview responses saved successfully!')
            
        elif action == 'employee_sign':
            # Employee digital signature
            signature_data = request.POST.get('signature_data')
            if signature_data:
                exit_interview_obj.employee_signature = signature_data
                exit_interview_obj.employee_signed_at = timezone.now()
                exit_interview_obj.save()
                messages.success(request, '✅ Digital signature submitted successfully!')
                
        elif action == 'hr_sign':
            # HR digital signature
            if request.session.get('user_role') in ['HR', 'ADMIN', 'SUPER_ADMIN']:
                signature_data = request.POST.get('hr_signature_data')
                if signature_data:
                    exit_interview_obj.hr_signature = signature_data
                    exit_interview_obj.hr_signed_at = timezone.now()
                    exit_interview_obj.is_completed = True
                    exit_interview_obj.save()
                    messages.success(request, '✅ Exit Interview completed and signed!')
        
        return redirect('resignation:exit_interview', resignation_id=resignation_id)
    
    context = {
        'resignation': resignation,
        'exit_interview': exit_interview_obj,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'resignation/exit_interview.html', context)

def download_exit_interview(request, resignation_id):
    """Download Exit Interview as PDF"""
    resignation = get_object_or_404(Resignation, id=resignation_id)
    exit_interview_obj = get_object_or_404(ExitInterview, resignation=resignation)
    
    context = {
        'resignation': resignation,
        'exit_interview': exit_interview_obj,
    }
    
    return render(request, 'resignation/exit_interview_pdf.html', context)