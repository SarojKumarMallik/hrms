from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Admin, Employee ,EmployeeDocument
from .forms import AdminForm
from datetime import date, datetime
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q ,Count
from .utils import authenticate_user, get_user_display_name, simple_hash, set_employee_password
import json
# Authentication decorator
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

# Authentication Views
def login_view(request):
    if request.session.get('user_authenticated'):
        return redirect('dashboard')
    
    if request.method == 'POST':
        email = request.POST.get('username')
        password = request.POST.get('password')
        
        user, user_type = authenticate_user(email, password)
        
        if user and user_type:
            request.session['user_authenticated'] = True
            request.session['user_email'] = email
            request.session['user_role'] = user_type
            # request.session['user_department'] = user.department
            if user_type == 'ADMIN':
                request.session['user_department'] = "NONE"
            else:
                request.session['user_department'] = user.department if user.department else None
            request.session['user_id'] = getattr(user, 'admin_id', getattr(user, 'id', None))
            request.session['user_name'] = get_user_display_name(user, user_type)
            
            messages.success(request, f'Welcome back, {request.session["user_name"]}!')
            
            # Redirect based on role
            if user_type in ['ADMIN', 'HR', 'SUPER_ADMIN']:
                return redirect('dashboard')
            elif user_type == 'MANAGER':
                return redirect('dashboard')
            else:
                return redirect('employee_dashboard')
        else:
            messages.error(request, 'Invalid email or password.')
    
    return render(request, 'hr/login.html')

def logout_view(request):
    request.session.flush()
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')

@login_required
def change_password(request):
    user_email = request.session.get('user_email')
    user_role = request.session.get('user_role')
    
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Verify current password
        user, user_type = authenticate_user(user_email, current_password)
        if not user:
            messages.error(request, 'Current password is incorrect.')
            return render(request, 'hr/change_password.html')
        
        # Check new password requirements
        if new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
        elif len(new_password) < 6:
            messages.error(request, 'Password must be at least 6 characters long.')
        else:
            try:
                # Update password based on user type
                if user_role == 'ADMIN':
                    admin = Admin.objects.get(email=user_email)
                    admin.password_hash = simple_hash(new_password)
                    admin.updated_at = timezone.now()
                    admin.save()
                    messages.success(request, 'Password changed successfully!')
                
                elif user_role in ['EMPLOYEE', 'MANAGER', 'HR', 'SUPER_ADMIN']:
                    # For employees and other roles
                    employee = Employee.objects.get(email=user_email, status='active')
                    set_employee_password(employee, new_password)
                    messages.success(request, 'Password changed successfully!')
                
                # Redirect based on user role after successful password change
                if user_role == 'EMPLOYEE':
                    return redirect('employee_dashboard')
                elif user_role in ['ADMIN', 'HR', 'SUPER_ADMIN', 'MANAGER']:
                    return redirect('dashboard')
                    
            except Employee.DoesNotExist:
                messages.error(request, 'Employee account not found or inactive.')
            except Exception as e:
                messages.error(request, f'Error changing password: {str(e)}')
        
        # If we get here, there was an error - stay on the same page
        return render(request, 'hr/change_password.html')
    
    # GET request - show the form
    context = {
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
        'today_date': date.today(),
    }
    return render(request, 'hr/change_password.html', context)

def access_denied(request):
    return render(request, 'hr/access_denied.html')

# Dashboard Views
@login_required
def dashboard(request):
    user_role = request.session.get('user_role')

    # ---- Base Data ----
    total_employees = Employee.objects.count()

    # Location-wise count
    location_data = Employee.objects.values('location').annotate(count=Count('id'))
    location_labels = [loc['location'] for loc in location_data]
    location_counts = [loc['count'] for loc in location_data]

    # Department-wise count
    department_data = Employee.objects.values('department').annotate(count=Count('id'))
    department_labels = [dept['department'] for dept in department_data]
    department_counts = [dept['count'] for dept in department_data]

    # ---- Shared Context ----
    context = {
        'total_employees': total_employees,
        'location_labels': json.dumps(location_labels),
        'location_counts': json.dumps(location_counts),
        'department_labels': json.dumps(department_labels),
        'department_counts': json.dumps(department_counts),
        'department_data': department_data,
        'today_date': date.today(),
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
    }

    # ---- Role-Based Additions ----
    if user_role == 'ADMIN':
        total_admins = Admin.objects.count()
        new_admins = Admin.objects.order_by('-created_at')[:5]
        active_employees = Employee.objects.filter(status='active').count()

        context.update({
            'total_admins': total_admins,
            'new_admins': new_admins,
            'active_employees': active_employees,
        })

    else:
        active_employees = Employee.objects.filter(status='active').count()
        context.update({
            'active_employees': active_employees,
        })

    return render(request, 'hr/dashboard.html', context)


