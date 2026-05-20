from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),          # public landing page
    path('dashboard/', views.dashboard, name='dashboard'), # upload / main app
    path('reports/', views.report_history, name='report_history'),
    path('reports/<int:pk>/', views.report_detail, name='report_detail'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('garages/', views.nearby_garages, name='nearby_garages'),
]
