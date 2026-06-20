from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('portal/', views.portal, name='portal'),
    path('portal-redirect/', views.login_redirect, name='login_redirect'),
    path('panel/<str:username>/', views.admin_detail, name='admin_detail'),
    path('panel/<str:username>/set-limit/', views.set_limit, name='set_limit'),
    path('panel/<str:username>/action/', views.admin_action, name='admin_action'),
    path('sync/', views.trigger_sync, name='trigger_sync'),
    path('sync/status/', views.sync_status, name='sync_status'),
    path('settings/sync-interval/', views.update_sync_interval, name='update_sync_interval'),
    path('backup/database/', views.backup_database, name='backup_database'),
    path('login/', auth_views.LoginView.as_view(template_name='admins/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]
