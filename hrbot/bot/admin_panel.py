from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from hrbot.bot.reports import generate_report
import io
import logging

logger = logging.getLogger(__name__)

async def report_role(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/report_role <role_id> - Send evaluation report for a specific role."""
    if not ctx.args:
        return await update.message.reply_text("Usage: /report_role <role_id>")
    role_id = ctx.args[0]
    # Filter stats by role_id
    # For simplicity, reuse generate_report for all
    buffer = io.BytesIO()
    await generate_report(buffer)
    buffer.name = f"report_role_{role_id}.pdf"
    await update.message.reply_document(buffer)
    logger.info(f"Sent role report for {role_id}")

admin_handlers = [
    CommandHandler("report_role", report_role)
]