from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db.models import Count, Q ,Sum
from django.utils import timezone
from datetime import date, datetime, timedelta
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Leave, LeaveType, Region, Holiday ,LeaveBalance
from hr.models import Employee
from calendar import monthrange

# IMPORT THE NEW SERVICES
from .services import (
    LeaveValidationService, 
    ProbationService, 
    OptionalLeaveService,
    LeaveAccrualService,
    initialize_employee_leave_balances
)

def leave_dashboard(request):
    """Main dashboard view with leave statistics"""
    # Check authentication via session
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    user_role = request.session.get('user_role')
    is_hr_admin_manager = user_role in ['HR', 'Admin', 'Manager','Super Admin']
    
    today = timezone.now().date()
    current_year = today.year
    
    # Get logged-in user's region/location
    user_email = request.session.get('user_email')
    user_region = None
    default_region_id = None
    
    
    try:
        # Try to get employee's location
        employee = Employee.objects.get(email=user_email)
        if employee.location:
            # Find matching region by location name
            region = Region.objects.filter(
                Q(name__iexact=employee.location) | 
                Q(code__iexact=employee.location),
                is_active=True
            ).first()
            if region:
                user_region = region
                default_region_id = region.id
    except Employee.DoesNotExist:
        pass
    
    # Calculate statistics
    total_employees = Employee.objects.count()
    
    # Today Present (employees not on leave today)
    employees_on_leave_today = Leave.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
        status='approved'
    ).values_list('employee_id', flat=True)
    
    today_present = total_employees - len(set(employees_on_leave_today))
    today_present_percentage = int((today_present / total_employees) * 100) if total_employees > 0 else 0
    
    # Planned Leaves (approved leaves starting in future)
    planned_leaves = Leave.objects.filter(
        start_date__gt=today,
        status='approved'
    ).count()
    planned_leaves_percentage = int((planned_leaves / total_employees) * 20) if total_employees > 0 else 0
    
    # Unplanned Leaves (pending or new leaves)
    unplanned_leaves = Leave.objects.filter(
        status__in=['pending', 'new']
    ).count()
    unplanned_leaves_percentage = int((unplanned_leaves / total_employees) * 50) if total_employees > 0 else 0
    
    # Pending Requests
    pending_requests = Leave.objects.filter(
        status__in=['pending', 'new']
    ).count()
    pending_requests_percentage = int((pending_requests / total_employees) * 70) if total_employees > 0 else 0
    
    # Recent leaves for the table
    # recent_leaves = Leave.objects.select_related('employee', 'leave_type').all()[:10]
    # Get user role and department from session
    user_role = request.session.get('user_role')          
    user_department = request.session.get('user_department') 
    # print(user_role)
    # print(user_department)
    # print(request.session.items())
    
    # if user_role == 'MANAGER' and user_department:recent_leaves = Leave.objects.select_related('employee', 'leave_type') \
    #     .filter(employee__department=user_department)[:10]
    # else:
    #     recent_leaves = Leave.objects.select_related('employee', 'leave_type').all()[:10]
    
    
     # 🔹 Handle date filtering (from query params)
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    recent_leaves = Leave.objects.select_related('employee', 'leave_type')

    if user_role == 'MANAGER' and request.session.get('user_department'):
        recent_leaves = recent_leaves.filter(employee__department=request.session.get('user_department'))

    # 🔹 Apply date filter
    if from_date and to_date:
        try:
            start = datetime.strptime(from_date, '%Y-%m-%d').date()
            end = datetime.strptime(to_date, '%Y-%m-%d').date()
            recent_leaves = recent_leaves.filter(applied_date__range=[start, end])
        except ValueError:
            pass
    elif from_date:
        recent_leaves = recent_leaves.filter(applied_date__gte=from_date)
    elif to_date:
        recent_leaves = recent_leaves.filter(applied_date__lte=to_date)

    recent_leaves = recent_leaves.order_by('-applied_date')[:50]  # limit for performance
    
    # Get all active regions with their holidays for current year
    regions = Region.objects.filter(is_active=True).prefetch_related(
        'holidays'
    ).order_by('name')
    
    # Get all holidays for current year
    holidays = Holiday.objects.filter(
        date__year=current_year
    ).select_related('region').order_by('date')
    
    context = {
        'is_hr_admin_manager': is_hr_admin_manager,
        'today_present': today_present,
        'today_present_total': total_employees,
        'today_present_percentage': today_present_percentage,
        
        'planned_leaves': planned_leaves,
        'planned_leaves_total': total_employees,
        'planned_leaves_percentage': planned_leaves_percentage,
        
        'unplanned_leaves': unplanned_leaves,
        'unplanned_leaves_total': total_employees,
        'unplanned_leaves_percentage': unplanned_leaves_percentage,
        
        'pending_requests': pending_requests,
        'pending_requests_total': total_employees,
        'pending_requests_percentage': pending_requests_percentage,
        
        'recent_leaves': recent_leaves,
        'current_year': current_year,
        'regions': regions,
        'holidays': holidays,
        'user_region': user_region,
        'default_region_id': default_region_id,  # Pass default region to template
    }
    
    return render(request, 'leave/leave_dashboard.html', context)

