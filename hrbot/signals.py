# hrbot/signals.py
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.conf import settings
from telegram import Bot
from django.utils.translation import gettext_lazy as _
from .models import TelegramUser

# перед сохранением запомним старое значение approved
@receiver(pre_save, sender=TelegramUser)
def _store_prev_approved(sender, instance, **kwargs):
    if instance.pk:
        old = sender.objects.get(pk=instance.pk)
        instance._previous_approved = old.approved
    else:
        instance._previous_approved = False

# после сохранения — если только что одобрили, шлём сообщение
@receiver(post_save, sender=TelegramUser)
def notify_on_approval(sender, instance, created, **kwargs):
    # не на создании, а при обновлении из False → True
    if not created and not instance._previous_approved and instance.approved:
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        chat_id = instance.telegram_id
        text = str(_("🎉 Ваш доступ подтверждён! Теперь можете начать оценку: /start"))
        bot.send_message(chat_id=chat_id, text=text)
