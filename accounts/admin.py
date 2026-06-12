from django.contrib import admin
from .models import TelegramUser


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'first_name', 'username', 'joined_at')
    search_fields = ('telegram_id', 'username', 'first_name')
    readonly_fields = ('joined_at',)
