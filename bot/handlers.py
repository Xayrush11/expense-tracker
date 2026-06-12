"""
Telegram bot handlers.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'expense_tracker.settings')
django.setup()

from datetime import date
from decimal import Decimal

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, MenuButtonWebApp
from telegram.ext import ContextTypes

from accounts.models import TelegramUser
from expenses.models import Expense
from .ai_parser import transcribe_voice, parse_expense


def _web_app_url() -> str:
    return os.getenv('WEB_APP_URL', '').rstrip('/')


async def get_or_create_user(tg_user) -> TelegramUser:
    user, _ = await TelegramUser.objects.aget_or_create(
        telegram_id=tg_user.id,
        defaults={
            'username': tg_user.username or '',
            'first_name': tg_user.first_name or '',
        },
    )
    return user


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user)
    name = user.first_name or user.username or 'друг'

    web_url = _web_app_url()
    keyboard = None
    if web_url:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                '📊 Открыть дашборд',
                web_app=WebAppInfo(url=web_url),
            )
        ]])

    await update.message.reply_text(
        f'👋 Привет, {name}!\n\n'
        '💸 *Трекер расходов* — просто отправь голосовое сообщение '
        'вида «потратил 50 тысяч сум на такси» и я всё запишу.\n\n'
        '📌 Команды:\n'
        '/stats — статистика за месяц\n'
        '/last  — последние 5 расходов\n'
        '/app   — открыть дашборд\n'
        '/delete — удалить последний расход',
        parse_mode='Markdown',
        reply_markup=keyboard,
    )


# ─── /app ─────────────────────────────────────────────────────────────────────

async def cmd_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    web_url = _web_app_url()
    if not web_url:
        await update.message.reply_text(
            '⚠️ Сайт ещё не задеплоен. Запусти сайт и добавь WEB_APP_URL в .env',
        )
        return
    await update.message.reply_text(
        '📊 Открываю дашборд...',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton('📊 Открыть дашборд', web_app=WebAppInfo(url=web_url))
        ]]),
    )


# ─── /stats ───────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user)
    today = date.today()
    month_start = today.replace(day=1)

    from django.db.models import Sum
    qs = Expense.objects.filter(user=user, expense_date__gte=month_start)

    total = await qs.aaggregate(t=Sum('amount'))
    count = await qs.acount()
    total_val = total['t'] or Decimal('0')

    lines = [f'📊 *Статистика за {today.strftime("%B %Y")}*\n']
    lines.append(f'💰 Итого: {total_val}')
    lines.append(f'🔢 Транзакций: {count}\n')

    cats = qs.values('category').annotate(s=Sum('amount')).order_by('-s')
    async for c in cats:
        icon = Expense.CATEGORY_ICONS.get(c['category'], '📦')
        label = dict(Expense.CATEGORY_CHOICES).get(c['category'], c['category'])
        lines.append(f'{icon} {label}: {c["s"]}')

    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


# ─── /last ────────────────────────────────────────────────────────────────────

async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user)
    lines = ['📋 *Последние 5 расходов:*\n']
    async for e in Expense.objects.filter(user=user).order_by('-expense_date', '-created_at')[:5]:
        lines.append(
            f'{e.category_icon} {e.description}\n'
            f'   💸 {e.amount} {e.currency} · {e.expense_date}'
        )
    if len(lines) == 1:
        lines.append('Расходов пока нет.')
    await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')


# ─── /delete ──────────────────────────────────────────────────────────────────

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user)
    last = await Expense.objects.filter(user=user).order_by('-created_at').afirst()
    if not last:
        await update.message.reply_text('❌ Нечего удалять.')
        return
    desc = last.description
    await last.adelete()
    await update.message.reply_text(f'🗑️ Удалено: *{desc}*', parse_mode='Markdown')


# ─── Voice message ────────────────────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update.effective_user)
    msg = await update.message.reply_text('🎙️ Обрабатываю...')

    voice = update.message.voice
    tg_file = await context.bot.get_file(voice.file_id)
    ogg_bytes = await tg_file.download_as_bytearray()

    try:
        transcript = await transcribe_voice(bytes(ogg_bytes))
        data = await parse_expense(transcript)

        if not data['amount'] or float(data['amount']) <= 0:
            await msg.edit_text(
                f'🎙️ Услышал: _{transcript}_\n\n'
                '❓ Не смог определить сумму. Попробуй сказать чётче, например:\n'
                '*«Потратил пятьдесят тысяч сум на такси»*',
                parse_mode='Markdown'
            )
            return

        expense = await Expense.objects.acreate(
            user=user,
            amount=Decimal(str(data['amount'])),
            currency=data.get('currency', 'USD'),
            category=data.get('category', 'other'),
            description=data.get('description', transcript[:100]),
            voice_transcript=transcript,
            expense_date=date.fromisoformat(data['expense_date']),
        )

        symbols = {'USD': '$', 'UZS': 'сум', 'RUB': '₽'}
        sym = symbols.get(expense.currency, expense.currency)

        reply = (
            f'✅ *Сохранено!*\n\n'
            f'{expense.category_icon} {expense.category_label}\n'
            f'💸 {expense.amount} {sym}\n'
            f'📝 {expense.description}\n\n'
            f'🎙️ _{transcript}_'
        )

        web_url = _web_app_url()
        keyboard = None
        if web_url:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton('📊 Посмотреть в дашборде', web_app=WebAppInfo(url=web_url))
            ]])

        await msg.edit_text(reply, parse_mode='Markdown', reply_markup=keyboard)

    except Exception as exc:
        await msg.edit_text(
            f'⚠️ Ошибка обработки: `{exc}`',
            parse_mode='Markdown'
        )
