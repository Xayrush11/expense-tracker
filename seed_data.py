"""
Run: python seed_data.py
Populates the database with realistic demo expenses for the past 2 months.
"""
import os
import sys
import random
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'expense_tracker.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
django.setup()

from accounts.models import TelegramUser
from expenses.models import Expense

EXPENSES = [
    ('food',         'Завтрак в кафе',         8.50,  'USD'),
    ('food',         'Продукты в Korzinka',     45.00, 'USD'),
    ('food',         'Пицца на обед',           12.00, 'USD'),
    ('food',         'Суши на ужин',            22.00, 'USD'),
    ('food',         'Кофе и круассан',         4.50,  'USD'),
    ('transport',    'Яндекс такси',            3.20,  'USD'),
    ('transport',    'Метро на работу',         0.50,  'USD'),
    ('transport',    'Uber до аэропорта',       18.00, 'USD'),
    ('transport',    'Автобус',                 0.30,  'USD'),
    ('entertainment','Кино с друзьями',         9.00,  'USD'),
    ('entertainment','Netflix подписка',        15.99, 'USD'),
    ('entertainment','Боулинг',                 14.00, 'USD'),
    ('entertainment','Концерт',                 35.00, 'USD'),
    ('health',       'Аптека, витамины',        12.00, 'USD'),
    ('health',       'Приём врача',             30.00, 'USD'),
    ('shopping',     'Кроссовки Nike',          89.00, 'USD'),
    ('shopping',     'Футболка',                19.00, 'USD'),
    ('shopping',     'Книги на Ozon',           24.00, 'USD'),
    ('utilities',    'Интернет UZTELECOM',      10.00, 'USD'),
    ('utilities',    'Коммунальные платежи',    28.00, 'USD'),
    ('other',        'Подарок коллеге',         20.00, 'USD'),
    ('other',        'Канцелярия',              8.00,  'USD'),
]

def seed():
    user, created = TelegramUser.objects.get_or_create(
        telegram_id=123456789,
        defaults={'username': 'demo_user', 'first_name': 'Алишер'}
    )
    if created:
        print(f'Created demo user: {user}')

    today = date.today()
    Expense.objects.filter(user=user).delete()

    count = 0
    for i in range(60):
        d = today - timedelta(days=i)
        n = random.randint(1, 3)
        for _ in range(n):
            cat, desc, amt, cur = random.choice(EXPENSES)
            variation = Decimal(str(random.uniform(0.85, 1.15)))
            final_amt = round(Decimal(str(amt)) * variation, 2)
            Expense.objects.create(
                user=user,
                amount=final_amt,
                currency=cur,
                category=cat,
                description=desc,
                voice_transcript=f'Потратил {final_amt} долларов на {desc.lower()}',
                expense_date=d,
            )
            count += 1

    print(f'Seeded {count} expenses for user {user.display_name}')
    print(f'Telegram ID to use: {user.telegram_id}')


if __name__ == '__main__':
    seed()
