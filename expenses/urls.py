from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.dashboard, name='dashboard'),
    path('history/', views.history, name='history'),
    path('history/delete/<int:pk>/', views.delete_expense, name='delete_expense'),
    path('analytics/', views.analytics, name='analytics'),

    # Telegram Mini App auth
    path('twa-auth/', views.twa_auth, name='twa_auth'),

    # REST API
    path('api/expenses/', views.api_expenses, name='api_expenses'),
    path('api/expenses/add/', views.api_add_expense, name='api_add_expense'),
    path('api/expenses/stats/', views.api_stats, name='api_stats'),
    path('api/expenses/monthly/', views.api_monthly, name='api_monthly'),
]
