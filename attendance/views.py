from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.utils.timezone import localtime
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Attendance
from hr.models import Employee
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import inch
from datetime import datetime, date, time



# -------------------------------
# Custom Decorators
# -------------------------------

def login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('user_authenticated'):
            messages.error(request, 'Please login to access this page.')
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(allowed_roles):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            user_role = request.session.get('user_role')
            if not user_role or user_role not in allowed_roles:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('access_denied')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# -------------------------------
# Attendance Dashboard
# -------------------------------

@login_required
def attendance_dashboard(request):
    user_id = request.session.get('user_id')
    user_role = request.session.get('user_role')
    
    if user_role == 'ADMIN':
        messages.info(request, 'Admins can only view attendance.')
    
    employee = Employee.objects.get(id=user_id)
    today = timezone.now().date()
    today_attendance = Attendance.objects.filter(employee=employee, date=today).first()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'check_in':
            if today_attendance:
                messages.warning(request, 'You have already checked in today.')
            else:
                Attendance.objects.create(
                    employee=employee,
                    date=today,
                    check_in=timezone.now()
                )
                messages.success(request, 'Check-in successful!')
                return redirect('attendance:dashboard')
        
        elif action == 'check_out':
            if not today_attendance:
                messages.error(request, 'You need to check in first.')
            elif today_attendance.check_out:
                messages.warning(request, 'You have already checked out today.')
            else:
                today_attendance.check_out = timezone.now()
                today_attendance.save()
                messages.success(request, 'Check-out successful!')
                return redirect('attendance:dashboard')
                
    
    context = {
        'today_attendance': today_attendance,
        'employee': employee,
    }
    return render(request, 'attendance/dashboard.html', context)


# -------------------------------
# View All Attendance (Employee)
# -------------------------------

