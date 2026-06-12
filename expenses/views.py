import csv
import hmac
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import parse_qsl

from django.conf import settings
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDay, TruncMonth
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt

from accounts.models import TelegramUser
from .models import Expense


def get_current_user(request):
    """Return the TelegramUser linked to this session, or the first real user, or None."""
    tg_id = request.session.get('telegram_id')
    if tg_id:
        try:
            return TelegramUser.objects.get(telegram_id=tg_id)
        except TelegramUser.DoesNotExist:
            pass
    # Fallback: first real user (telegram_id > 0, registered via bot)
    return TelegramUser.objects.filter(telegram_id__gt=0).order_by('joined_at').first()


# ─── Dashboard ────────────────────────────────────────────────────────────────

def dashboard(request):
    user = get_current_user(request)
    today = date.today()

    period = request.GET.get('period', 'month')
    if period == 'week':
        date_from = today - timedelta(days=today.weekday())
    elif period == 'month':
        date_from = today.replace(day=1)
    else:
        date_from = None

    qs = Expense.objects.filter(user=user) if user else Expense.objects.none()
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)

    total_amount = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    tx_count = qs.count()
    voice_count = qs.exclude(voice_transcript='').count()

    top_category = (
        qs.values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
        .first()
    )
    top_cat_label = ''
    top_cat_icon = ''
    if top_category:
        top_cat_label = dict(Expense.CATEGORY_CHOICES).get(top_category['category'], '')
        top_cat_icon = Expense.CATEGORY_ICONS.get(top_category['category'], '📦')

    categories = (
        qs.values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    cat_max = max((c['total'] for c in categories), default=Decimal('1'))

    category_data = []
    for c in categories:
        label = dict(Expense.CATEGORY_CHOICES).get(c['category'], c['category'])
        icon = Expense.CATEGORY_ICONS.get(c['category'], '📦')
        pct = int((c['total'] / cat_max) * 100)
        category_data.append({
            'category': c['category'],
            'label': label,
            'icon': icon,
            'total': c['total'],
            'pct': pct,
        })

    recent = qs.order_by('-expense_date', '-created_at')[:10]

    context = {
        'user': user,
        'period': period,
        'total_amount': total_amount,
        'tx_count': tx_count,
        'voice_count': voice_count,
        'top_cat_label': top_cat_label,
        'top_cat_icon': top_cat_icon,
        'category_data': category_data,
        'recent': recent,
        'categories': Expense.CATEGORY_CHOICES,
    }
    return render(request, 'expenses/dashboard.html', context)


# ─── History ──────────────────────────────────────────────────────────────────

def history(request):
    user = get_current_user(request)
    qs = Expense.objects.filter(user=user) if user else Expense.objects.none()

    category_filter = request.GET.get('category', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if category_filter:
        qs = qs.filter(category=category_filter)
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)

    if request.GET.get('export') == 'csv':
        return export_csv(qs)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    context = {
        'user': user,
        'page': page,
        'categories': Expense.CATEGORY_CHOICES,
        'category_filter': category_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'expenses/history.html', context)


def export_csv(qs):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="expenses.csv"'
    response.write('﻿')  # BOM for Excel
    writer = csv.writer(response)
    writer.writerow(['Дата', 'Описание', 'Категория', 'Сумма', 'Валюта'])
    for e in qs:
        writer.writerow([e.expense_date, e.description, e.category_label, e.amount, e.currency])
    return response


def delete_expense(request, pk):
    user = get_current_user(request)
    expense = get_object_or_404(Expense, pk=pk, user=user)
    if request.method == 'POST':
        expense.delete()
    return redirect('history')


# ─── Analytics ────────────────────────────────────────────────────────────────

def analytics(request):
    user = get_current_user(request)
    today = date.today()

    # Last 6 months labels
    months = []
    for i in range(5, -1, -1):
        d = today.replace(day=1) - timedelta(days=i * 30)
        months.append(d.replace(day=1))

    context = {
        'user': user,
        'categories': Expense.CATEGORY_CHOICES,
    }
    return render(request, 'expenses/analytics.html', context)


# ─── REST API ─────────────────────────────────────────────────────────────────

def api_expenses(request):
    user = get_current_user(request)
    qs = Expense.objects.filter(user=user) if user else Expense.objects.none()

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    category = request.GET.get('category')

    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)
    if category:
        qs = qs.filter(category=category)

    data = [
        {
            'id': e.id,
            'amount': str(e.amount),
            'currency': e.currency,
            'category': e.category,
            'category_label': e.category_label,
            'category_icon': e.category_icon,
            'description': e.description,
            'expense_date': e.expense_date.isoformat(),
            'created_at': e.created_at.isoformat(),
        }
        for e in qs[:200]
    ]
    return JsonResponse({'expenses': data, 'count': len(data)})


