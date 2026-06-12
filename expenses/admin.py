from django.contrib import admin
from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'currency', 'category', 'description', 'expense_date', 'created_at')
    list_filter = ('category', 'currency', 'expense_date')
    search_fields = ('description', 'voice_transcript', 'user__username', 'user__first_name')
    readonly_fields = ('created_at',)
    date_hierarchy = 'expense_date'