@login_required
def employee_dashboard(request):
    user_email = request.session.get('user_email')
    user_role = request.session.get('user_role')
    
    print(f"DEBUG: User email from session: {user_email}")
    print(f"DEBUG: User role from session: {user_role}")
    
    # if user_role not in ['EMPLOYEE','MANAGER']:
    #     messages.error(request, 'Access denied. Employee dashboard is for employees only.')
    #     return redirect('access_denied')
    
    # Get employee details
    try:
        employee_profile = Employee.objects.get(email=user_email)
        print(f"DEBUG: Found employee: {employee_profile.first_name} {employee_profile.last_name}")
    except Employee.DoesNotExist:
        employee_profile = None
        print(f"DEBUG: No employee found with email: {user_email}")
        messages.warning(request, 'Employee profile not found.')
    
    context = {
        'employee': employee_profile,
        'today_date': date.today(),
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
    }
    
    print(f"DEBUG: Context data: {context}")
    return render(request, 'hr/employee_dashboard.html', context)

@login_required
@role_required(['ADMIN', 'HR', 'SUPER_ADMIN'])
def add_employee(request):
    # Get all active managers for the dropdown
    managers = Employee.objects.filter(
        role__in=['Manager', 'Team Lead', 'HR', 'Admin', 'Super Admin'],
        status='active'
    ).order_by('first_name', 'last_name')
   
    if request.method == "POST":
        try:
            # Check if employee ID already exists
            employee_id = request.POST.get('employee_id')
            if Employee.objects.filter(employee_id=employee_id).exists():
                messages.error(request, f"Employee with ID {employee_id} already exists.")
                return render(request, 'hr/add_employee.html', {'managers': managers})
           
            # Check if email already exists
            email = request.POST.get('email')
            if Employee.objects.filter(email=email).exists():
                messages.error(request, f"Employee with email {email} already exists.")
                return render(request, 'hr/add_employee.html', {'managers': managers})
           
            # Extract reporting manager ID from the selected option
            reporting_manager_full = request.POST.get('reporting_manager')
            reporting_manager_id = None
           
            if reporting_manager_full:
                try:
                    name_part = reporting_manager_full.split(' (')[0]
                    first_name, last_name = name_part.split(' ', 1) if ' ' in name_part else (name_part, '')
                   
                    manager = Employee.objects.filter(
                        first_name=first_name,
                        last_name=last_name,
                        status='active'
                    ).first()
                   
                    if manager:
                        reporting_manager_id = manager.employee_id
                except (IndexError, ValueError):
                    reporting_manager_id = None
            date_of_joining_str = request.POST.get('date_of_joining')
            if date_of_joining_str:
                try:
                    date_of_joining = datetime.strptime(date_of_joining_str, "%Y-%m-%d").date()
                except ValueError:
                    date_of_joining = timezone.now().date()
            else:
                date_of_joining = timezone.now().date()
            # Create new employee
            employee = Employee(
                employee_id=employee_id,
                first_name=request.POST.get('first_name'),
                last_name=request.POST.get('last_name'),
                email=email,
                phone=request.POST.get('phone'),
                department=request.POST.get('department'),
                designation=request.POST.get('designation'),
                reporting_manager=reporting_manager_full,
                reporting_manager_id=reporting_manager_id,
                role=request.POST.get('role'),
                location=request.POST.get('location'),
                # date_of_joining=request.POST.get('date_of_joining') or timezone.now().date(),
                date_of_joining=date_of_joining,
                status=request.POST.get('status'),
                profile_picture=request.FILES.get('image'),
                bank_name=request.POST.get('bank_name'),
                account_number=request.POST.get('account_number'),
                ifsc_code=request.POST.get('ifsc_code'),
                created_at=timezone.now(),
                updated_at=timezone.now()
            )
            
            employee.save()
           
            # Save Educational Certificates
            education_types = request.POST.getlist('education_type[]')
            education_files = request.FILES.getlist('education_files[]')
           
            for edu_type, edu_file in zip(education_types, education_files):
                if edu_type and edu_file:
                    EmployeeDocument.objects.create(
                        employee=employee,
                        document_type='educational',
                        document_number=edu_type,
                        file=edu_file
                    )
           
            # Save PAN Card
            pan_number = request.POST.get('pan_number')
            pan_file = request.FILES.get('pan_file')
            if pan_number and pan_file:
                EmployeeDocument.objects.create(
                    employee=employee,
                    document_type='pan',
                    document_number=pan_number,
                    file=pan_file
                )
           
            # Save Aadhaar Card
            aadhaar_number = request.POST.get('aadhaar_number')
            aadhaar_file = request.FILES.get('aadhaar_file')
            if aadhaar_number and aadhaar_file:
                EmployeeDocument.objects.create(
                    employee=employee,
                    document_type='aadhaar',
                    document_number=aadhaar_number,
                    file=aadhaar_file
                )
           
            # Save Bank Passbook
            passbook_file = request.FILES.get('passbook_file')
            if passbook_file:
                EmployeeDocument.objects.create(
                    employee=employee,
                    document_type='passbook',
                    file=passbook_file
                )
           
            # Save Offer Letter
            offer_letter_file = request.FILES.get('offer_letter_file')
            if offer_letter_file:
                EmployeeDocument.objects.create(
                    employee=employee,
                    document_type='offer_letter',
                    file=offer_letter_file
                )
           
            # Save Salary Slips (multiple files)
            salary_slip_files = request.FILES.getlist('salary_slip_files')
            for salary_slip_file in salary_slip_files:
                EmployeeDocument.objects.create(
                    employee=employee,
                    document_type='salary_slip',
                    file=salary_slip_file
                )
           
            # Save Bank Statement
            bank_statement_file = request.FILES.get('bank_statement_file')
            if bank_statement_file:
                EmployeeDocument.objects.create(
                    employee=employee,
                    document_type='bank_statement',
                    file=bank_statement_file
                )
           
            # Save Experience Letter
            experience_letter_file = request.FILES.get('experience_letter_file')
            if experience_letter_file:
                EmployeeDocument.objects.create(
                    employee=employee,
                    document_type='experience_letter',
                    file=experience_letter_file
                )
           
            messages.success(request, f"Employee {employee.first_name} {employee.last_name} added successfully with all documents!")
            return redirect('employee_page')
           
        except Exception as e:
            messages.error(request, f"Error adding employee: {str(e)}")
            return render(request, 'hr/add_employee.html', {'managers': managers})
   
    # GET request - show empty form with managers data
    context = {
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'managers': managers,
    }
    return render(request, 'hr/add_employee.html', context)

