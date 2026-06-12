"""
Entry point: runs the Telegram bot as a separate process.
Usage: python -m bot.bot  (from project root with DJANGO_SETTINGS_MODULE set)
"""
import asyncio
import logging
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'expense_tracker.settings')

from dotenv import load_dotenv
load_dotenv()
django.setup()

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from bot.handlers import cmd_start, cmd_app, cmd_stats, cmd_last, cmd_delete, handle_voice

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error('TELEGRAM_BOT_TOKEN is not set in .env')
        sys.exit(1)

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('app', cmd_app))
    app.add_handler(CommandHandler('stats', cmd_stats))
    app.add_handler(CommandHandler('last', cmd_last))
    app.add_handler(CommandHandler('delete', cmd_delete))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    logger.info('Bot is running...')
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