@login_required
def all_attendance(request):
    user_id = request.session.get('user_id')
    user_role = request.session.get('user_role')
    
    if user_role == 'ADMIN':
        messages.error(request, 'Admin users do not have attendance records.')
        return redirect('dashboard')
    
    employee = Employee.objects.get(id=user_id)
    attendance_list = Attendance.objects.filter(employee=employee).order_by('-date')
    
    # ✅ Add duration calculation for each record
    for record in attendance_list:
        if record.check_in and record.check_out:
            diff = record.check_out - record.check_in
            total_minutes = diff.total_seconds() / 60
            hours = int(total_minutes // 60)
            minutes = int(total_minutes % 60)
            if hours > 0 and minutes > 0:
                record.duration_display = f"{hours}h {minutes}m"
            elif hours > 0:
                record.duration_display = f"{hours} hours"
            else:
                record.duration_display = f"{minutes} minutes"
        elif record.check_in and not record.check_out:
            record.duration_display = "In Progress"
        else:
            record.duration_display = "-"

    paginator = Paginator(attendance_list, 15)
    page = request.GET.get('page')
    attendances = paginator.get_page(page)
    
    context = {
        'attendances': attendances,
        'employee': employee,
    }
    return render(request, 'attendance/all_attendance.html', context)


# -------------------------------
# Admin / HR Attendance Report
# -------------------------------

@login_required
@role_required(['ADMIN', 'HR', 'SUPER_ADMIN'])
def attendance_report(request):
    search_query = request.GET.get('search', '')
    department = request.GET.get('department', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    today = date.today()
    office_start_time = time(9, 30)  # 9:30 AM

    # Default: show today's attendance
    attendances = Attendance.objects.select_related('employee').filter(date=today)

    # Apply filters if provided
    if search_query or department or date_from or date_to:
        attendances = Attendance.objects.select_related('employee').all()

        if search_query:
            attendances = attendances.filter(
                Q(employee__first_name__icontains=search_query) |
                Q(employee__last_name__icontains=search_query) |
                Q(employee__employee_id__icontains=search_query)
            )

        if department:
            attendances = attendances.filter(employee__department=department)

        if date_from:
            attendances = attendances.filter(date__gte=date_from)

        if date_to:
            attendances = attendances.filter(date__lte=date_to)

    # ✅ Add punctuality field dynamically
    for att in attendances:
        if att.check_in:
            if att.check_in.time() <= office_start_time:
                att.punctuality = "On Time"
            else:
                att.punctuality = "Late"
        else:
            att.punctuality = "Absent"

    departments = Employee.objects.values_list('department', flat=True).distinct()
    paginator = Paginator(attendances.order_by('-date'), 20)
    page = request.GET.get('page')
    attendance_records = paginator.get_page(page)

    context = {
        'attendances': attendance_records,
        'departments': departments,
        'search_query': search_query,
        'selected_department': department,
        'date_from': date_from,
        'date_to': date_to,
        'today': today,
    }

    return render(request, 'attendance/report.html', context)


@login_required
@role_required(['ADMIN', 'HR', 'SUPER_ADMIN'])
def download_admin_attendance_report(request):
    """Generate PDF for all employees' attendance (times in IST)"""
    search_query = request.GET.get('search', '')
    department = request.GET.get('department', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # ✅ Filter data
    attendances = Attendance.objects.select_related('employee').all()
    if search_query:
        attendances = attendances.filter(
            Q(employee__first_name__icontains=search_query) |
            Q(employee__last_name__icontains=search_query) |
            Q(employee__employee_id__icontains=search_query)
        )
    if department:
        attendances = attendances.filter(employee__department=department)
    if date_from:
        attendances = attendances.filter(date__gte=date_from)
    if date_to:
        attendances = attendances.filter(date__lte=date_to)

    # ✅ Create response as PDF
    response = HttpResponse(content_type='application/pdf')
    filename = "Attendance_Report_All_Employees.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # PDF setup
    p = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)
    y = height - 80

    # Title
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width / 2, y, "IKONTEL HR SYSTEM - Attendance Report")
    y -= 30
    p.setFont("Helvetica", 11)
    # ✅ Generated On in IST
    p.drawCentredString(width / 2, y, f"Generated On: {localtime().strftime('%b %d, %Y %I:%M %p')}")
    y -= 40

    # Header Row
    p.setFont("Helvetica-Bold", 11)
    p.drawString(40, y, "Emp ID")
    p.drawString(120, y, "Name")
    p.drawString(250, y, "Dept")
    p.drawString(330, y, "Date")
    p.drawString(420, y, "Check-In")
    p.drawString(510, y, "Check-Out")
    p.drawString(600, y, "Status")
    p.drawString(680, y, "Duration")
    y -= 10
    p.line(35, y, width - 35, y)
    y -= 15

    # ✅ Data Rows
    p.setFont("Helvetica", 10)
    for a in attendances:
        if y < 60:  # Page break
            p.showPage()
            y = height - 60
            p.setFont("Helvetica", 10)

        # ✅ Convert to local time (IST)
        check_in_local = localtime(a.check_in).strftime("%I:%M %p") if a.check_in else "-"
        check_out_local = localtime(a.check_out).strftime("%I:%M %p") if a.check_out else "-"

        # Calculate status & duration
        if a.check_in and a.check_out:
            status = "Present"
            diff = a.check_out - a.check_in
            total_minutes = diff.total_seconds() / 60
            hours = int(total_minutes // 60)
            minutes = int(total_minutes % 60)
            duration = f"{hours}h {minutes}m"
        elif a.check_in:
            status = "Half Day"
            duration = "In Progress"
        else:
            status = "Absent"
            duration = "-"

        # ✅ Draw Data (now showing IST)
        p.drawString(40, y, a.employee.employee_id)
        p.drawString(120, y, f"{a.employee.first_name} {a.employee.last_name}")
        p.drawString(250, y, a.employee.department)
        p.drawString(330, y, a.date.strftime("%b %d, %Y"))
        p.drawString(420, y, check_in_local)
        p.drawString(510, y, check_out_local)
        p.drawString(600, y, status)
        p.drawString(680, y, duration)
        y -= 18

    # Footer
    p.setFont("Helvetica-Oblique", 9)
    y -= 10
    p.line(35, y, width - 35, y)
    y -= 20
    p.drawCentredString(width / 2, y, "Generated by IkonTel HRMS | Confidential Report")

    p.showPage()
    p.save()
    return response
# -------------------------------
# Generate Attendance Report PDF
# -------------------------------

@login_required
def download_attendance_report(request):
    user_id = request.session.get('user_id')
    employee = Employee.objects.get(id=user_id)
    attendances = Attendance.objects.filter(employee=employee).order_by('-date')

    # Create response as PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f"{employee.first_name}_attendance_report.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Initialize PDF
    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    y = height - 80

    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2, y, "IKONTEL HR SYSTEM")
    y -= 25
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2, y, f"Attendance Report - {employee.first_name} {employee.last_name}")
    y -= 30

    # Employee Info
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"Employee ID: {employee.employee_id}")
    p.drawString(300, y, f"Department: {employee.department}")
    y -= 20
    p.drawString(50, y, f"Designation: {employee.designation}")
    p.drawString(300, y, f"Generated On: {localtime().strftime('%b %d, %Y %I:%M %p')}")  # ✅ IST time
    y -= 40

    # Table Header
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, "Date")
    p.drawString(150, y, "Check-In")
    p.drawString(250, y, "Check-Out")
    p.drawString(350, y, "Status")
    p.drawString(450, y, "Duration")
    y -= 10
    p.line(45, y, 550, y)
    y -= 15

    # Table Rows
    p.setFont("Helvetica", 10)
    for a in attendances:
        if y < 80:  # Page break
            p.showPage()
            y = height - 80
            p.setFont("Helvetica", 10)

        # ✅ Convert UTC to local IST before printing
        check_in_local = localtime(a.check_in).strftime("%I:%M %p") if a.check_in else "-"
        check_out_local = localtime(a.check_out).strftime("%I:%M %p") if a.check_out else "-"

        # Calculate status
        if a.check_in and a.check_out:
            status = "Present"
        elif a.check_in and not a.check_out:
            status = "Half Day"
        else:
            status = "Absent"

        # Duration
        if a.check_in and a.check_out:
            diff = a.check_out - a.check_in
            total_minutes = diff.total_seconds() / 60
            hours = int(total_minutes // 60)
            minutes = int(total_minutes % 60)
            duration = f"{hours}h {minutes}m"
        elif a.check_in:
            duration = "In Progress"
        else:
            duration = "-"

        # ✅ Row Data (with local times)
        p.drawString(50, y, a.date.strftime("%b %d, %Y"))
        p.drawString(150, y, check_in_local)
        p.drawString(250, y, check_out_local)
        p.drawString(350, y, status)
        p.drawString(450, y, duration)
        y -= 20

    # Footer
    p.setFont("Helvetica-Oblique", 9)
    y -= 10
    p.line(45, y, 550, y)
    y -= 20
    p.drawCentredString(width / 2, y, "Generated by IkonTel HRMS | Confidential Employee Report")

    # Finalize PDF
    p.showPage()
    p.save()
    return response