def leave_list(request):
    """List all leaves with comprehensive filtering options"""
    # Check authentication
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    leaves = Leave.objects.select_related(
        'employee',
        'leave_type',
        'approved_by'
    ).all()
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        leaves = leaves.filter(status=status_filter)
    
    # Filter by leave type
    leave_type_filter = request.GET.get('leave_type')
    if leave_type_filter:
        leaves = leaves.filter(leave_type_id=leave_type_filter)
    
    # Filter by region (using location field from Employee)
    region_filter = request.GET.get('region')
    if region_filter:
        leaves = leaves.filter(employee__location=region_filter)
    
    # Filter by department
    department_filter = request.GET.get('department')
    if department_filter:
        leaves = leaves.filter(employee__department=department_filter)
    
    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            leaves = leaves.filter(start_date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            leaves = leaves.filter(end_date__lte=date_to_obj)
        except ValueError:
            pass
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        leaves = leaves.filter(
            Q(employee__first_name__icontains=search_query) |
            Q(employee__last_name__icontains=search_query) |
            Q(employee__employee_id__icontains=search_query) |
            Q(reason__icontains=search_query)
        )
    
    # Sort functionality
    sort_by = request.GET.get('sort', '-applied_date')
    if sort_by:
        leaves = leaves.order_by(sort_by)
    
    # Pagination
    paginator = Paginator(leaves, 20)
    page_number = request.GET.get('page', 1)
    leaves_page = paginator.get_page(page_number)
    
    # Get filter options
    leave_types = LeaveType.objects.all()
    regions = Region.objects.filter(is_active=True)
    departments = Employee.objects.values_list('department', flat=True).distinct().order_by('department')
    
    context = {
        'leaves': leaves_page,
        'leave_types': leave_types,
        'regions': regions,
        'departments': departments,
        'status_choices': Leave.STATUS_CHOICES,
        
        # Current filters
        'current_status': status_filter,
        'current_leave_type': leave_type_filter,
        'current_region': region_filter,
        'current_department': department_filter,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
        'sort_by': sort_by,
        
        # Statistics
        'total_leaves': leaves.count(),
        'pending_count': Leave.objects.filter(status='pending').count(),
        'approved_count': Leave.objects.filter(status='approved').count(),
        'rejected_count': Leave.objects.filter(status='rejected').count(),
    }
    
    return render(request, 'leave/leave_list.html', context)

def calculate_working_days(start_date, end_date):
    """
    Calculate working days between two dates, excluding weekends.
    You can also add holiday exclusion logic here.
    """
    if start_date > end_date:
        return 0
    
    working_days = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Check if it's a weekday (Monday=0, Sunday=6)
        if current_date.weekday() < 5:  # Monday to Friday
            working_days += 1
        current_date += timedelta(days=1)
    
    return working_days

def apply_leave(request):
    user_email = request.session.get('user_email')
    user_role = request.session.get('user_role')
    
    try:
        employee = Employee.objects.get(email=user_email)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('employee_dashboard')
    
    if request.method == 'POST':
        try:
            leave_type_id = request.POST.get('leave_type')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            reason = request.POST.get('reason')
            
            # Validate required fields
            if not all([leave_type_id, start_date, end_date, reason]):
                messages.error(request, 'Please fill in all required fields.')
                return redirect('apply_leave')
            
            # Get half-day data from form
            is_half_day = request.POST.get('is_half_day', 'false') == 'true'
            half_day_period = request.POST.get('half_day_period', '')
            total_days_str = request.POST.get('total_days', '0')
            
            # Validate and parse dates
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                messages.error(request, 'Invalid date format. Please select valid dates.')
                return redirect('apply_leave')
            
            if start_date_obj > end_date_obj:
                messages.error(request, 'Start date cannot be after end date.')
                return redirect('apply_leave')
            
            if start_date_obj < date.today():
                messages.error(request, 'Cannot apply for leave in the past.')
                return redirect('apply_leave')
            
            # Validate half-day period selection
            if is_half_day and not half_day_period:
                messages.error(request, 'Please select first half or second half for half-day leave.')
                return redirect('apply_leave')
            
            # Convert total_days from form (frontend calculated)
            try:
                total_days = Decimal(total_days_str)
            except:
                total_days = Decimal('0')
            
            # Debug logging
            print(f"DEBUG: is_half_day={is_half_day}, total_days={total_days}, total_days_str={total_days_str}")
            
            # If total_days is still 0, recalculate on backend
            if total_days <= 0:
                if is_half_day:
                    total_days = Decimal('0.5')
                else:
                    # Backend calculation as fallback
                    from datetime import timedelta
                    working_days = 0
                    current_date = start_date_obj
                    while current_date <= end_date_obj:
                        # Monday=0, Sunday=6
                        if current_date.weekday() < 5:  # Monday to Friday
                            working_days += 1
                        current_date += timedelta(days=1)
                    total_days = Decimal(str(working_days))
            
            # Final check
            if total_days <= 0:
                messages.error(request, 'No working days in the selected date range. Please check your dates.')
                return redirect('apply_leave')
            
            # Get leave type
            try:
                leave_type = LeaveType.objects.get(id=leave_type_id)
            except LeaveType.DoesNotExist:
                messages.error(request, 'Invalid leave type selected.')
                return redirect('apply_leave')
            
            # NEW: VALIDATE LEAVE USING STRICT RULES SERVICE
            is_valid, errors, warnings = LeaveValidationService.validate_leave_application(
                employee, leave_type, start_date_obj, end_date_obj, total_days
            )
            
            if not is_valid:
                for error in errors:
                    messages.error(request, error)
                return redirect('apply_leave')
            
            # Show warnings if any
            for warning in warnings:
                messages.warning(request, warning)
            
            # Check leave balance (additional check)
            try:
                balance = LeaveBalance.objects.get(
                    employee=employee, 
                    leave_type=leave_type,
                    year=date.today().year
                )
                
                # Check if sufficient balance
                if Decimal(str(balance.leaves_remaining)) < total_days:
                    messages.error(
                        request, 
                        f'Insufficient {leave_type.get_name_display()} balance. '
                        f'Available: {balance.leaves_remaining} days, Requested: {total_days} days'
                    )
                    return redirect('apply_leave')
                    
            except LeaveBalance.DoesNotExist:
                messages.error(request, 'Leave balance not found for this leave type.')
                return redirect('apply_leave')
            
            # Get leave type color (with fallback)
            leave_colour = getattr(leave_type, 'colour', '#667eea')
            if not leave_colour:
                leave_colour = '#667eea'
            
            # Create leave application
            leave = Leave(
                employee=employee,
                leave_type=leave_type,
                colour=leave_colour,
                start_date=start_date_obj,
                end_date=end_date_obj,
                days_requested=total_days,
                reason=reason,
                status='pending',
                applied_date=timezone.now(),
                is_half_day=is_half_day,
                half_day_period=half_day_period if is_half_day else None
            )
            
            # Save the leave (don't deduct balance yet - wait for approval)
            leave.save()
            
            # Success message with details
            if is_half_day:
                period_display = "First Half" if half_day_period == "first_half" else "Second Half"
                messages.success(
                    request, 
                    f'Half-day leave application ({period_display}) submitted successfully for {start_date_obj.strftime("%d %b %Y")}! '
                    f'Waiting for approval.'
                )
            else:
                messages.success(
                    request, 
                    f'Leave application for {total_days} days submitted successfully! '
                    f'Waiting for approval.'
                )
            
            return redirect('leave_history')
            
        except Exception as e:
            messages.error(request, f'Error applying for leave: {str(e)}')
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Leave application error for {user_email}: {str(e)}", exc_info=True)
            return redirect('apply_leave')
    
    # GET request - show form
    leave_types = LeaveType.objects.filter(is_active=True)
    
    # Get leave balances for current year
    leave_balances = LeaveBalance.objects.filter(
        employee=employee, 
        year=date.today().year
    ).select_related('leave_type')
    
    # NEW: Check probation status
    is_on_probation = ProbationService.is_on_probation(employee)
    probation_message = None
    if is_on_probation:
        probation_message = "You are currently on probation. Only sick and maternity leaves are allowed."
    
    context = {
        'leave_types': leave_types,
        'leave_balances': leave_balances,
        'today_date': date.today(),
        'min_date': date.today().strftime('%Y-%m-%d'),
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
        'is_on_probation': is_on_probation,
        'probation_message': probation_message,
    }
    return render(request, 'leave/apply_leave.html', context)

def approve_leave(request, leave_id):
    """Approve or reject a leave application with strict rules validation"""
    # Check authentication
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        leave = get_object_or_404(Leave, id=leave_id)
        action = request.POST.get('action')
        rejection_reason = request.POST.get('rejection_reason', '')
        
        if action == 'approve':
            # FINAL VALIDATION BEFORE APPROVAL
            is_valid, errors, warnings = LeaveValidationService.validate_leave_application(
                leave.employee, 
                leave.leave_type, 
                leave.start_date, 
                leave.end_date, 
                leave.days_requested
            )
            
            if not is_valid:
                for error in errors:
                    messages.error(request, f"Cannot approve leave: {error}")
                return redirect(request.META.get('HTTP_REFERER', 'leave_dashboard'))
            
            # Deduct leave balance
            success = LeaveValidationService.deduct_leave_balance(
                leave.employee,
                leave.leave_type,
                leave.days_requested,
                leave.start_date.year
            )
            
            if not success:
                messages.error(request, 'Error deducting leave balance. Please check available balance.')
                return redirect(request.META.get('HTTP_REFERER', 'leave_dashboard'))
            
            leave.status = 'approved'
            leave.approved_date = timezone.now()
            messages.success(request, f'Leave approved for {leave.employee.first_name} {leave.employee.last_name}')
            
        elif action == 'reject':
            leave.status = 'rejected'
            leave.approved_date = timezone.now()
            leave.rejection_reason = rejection_reason
            messages.success(request, f'Leave rejected for {leave.employee.first_name} {leave.employee.last_name}')
        
        leave.save()
    
    return redirect(request.META.get('HTTP_REFERER', 'leave_dashboard'))

# def leave_detail(request, leave_id):
#     """View details of a specific leave"""
#     # Check authentication
#     if not request.session.get('user_authenticated'):
#         return redirect('login')
    
#     leave = get_object_or_404(
#         Leave.objects.select_related(
#             'employee',
#             'leave_type',
#             'approved_by'
#         ),
#         id=leave_id
#     )
    
#     # Get regional holidays during leave period
#     holidays = []
#     if leave.employee.location:
#         region = Region.objects.filter(name__iexact=leave.employee.location).first()
#         if region:
#             holidays = Holiday.objects.filter(
#                 region=region,
#                 date__gte=leave.start_date,
#                 date__lte=leave.end_date
#             )
    
#     context = {
#         'leave': leave,
#         'holidays': holidays,
#         'working_days': leave.get_working_days(),
#     }
    
#     return render(request, 'leave/leave_detail.html', context)

def manage_regions(request):
    """Manage regions and holidays"""
    # Check authentication
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_region':
            name = request.POST.get('name')
            code = request.POST.get('code')
            description = request.POST.get('description', '')
            
            try:
                Region.objects.create(
                    name=name,
                    code=code.upper(),
                    description=description
                )
                messages.success(request, f'Region {name} added successfully!')
            except Exception as e:
                messages.error(request, f'Error adding region: {str(e)}')
        
        elif action == 'add_holiday':
            region_id = request.POST.get('region')
            name = request.POST.get('holiday_name')
            date = datetime.strptime(request.POST.get('holiday_date'), '%Y-%m-%d').date()
            description = request.POST.get('holiday_description', '')
            is_optional = request.POST.get('is_optional') == 'on'
            
            try:
                region = Region.objects.get(id=region_id)
                Holiday.objects.create(
                    region=region,
                    name=name,
                    date=date,
                    description=description,
                    is_optional=is_optional
                )
                messages.success(request, f'Holiday {name} added for {region.name}!')
            except Exception as e:
                messages.error(request, f'Error adding holiday: {str(e)}')
        
        return redirect('manage_regions')
    
    regions = Region.objects.prefetch_related('holidays').all()
    today = timezone.now().date()
    
    context = {
        'regions': regions,
        'current_year': today.year,
    }
    
    return render(request, 'leave/manage_regions.html', context)

def get_leave_stats_api(request):
    """API endpoint for dashboard statistics"""
    today = timezone.now().date()
    total_employees = Employee.objects.count()
    
    stats = {
        'total_employees': total_employees,
        'on_leave_today': Leave.objects.filter(
            start_date__lte=today,
            end_date__gte=today,
            status='approved'
        ).count(),
        'pending_applications': Leave.objects.filter(
            status='pending'
        ).count(),
        'approved_this_month': Leave.objects.filter(
            status='approved',
            approved_date__month=today.month,
            approved_date__year=today.year
        ).count(),
    }
    
    return JsonResponse(stats)

def leave_view(request):
    """Simple leave view - redirects to dashboard"""
    return redirect('leave_dashboard')

def calendar_events(request):
    """Return holidays and approved leaves as JSON for FullCalendar"""
    events = []

    # 1. Holidays
    holidays = Holiday.objects.all()
    for h in holidays:
        events.append({
            "title": f"Holiday: {h.name}",
            "start": h.date.strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#f87171",
        })

    # 2. Approved Leaves
    leaves = Leave.objects.filter(status="approved")
    for l in leaves:
        events.append({
            "title": f"Leave: {l.employee.first_name} {l.employee.last_name}",
            "start": l.start_date.strftime("%Y-%m-%d"),
            "end": (l.end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "allDay": True,
            "color": "#60a5fa",
        })

    return JsonResponse(events, safe=False)
def get_region_holidays_api(request, region_id):
    """API to fetch holidays for a specific region"""
    holidays = Holiday.objects.filter(
        region_id=region_id,
        date__year=timezone.now().year
    ).values('id', 'name', 'date', 'is_optional')
    
    return JsonResponse(list(holidays), safe=False)


def add_holiday(request):
    """Add a new holiday via modal form"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            region_id = request.POST.get('region')
            name = request.POST.get('holiday_name')
            holiday_type = request.POST.get('holiday_type')
            date_str = request.POST.get('holiday_date')
            description = request.POST.get('holiday_description', '')
            is_optional = request.POST.get('is_optional') == 'on'
            
            # Validate required fields
            if not region_id or not name or not date_str:
                messages.error(request, 'Please fill in all required fields.')
                return redirect('leave_dashboard')
            
            # Parse date
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Invalid date format.')
                return redirect('leave_dashboard')
            
            # Check if date is not in the past
            if date < timezone.now().date():
                messages.error(request, 'Cannot add holidays for past dates.')
                return redirect('leave_dashboard')
            
            # Get region
            region = Region.objects.get(id=region_id, is_active=True)
            
            # Check for duplicate holiday
            existing = Holiday.objects.filter(
                region=region,
                name=name,
                date=date
            ).exists()
            
            if existing:
                messages.warning(request, f'Holiday "{name}" already exists for {region.name} on {date}.')
                return redirect('leave_dashboard')
            
            # Create holiday
            Holiday.objects.create(
                region=region,
                name=name,
                holiday_type =holiday_type,
                date=date,
                description=description,
                is_optional=is_optional
            )
            
            messages.success(request, f'Holiday "{name}" added successfully for {region.name}!')
            
        except Region.DoesNotExist:
            messages.error(request, 'Selected region not found.')
        except Exception as e:
            messages.error(request, f'Error adding holiday: {str(e)}')
    
    return redirect('leave_dashboard')

def add_custom_event(request):
    """Add custom event (like company meeting) via modal"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            event_type = request.POST.get('event_type')
            title = request.POST.get('event_title')
            start_date_str = request.POST.get('start_date')
            end_date_str = request.POST.get('end_date')
            description = request.POST.get('event_description', '')
            
            # Validate required fields
            if not event_type or not title or not start_date_str:
                messages.error(request, 'Please fill in all required fields.')
                return redirect('leave_dashboard')
            
            # Parse dates
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else start_date
            
            # Validate date range
            if end_date < start_date:
                messages.error(request, 'End date cannot be before start date.')
                return redirect('leave_dashboard')
            
            # Here you can save to a CustomEvent model or handle as needed
            # For now, we'll just show a success message
            messages.success(request, f'Event "{title}" added successfully!')
            
        except ValueError:
            messages.error(request, 'Invalid date format.')
        except Exception as e:
            messages.error(request, f'Error adding event: {str(e)}')
    
    return redirect('leave_dashboard')

def employee_leave_details(request):
    """Employee-specific leave details page with strict rules information"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    # Get employee email from session
    user_email = request.session.get('user_email')
    if not user_email:
        messages.error(request, 'Session expired. Please log in again.')
        return redirect('login')

    try:
        employee = Employee.objects.get(email=user_email)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('leave_dashboard')
    
    # Current date and month calculations
    today = timezone.now().date()
    current_year = today.year
    current_month = today.month
    
    # Month names
    month_names = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    
    # NEW: Get probation status
    is_on_probation = ProbationService.is_on_probation(employee)
    probation_end_date = employee.probation_end_date
    
    # Get all leave balances with detailed information
    leave_balances = LeaveBalance.objects.filter(
        employee=employee,
        year=current_year
    ).select_related('leave_type')
    
    # Calculate statistics for each leave type
    leave_stats = {}
    for balance in leave_balances:
        leave_stats[balance.leave_type.name] = {
            'total': balance.total_leaves,
            'taken': balance.leaves_taken,
            'remaining': balance.leaves_remaining,
            'carry_forward': balance.carry_forward,
            'max_carry_forward': balance.leave_type.max_carry_forward,
            'is_optional': balance.leave_type.is_optional,
        }
    
    # Optional leave specific rules
    optional_leave_info = None
    if 'optional' in leave_stats:
        optional_info = leave_stats['optional']
        optional_leave_info = {
            'annual_allocation': 4,
            'max_usable': 2,
            'used': optional_info['taken'],
            'remaining_usable': max(0, 2 - optional_info['taken']),
            'will_lose': optional_info['remaining'] - max(0, 2 - optional_info['taken'])
        }
    
    # Annual leave accrual information
    annual_leave_info = None
    if 'annual' in leave_stats:
        annual_info = leave_stats['annual']
        annual_leave_info = {
            'monthly_accrual': 1.5,
            'max_carry_forward': 12,
            'current_carry_forward': annual_info['carry_forward'],
        }
    
    # Pending leaves
    pending_leaves = Leave.objects.filter(
        employee=employee,
        status__in=['pending', 'new']
    ).count()
    
    # Get leave history
    leave_history = Leave.objects.filter(
        employee=employee
    ).select_related('leave_type').order_by('-applied_date')
    
    context = {
        'employee': employee,
        'is_on_probation': is_on_probation,
        'probation_end_date': probation_end_date,
        'leave_stats': leave_stats,
        'optional_leave_info': optional_leave_info,
        'annual_leave_info': annual_leave_info,
        'pending_leaves': pending_leaves,
        'leave_history': leave_history,
        'current_year': current_year,
        'today_date': today,
    }
    
    return render(request, 'leave/emp_leave_details.html', context)


def view_leave_detail(request, leave_id):
    """Return JSON data for a specific leave (for modal display)"""
    leave = get_object_or_404(Leave, id=leave_id)

    context = {
        'leave': leave,
        'employee_name': f"{leave.employee.first_name} {leave.employee.last_name}",
        'department': leave.employee.department if hasattr(leave.employee, 'department') else None,
        'profile_image': leave.employee.profile_image.url if getattr(leave.employee, 'profile_image', None) else None,
    }

    return render(request, 'leave/view_leave_details.html',context)

def edit_leave_details(request, leave_id):
    """Admin can view and update leave status"""
    leave = get_object_or_404(Leave, id=leave_id)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        admin_remarks = request.POST.get('admin_remarks', '').strip()

        if new_status in ['approved', 'rejected', 'pending', 'new']:
            leave.status = new_status
            leave.admin_remarks = admin_remarks
            leave.save()
            messages.success(request, f'Leave status updated to {new_status}.')
            return redirect('view_leave_detail', leave_id=leave.id)
        else:
            messages.error(request, 'Invalid status selected.')

    context = {
        'leave': leave,
        'employee_name': f"{leave.employee.first_name} {leave.employee.last_name}",
        'department': getattr(leave.employee, 'department', None),
        'profile_image': leave.employee.profile_image.url if getattr(leave.employee, 'profile_image', None) else None,
    }
    return render(request, 'leave/edit_leave_details.html', context)


def leave_balance_summary(request):
    user_role = request.session.get('user_role')          
    user_department = request.session.get('user_department')
    
    # Start building the queryset
    queryset = LeaveBalance.objects
    
    # Apply department filter for managers BEFORE aggregation
    if user_role == 'MANAGER' and user_department:
        queryset = queryset.filter(employee__department=user_department)
    
    # Group by employee and sum up all leave types
    balances = (
        queryset
        .values('employee__id', 'employee__first_name', 'employee__last_name')
        .annotate(
            total_leaves=Sum('total_leaves'),
            leaves_taken=Sum('leaves_taken'),
            carry_forward=Sum('carry_forward')
        )
        .order_by('employee__first_name')
    )

    # Calculate remaining leaves for each employee
    for b in balances:
        total = (b['total_leaves'] or 0) + (b['carry_forward'] or 0)
        taken = b['leaves_taken'] or 0
        b['leaves_remaining'] = total - taken

    # ADD THESE LINES - Get data for modal dropdowns
    if user_role == 'MANAGER' and user_department:
        employees = Employee.objects.filter(department=user_department, status='active').order_by('first_name')
    else:
        employees = Employee.objects.filter(status='active').order_by('first_name')
    
    leave_types = LeaveType.objects.filter(is_active=True)
    current_year = date.today().year
    years = range(current_year - 2, current_year + 3)

    # UPDATE YOUR CONTEXT - Add these three lines
    context = {
        'balances': balances,
        'employees': employees,           # ADD THIS
        'leave_types': leave_types,       # ADD THIS
        'years': years,                   # ADD THIS
        'current_year': current_year,     # ADD THIS
    }
    
    return render(request, 'leave/leave_balance_summary.html', context)

def add_leave_balance(request):
    """Handle adding new leave balance"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            employee_id = request.POST.get('employee')
            leave_type_id = request.POST.get('leave_type')
            total_leaves = int(request.POST.get('total_leaves', 0))
            carry_forward = int(request.POST.get('carry_forward', 0))
            year = int(request.POST.get('year'))
            
            # Validate required fields
            if not employee_id or not leave_type_id or not year:
                messages.error(request, 'Please fill in all required fields.')
                return redirect('leave_balance_list')
            
            # Get employee and leave type
            try:
                employee = Employee.objects.get(id=employee_id)
                leave_type = LeaveType.objects.get(id=leave_type_id)
            except (Employee.DoesNotExist, LeaveType.DoesNotExist):
                messages.error(request, 'Invalid employee or leave type selected.')
                return redirect('leave_balance_list')
            
            # Check if balance already exists
            existing_balance = LeaveBalance.objects.filter(
                employee=employee,
                leave_type=leave_type,
                year=year
            ).first()
            
            if existing_balance:
                messages.warning(
                    request, 
                    f'Leave balance already exists for {employee.first_name} {employee.last_name} '
                    f'- {leave_type.get_name_display()} ({year}). Please update the existing record.'
                )
                return redirect('leave_balance_list')
            
            # Calculate remaining leaves
            leaves_remaining = total_leaves + carry_forward
            
            # Create new leave balance
            LeaveBalance.objects.create(
                employee=employee,
                leave_type=leave_type,
                total_leaves=total_leaves,
                leaves_taken=0,
                leaves_remaining=leaves_remaining,
                carry_forward=carry_forward,
                year=year
            )
            
            messages.success(
                request, 
                f'Leave balance added successfully for {employee.first_name} {employee.last_name} '
                f'- {leave_type.get_name_display()} ({year})'
            )
            
        except ValueError:
            messages.error(request, 'Invalid numeric values provided.')
        except Exception as e:
            messages.error(request, f'Error adding leave balance: {str(e)}')
    
    return redirect('leave_balance_list')