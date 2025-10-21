from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('dashboard/', views.attendance_dashboard, name='dashboard'),
    path('all/', views.all_attendance, name='all_attendance'),
    path('report/', views.attendance_report, name='report'),
    path('download-report/', views.download_attendance_report, name='download_report'),
    path('download-admin-report/', views.download_admin_attendance_report, name='download_admin_report'),

]