def api_stats(request):
    user = get_current_user(request)
    today = date.today()

    period = request.GET.get('period', 'month')
    if period == 'week':
        date_from = today - timedelta(days=today.weekday())
    elif period == 'month':
        date_from = today.replace(day=1)
    else:
        date_from = None

    qs = Expense.objects.filter(user=user) if user else Expense.objects.none()
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)

    total = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    by_category = list(
        qs.values('category')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    for c in by_category:
        c['total'] = str(c['total'])
        c['label'] = dict(Expense.CATEGORY_CHOICES).get(c['category'], c['category'])
        c['icon'] = Expense.CATEGORY_ICONS.get(c['category'], '📦')

    by_day = list(
        qs.annotate(day=TruncDay('expense_date'))
        .values('day')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )
    by_day_data = [
        {'day': item['day'].isoformat(), 'total': str(item['total'])}
        for item in by_day
    ]

    return JsonResponse({
        'total': str(total),
        'count': qs.count(),
        'by_category': by_category,
        'by_day': by_day_data,
    })


def api_monthly(request):
    user = get_current_user(request)
    today = date.today()

    six_months_ago = (today.replace(day=1) - timedelta(days=150)).replace(day=1)

    base_qs = Expense.objects.filter(user=user) if user else Expense.objects.none()

    qs = (
        base_qs.filter(expense_date__gte=six_months_ago)
        .annotate(month=TruncMonth('expense_date'))
        .values('month')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('month')
    )

    # Current vs previous month
    this_month_start = today.replace(day=1)
    prev_month_end = this_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    this_total = base_qs.filter(
        expense_date__gte=this_month_start
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    prev_total = base_qs.filter(
        expense_date__gte=prev_month_start,
        expense_date__lte=prev_month_end,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    if prev_total > 0:
        diff_pct = round(float((this_total - prev_total) / prev_total) * 100, 1)
    else:
        diff_pct = 0

    top5 = list(
        base_qs.filter(expense_date__gte=this_month_start)
        .order_by('-amount')[:5]
        .values('description', 'amount', 'currency', 'category', 'expense_date')
    )
    for t in top5:
        t['amount'] = str(t['amount'])
        t['expense_date'] = t['expense_date'].isoformat()
        t['icon'] = Expense.CATEGORY_ICONS.get(t['category'], '📦')

    monthly = [
        {
            'month': item['month'].strftime('%Y-%m'),
            'label': item['month'].strftime('%b %Y'),
            'total': str(item['total']),
            'count': item['count'],
        }
        for item in qs
    ]

    return JsonResponse({
        'monthly': monthly,
        'this_month': str(this_total),
        'prev_month': str(prev_total),
        'diff_pct': diff_pct,
        'top5': top5,
    })


@csrf_exempt
def twa_auth(request):
    """Auto-login from Telegram Mini App initData. Called by JS on page load."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    init_data = request.POST.get('initData', '').strip()
    if not init_data:
        return JsonResponse({'ok': False, 'error': 'no initData'}, status=400)

    bot_token = settings.TELEGRAM_BOT_TOKEN
    data_dict = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data_dict.pop('hash', '')

    data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(data_dict.items()))
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return JsonResponse({'ok': False, 'error': 'bad signature'}, status=403)

    user_json = data_dict.get('user', '{}')
    user_data = json.loads(user_json)
    tg_id = user_data.get('id')
    if not tg_id:
        return JsonResponse({'ok': False, 'error': 'no user id'}, status=400)

    tg_user, _ = TelegramUser.objects.get_or_create(
        telegram_id=tg_id,
        defaults={
            'username': user_data.get('username', ''),
            'first_name': user_data.get('first_name', ''),
        },
    )
    request.session['telegram_id'] = tg_id
    request.session.modified = True
    return JsonResponse({'ok': True})


def api_add_expense(request):
    """Quick-add expense from the dashboard form."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    user = get_current_user(request)
    if not user:
        return JsonResponse({'ok': False, 'error': 'Нет пользователя. Напиши /start боту.'}, status=400)

    try:
        amount = Decimal(request.POST.get('amount', '0'))
        if amount <= 0:
            raise ValueError('Сумма должна быть больше 0')

        expense = Expense.objects.create(
            user=user,
            amount=amount,
            currency=request.POST.get('currency', 'USD'),
            category=request.POST.get('category', 'other'),
            description=request.POST.get('description', '')[:200],
            expense_date=request.POST.get('expense_date') or date.today(),
        )
        return JsonResponse({
            'ok': True,
            'id': expense.pk,
            'amount': str(expense.amount),
            'currency': expense.currency,
            'description': expense.description,
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