@login_required
@role_required(['ADMIN', 'HR', 'MANAGER', 'SUPER_ADMIN'])
def employee_page(request):
    # Get search query and filters
    search_query = request.GET.get('search', '')
    department_filter = request.GET.get('department', '')
    status_filter = request.GET.get('status', '')
    page_size = int(request.GET.get('page_size', 12))
   
    # Get current user details
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    user_name = request.session.get('user_name')
   
    # Start with appropriate employee list based on role
    if user_role in ['ADMIN', 'HR', 'SUPER_ADMIN']:
        employees_list = Employee.objects.all().order_by('first_name')
        filter_info = "Showing all employees"
   
    elif user_role == 'MANAGER':
        try:
            # Get the current manager's employee record
            current_manager = Employee.objects.get(email=user_email)
           
            # Filter by reporting_manager_id OR by reporting_manager name (fallback)
            employees_list = Employee.objects.filter(
                Q(reporting_manager_id=current_manager.employee_id) |
                Q(reporting_manager__icontains=current_manager.first_name)
            ).order_by('first_name')
           
            filter_info = f"Showing employees under {user_name}"
           
        except Employee.DoesNotExist:
            employees_list = Employee.objects.none()
            filter_info = "Manager profile not found"
   
    else:
        employees_list = Employee.objects.none()
        filter_info = "No access to employee list"
   
    # Apply search filter
    if search_query:
        employees_list = employees_list.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(department__icontains=search_query) |
            Q(designation__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
   
    # Apply department filter
    if department_filter:
        employees_list = employees_list.filter(department__iexact=department_filter)
   
    # Apply status filter
    if status_filter:
        employees_list = employees_list.filter(status__iexact=status_filter)
   
    # Get total counts for display
    total_employees = employees_list.count()
    active_employees = employees_list.filter(status='active').count()
   
    # Pagination
    paginator = Paginator(employees_list, page_size)
    page = request.GET.get('page')
   
    try:
        employees = paginator.page(page)
    except PageNotAnInteger:
        employees = paginator.page(1)
    except EmptyPage:
        employees = paginator.page(paginator.num_pages)
   
    context = {
        'employees': employees,
        'today_date': date.today(),
        'search_query': search_query,
        'department_filter': department_filter,
        'status_filter': status_filter,
        'page_size': page_size,
        'user_name': user_name,
        'user_role': user_role,
        'total_employees': total_employees,
        'active_employees': active_employees,
        'filter_info': filter_info,
    }
   
    return render(request, 'hr/employee.html', context)


@login_required
def employee_detail(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
   
    # Check permission - employees can only view their own profile
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
   
    if user_role == 'EMPLOYEE' and employee.email != user_email:
        messages.error(request, 'You can only view your own profile.')
        return redirect('access_denied')
   
    # Get all active managers for the dropdown (for edit modal)
    managers = Employee.objects.filter(
        role__in=['Manager', 'Team Lead', 'HR', 'Admin', 'Super Admin'],
        status='active'
    ).order_by('first_name', 'last_name')
   
    context = {
        'employee': employee,
        'managers': managers,  # Add this line
        'today_date': timezone.now().date(),
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
    }
   
    return render(request, 'hr/employee_detail.html', context)


@login_required
@role_required(['ADMIN', 'HR', 'MANAGER', 'SUPER_ADMIN'])
def edit_employee(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
   
    # Get managers for dropdown
    managers = Employee.objects.filter(
        role__in=['Manager', 'Team Lead', 'HR', 'Admin', 'Super Admin'],
        status='active'
    ).order_by('first_name', 'last_name')
   
    # Check if manager can edit this employee
    user_role = request.session.get('user_role')
    if user_role == 'MANAGER':
        user_name = request.session.get('user_name')
        if user_name not in employee.reporting_manager:
            messages.error(request, 'You can only edit employees in your team.')
            return redirect('access_denied')
   
    if request.method == 'POST':
        try:
            # Get reporting manager data from form
            reporting_manager_full = request.POST.get('reporting_manager')
            reporting_manager_id = request.POST.get('reporting_manager_id')
           
            # If we have the reporting manager name but no ID, try to find it
            if reporting_manager_full and not reporting_manager_id:
                try:
                    name_part = reporting_manager_full.split(' (')[0]
                    first_name, last_name = name_part.split(' ', 1) if ' ' in name_part else (name_part, '')
                   
                    manager = Employee.objects.filter(
                        first_name=first_name,
                        last_name=last_name,
                        status='active'
                    ).first()
                   
                    if manager:
                        reporting_manager_id = manager.employee_id
                except (IndexError, ValueError):
                    reporting_manager_id = None
            date_of_joining_str = request.POST.get('date_of_joining')
            if date_of_joining_str:
                try:
                    employee.date_of_joining = datetime.strptime(date_of_joining_str, "%Y-%m-%d").date()
                except ValueError:
                    employee.date_of_joining = None
            else:
                employee.date_of_joining = None
            # Update employee fields
            employee.first_name = request.POST.get('first_name')
            employee.last_name = request.POST.get('last_name')
            employee.email = request.POST.get('email')
            employee.phone = request.POST.get('phone')
            employee.department = request.POST.get('department')
            employee.designation = request.POST.get('designation')
            employee.reporting_manager = reporting_manager_full
            employee.reporting_manager_id = reporting_manager_id
            employee.role = request.POST.get('role')
            employee.location = request.POST.get('location')
            employee.date_of_joining = request.POST.get('date_of_joining') or None
            employee.status = request.POST.get('status')
            employee.bank_name = request.POST.get('bank_name')
            employee.account_number = request.POST.get('account_number')
            employee.ifsc_code = request.POST.get('ifsc_code')
           
            if request.FILES.get('image'):
                employee.profile_picture = request.FILES.get('image')
           
            employee.updated_at = timezone.now()
            employee.save()
           
            # Handle document uploads
            handle_document_uploads(employee, request)
           
            messages.success(request, 'Employee and documents updated successfully!')
            return redirect('employee_detail', employee_id=employee_id)
           
        except Exception as e:
            messages.error(request, f'Error updating employee: {str(e)}')
   
    context = {
        'employee': employee,
        'managers': managers,
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
    }
   
    return render(request, 'hr/edit_employee.html', context)


# Admin Management
@login_required
@role_required(['ADMIN', 'SUPER_ADMIN'])
def admin_list(request):
    admins = Admin.objects.all()
    return render(request, 'hr/admin_list.html', {
        'admins': admins,
        'today_date': date.today(),
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
    })

@login_required
@role_required(['ADMIN', 'SUPER_ADMIN'])
def admin_create(request):
    form = AdminForm(request.POST or None)
    if form.is_valid():
        admin = form.save(commit=False)
        admin.password_hash = simple_hash('password123')  # Default password
        admin.created_at = timezone.now()
        admin.updated_at = timezone.now()
        admin.save()
        messages.success(request, 'Admin created successfully!')
        return redirect('admin_list')
    return render(request, 'hr/admin_form.html', {
        'form': form,
        'today_date': date.today(),
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
    })

@login_required
@role_required(['ADMIN', 'SUPER_ADMIN'])
def admin_update(request, pk):
    admin = get_object_or_404(Admin, pk=pk)
    form = AdminForm(request.POST or None, instance=admin)
    if form.is_valid():
        admin = form.save(commit=False)
        admin.updated_at = timezone.now()
        admin.save()
        messages.success(request, 'Admin updated successfully!')
        return redirect('admin_list')
    return render(request, 'hr/admin_form.html', {
        'form': form,
        'today_date': date.today(),
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
    })

@login_required
@role_required(['ADMIN', 'SUPER_ADMIN'])
def admin_delete(request, pk):
    admin = get_object_or_404(Admin, pk=pk)
    if request.method == 'POST':
        admin.delete()
        messages.success(request, 'Admin deleted successfully!')
        return redirect('admin_list')
    return render(request, 'hr/admin_confirm_delete.html', {
        'admin': admin,
        'today_date': date.today(),
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
    })

def home(request):
    if request.session.get('user_authenticated'):
        user_role = request.session.get('user_role')
        if user_role == 'EMPLOYEE':
            return redirect('employee_dashboard')
        else:
            return redirect('dashboard')
    return redirect('login')

@login_required
def update_employee_profile(request):
    """Allow active employees to update their own profile"""
    user_email = request.session.get('user_email')
    user_role = request.session.get('user_role')
    
    # Only allow employees to update their own profile
    # if user_role != 'EMPLOYEE':
    #     messages.error(request, 'Access denied.')
    #     return redirect('access_denied')
    
    try:
        employee = Employee.objects.get(email=user_email, status='active')
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found or inactive.')
        return redirect('employee_dashboard')
    
    if request.method == 'POST':
        # Update employee profile
        employee.phone = request.POST.get('phone', employee.phone)
        employee.department = request.POST.get('department', employee.department)
        employee.designation = request.POST.get('designation', employee.designation)
        employee.location = request.POST.get('location', employee.location)
        
        # Handle profile picture upload
        if request.FILES.get('profile_picture'):
            employee.profile_picture = request.FILES.get('profile_picture')
        
        employee.updated_at = timezone.now()
        employee.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('employee_dashboard')
    
    context = {
        'employee': employee,
        'today_date': date.today(),
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
    }
    return render(request, 'hr/update_employee_profile.html', context)


def handle_document_uploads(employee, request):
    # Save Educational Certificates
    education_types = request.POST.getlist('education_type[]')
    education_files = request.FILES.getlist('education_files[]')
   
    for edu_type, edu_file in zip(education_types, education_files):
        if edu_type and edu_file:
            EmployeeDocument.objects.create(
                employee=employee,
                document_type='educational',
                document_number=edu_type,
                file=edu_file
            )
   
    # Save PAN Card
    pan_number = request.POST.get('pan_number')
    pan_file = request.FILES.get('pan_file')
    if pan_file:  # If new file is uploaded
        # Delete existing PAN documents if new file is provided
        if pan_file:
            EmployeeDocument.objects.filter(employee=employee, document_type='pan').delete()
       
        EmployeeDocument.objects.create(
            employee=employee,
            document_type='pan',
            document_number=pan_number,
            file=pan_file
        )
    elif pan_number:  # If only number is updated, update existing document
        existing_pan = EmployeeDocument.objects.filter(employee=employee, document_type='pan').first()
        if existing_pan:
            existing_pan.document_number = pan_number
            existing_pan.save()
   
    # Save Aadhaar Card
    aadhaar_number = request.POST.get('aadhaar_number')
    aadhaar_file = request.FILES.get('aadhaar_file')
    if aadhaar_file:  # If new file is uploaded
        # Delete existing Aadhaar documents if new file is provided
        if aadhaar_file:
            EmployeeDocument.objects.filter(employee=employee, document_type='aadhaar').delete()
       
        EmployeeDocument.objects.create(
            employee=employee,
            document_type='aadhaar',
            document_number=aadhaar_number,
            file=aadhaar_file
        )
    elif aadhaar_number:  # If only number is updated, update existing document
        existing_aadhaar = EmployeeDocument.objects.filter(employee=employee, document_type='aadhaar').first()
        if existing_aadhaar:
            existing_aadhaar.document_number = aadhaar_number
            existing_aadhaar.save()
   
    # Save other documents (only if new file is uploaded)
    document_mappings = [
        ('passbook_file', 'passbook'),
        ('offer_letter_file', 'offer_letter'),
        ('bank_statement_file', 'bank_statement'),
        ('experience_letter_file', 'experience_letter'),
    ]
   
    for file_field, doc_type in document_mappings:
        doc_file = request.FILES.get(file_field)
        if doc_file:
            # Delete existing documents of this type
            EmployeeDocument.objects.filter(employee=employee, document_type=doc_type).delete()
            EmployeeDocument.objects.create(
                employee=employee,
                document_type=doc_type,
                file=doc_file
            )
   
    # Save Salary Slips (multiple files - append, don't replace)
    salary_slip_files = request.FILES.getlist('salary_slip_files')
    for salary_slip_file in salary_slip_files:
        EmployeeDocument.objects.create(
            employee=employee,
            document_type='salary_slip',
            file=salary_slip_file
        )

@login_required
@role_required(['ADMIN', 'HR', 'SUPER_ADMIN'])
def delete_document(request, document_id):
    if request.method == "POST":
        try:
            document = get_object_or_404(EmployeeDocument, id=document_id)
            employee_id = document.employee.id
            document.delete()
            messages.success(request, "Document deleted successfully!")
            return redirect('employee_detail', employee_id=employee_id)
        except Exception as e:
            messages.error(request, f"Error deleting document: {str(e)}")
            return redirect('employee_page')
   
    # If not POST method, redirect to employee page
    return redirect('employee_page')
# All employee
@login_required
def all_employee(request):
    employees = Employee.objects.all()
    return render(request, 'hr/all_employee.html', {
        'employees': employees,
        'today_date': date.today(),
    })


# Active employee
@login_required
def active_employee(request):
    employees = Employee.objects.filter(status__iexact='active')  

    return render(request, 'hr/active_employee.html', {
        'employees': employees,
        'today_date': date.today(),
    })
