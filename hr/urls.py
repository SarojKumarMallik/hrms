from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password, name='change_password'),
    path('access-denied/', views.access_denied, name='access_denied'),
    
    # Dashboards
    path('dashboard/', views.dashboard, name='dashboard'),
    path('employee-dashboard/', views.employee_dashboard, name='employee_dashboard'),
    
    # Employee Management
    path('employees/', views.employee_page, name='employee_page'),
    path('employees/add/', views.add_employee, name='add_employee'),
    path('employee/<int:employee_id>/', views.employee_detail, name='employee_detail'),
    path('employee/<int:employee_id>/edit/', views.edit_employee, name='edit_employee'),
    path('delete-document/<int:document_id>/', views.delete_document, name='delete_document'),
    path('update-profile/', views.update_employee_profile, name='update_employee_profile'),
    path('employees/all/', views.all_employee, name='all_employee'),
    path('employees/active/', views.active_employee, name='active_employee'),
    
    # Admin Management
    path('admins/', views.admin_list, name='admin_list'),
    path('admins/create/', views.admin_create, name='admin_create'),
    path('admins/<int:pk>/update/', views.admin_update, name='admin_update'),
    path('admins/<int:pk>/delete/', views.admin_delete, name='admin_delete'),
]