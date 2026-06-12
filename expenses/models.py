from django.db import models
from accounts.models import TelegramUser


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('food', 'Еда'),
        ('transport', 'Транспорт'),
        ('entertainment', 'Развлечения'),
        ('health', 'Здоровье'),
        ('shopping', 'Покупки'),
        ('utilities', 'Коммунальные'),
        ('other', 'Другое'),
    ]

    CATEGORY_ICONS = {
        'food': '🍕',
        'transport': '🚕',
        'entertainment': '🎬',
        'health': '💊',
        'shopping': '🛍️',
        'utilities': '🏠',
        'other': '📦',
    }

    CURRENCY_CHOICES = [
        ('USD', 'USD'),
        ('UZS', 'UZS'),
        ('RUB', 'RUB'),
    ]

    user = models.ForeignKey(
        TelegramUser, on_delete=models.CASCADE,
        related_name='expenses', verbose_name='Пользователь'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма')
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD', verbose_name='Валюта')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name='Категория')
    description = models.TextField(verbose_name='Описание')
    voice_transcript = models.TextField(blank=True, verbose_name='Транскрипция голоса')
    expense_date = models.DateField(verbose_name='Дата расхода')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        verbose_name = 'Расход'
        verbose_name_plural = 'Расходы'
        ordering = ['-expense_date', '-created_at']

    def __str__(self):
        return f'{self.get_category_display()} — {self.amount} {self.currency} ({self.expense_date})'

    @property
    def category_icon(self):
        return self.CATEGORY_ICONS.get(self.category, '📦')

    @property
    def category_label(self):
        return dict(self.CATEGORY_CHOICES).get(self.category, 'Другое')
