# user_profiles/signals.py
import logging
import json
from django.db.models.signals import post_save, pre_save, post_delete, m2m_changed
from django.dispatch import Signal, receiver
from django.conf import settings
from django.core.mail import send_mail, mail_admins
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.html import strip_tags, format_html
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import User, Team, Department, JobTitle, TeamMembershipUser

logger = logging.getLogger(__name__)

user_promoted_to_staff_signal = Signal()
user_demoted_from_staff_signal = Signal()
user_account_activated_signal = Signal()
user_account_deactivated_signal = Signal()
user_assigned_to_team_signal = Signal()
user_removed_from_team_signal = Signal()
department_head_changed_signal = Signal()
team_leader_changed_signal = Signal()
user_email_changed_signal = Signal()
user_password_changed_signal = Signal()


def send_websocket_notification(group_name, event_type, message_data):
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {"type": event_type, "message": message_data}
            )
            logger.debug(f"WS sent to {group_name} (type: {event_type}): {message_data}")
        else:
            logger.warning("Channel layer not available for WebSocket notification.")
    except Exception as e:
        logger.error(f"Failed sending WS to {group_name}: {e}", exc_info=True)

def log_user_activity(user_actor, action_verb, target_object=None, details_dict=None, request=None):
    actor_username = user_actor.username if user_actor and hasattr(user_actor, 'username') else "System"
    target_repr = str(target_object) if target_object else "N/A"
    log_message = f"ACTIVITY_LOG: Actor='{actor_username}', Action='{action_verb}', Target='{target_repr}'"
    extended_details = details_dict.copy() if details_dict else {}
    if request:
        ip = request.META.get('REMOTE_ADDR')
        ua = request.META.get('HTTP_USER_AGENT')
        if ip: extended_details['ip_address'] = ip
        if ua: extended_details['user_agent'] = ua
    if extended_details:
        try:
            details_str = json.dumps(extended_details, ensure_ascii=False, cls=DjangoJSONEncoder, indent=1)
            log_message += f", Details={details_str}"
        except TypeError:
            log_message += f", Details(Raw)={str(extended_details)}"
    logger.info(log_message)


@receiver(pre_save, sender=User)
def user_pre_save_handler(sender, instance: User, **kwargs):
    if instance.pk:
        try:
            old_instance = User.objects.get(pk=instance.pk)
            instance._previous_is_staff = old_instance.is_staff
            instance._previous_is_active = old_instance.is_active
            instance._previous_is_superuser = old_instance.is_superuser
            instance._previous_job_title_id = old_instance.job_title_id
            instance._previous_department_id = old_instance.department_id
            instance._previous_email = old_instance.email
        except User.DoesNotExist:
            for attr in ['_previous_is_staff', '_previous_is_active', '_previous_is_superuser',
                         '_previous_job_title_id', '_previous_department_id', '_previous_email']:
                setattr(instance, attr, None)
    else:
        instance._previous_is_superuser = False

    if instance.pk and hasattr(instance, '_previous_is_superuser') and instance._previous_is_superuser and not instance.is_superuser:
        if User.objects.filter(is_superuser=True).exclude(pk=instance.pk).count() == 0:
            logger.warning(f"Signal: Attempt to remove superuser status from the last superuser: {instance.username}. Reverting in signal.")
            instance.is_superuser = True


@receiver(post_save, sender=User)
def user_post_save_notifications_and_logs(sender, instance: User, created: bool, update_fields=None, **kwargs):
    actor = kwargs.get('request_user', instance)
    request_obj = kwargs.get('request', None)

    site_name = getattr(settings, 'SITE_NAME', 'Sphinx')
    base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
    user_profile_url = f"{base_site_url}{reverse('admin:user_profiles_user_change', args=[instance.pk])}"
    try:
        user_profile_url = base_site_url + instance.get_absolute_url()
    except Exception:
        pass

    if created:
        log_details = {"email": instance.email, "is_staff": instance.is_staff}
        if actor and actor != instance : log_details["actor_id"] = actor.id if hasattr(actor, 'id') else str(actor)
        log_user_activity(actor, "USER_CREATED", instance, log_details, request=request_obj)

        if instance.get_setting('enable_email_notifications', True):
            try:
                login_url = base_site_url + reverse('user_profiles:base_login')
                subject = _("Добро пожаловать в {site_name}!").format(site_name=site_name)
                message = _("Здравствуйте, {display_name}!\n\nВаш аккаунт в системе {site_name} успешно создан.\nВаш логин: {username}\n\nВы можете войти в систему по ссылке: {login_url}\n\nС уважением,\nКоманда {site_name}").format(display_name=instance.display_name, site_name=site_name, username=instance.username, login_url=login_url)
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [instance.email], fail_silently=False)
                logger.info(f"Welcome email sent to {instance.email}")
            except Exception as e: logger.error(f"Failed to send welcome email to {instance.email}: {e}", exc_info=True)

        if getattr(settings, 'NOTIFY_ADMINS_ON_NEW_USER', True):
            try:
                mail_admins(subject=f"[{site_name}] Новый пользователь: {instance.username}", message=f"Зарегистрирован новый пользователь: {instance.display_name} ({instance.username}, {instance.email}).\nПрофиль: {user_profile_url}", fail_silently=True)
                logger.info(f"Admin notification for new user {instance.username} sent.")
            except Exception as e: logger.error(f"Failed to send new user notification to admins: {e}")
    else:
        log_details = {"updated_fields": list(update_fields) if update_fields else "all"}
        if actor and actor != instance : log_details["actor_id"] = actor.id if hasattr(actor, 'id') else str(actor)
        log_user_activity(actor, "USER_UPDATED", instance, log_details, request=request_obj)

        previous_email = getattr(instance, '_previous_email', instance.email)
        if instance.email != previous_email :
            user_email_changed_signal.send(sender=User, user=instance, old_email=previous_email, new_email=instance.email, actor=actor, request=request_obj)

        previous_is_staff = getattr(instance, '_previous_is_staff', None)
        if previous_is_staff is not None and instance.is_staff != previous_is_staff:
            (user_promoted_to_staff_signal if instance.is_staff else user_demoted_from_staff_signal).send(sender=User, user=instance, actor=actor, request=request_obj)

        previous_is_active = getattr(instance, '_previous_is_active', None)
        if previous_is_active is not None and instance.is_active != previous_is_active:
            (user_account_activated_signal if instance.is_active else user_account_deactivated_signal).send(sender=User, user=instance, actor=actor, request=request_obj)
            if not instance.is_active:
                for session in Session.objects.filter(expire_date__gte=timezone.now()):
                    session_data = session.get_decoded()
                    if str(session_data.get('_auth_user_id')) == str(instance.pk):
                        session.delete(); logger.info(f"Terminated session {session.session_key} for deactivated user {instance.username}")

@receiver(user_password_changed_signal)
def user_password_changed_notification(sender, user:User, request_info=None, **kwargs):
    actor = kwargs.get('actor', user)
    actor_username = actor.username if actor and hasattr(actor, 'username') else "System"
    ip_address = request_info.get('ip_address', _('неизвестен')) if request_info else _('неизвестен')
    log_user_activity(actor, "USER_PASSWORD_CHANGED", user, {"ip_address": ip_address, "request_user_agent": request_info.get('user_agent') if request_info else None}, request=kwargs.get('request'))

    if user.get_setting('enable_email_notifications', True):
        try:
            site_name = getattr(settings, 'SITE_NAME', 'Sphinx')
            subject = _("Уведомление о смене пароля в {site_name}").format(site_name=site_name)
            message = _("Здравствуйте, {display_name}.\n\nПароль для вашего аккаунта в системе {site_name} был недавно изменен.\nЕсли это были не вы, немедленно свяжитесь с поддержкой.\nIP: {ip}, Время: {time}").format(
                display_name=user.display_name, site_name=site_name, ip_address=ip_address, time=timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z"))
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
            logger.info(f"Password change notification email sent to {user.email}")
        except Exception as e: logger.error(f"Failed to send password change notification to {user.email}: {e}")

@receiver(post_delete, sender=User)
def user_post_delete_handler(sender, instance: User, **kwargs):
    actor = kwargs.get('request_user', None)
    log_user_activity(actor, "USER_DELETED", details_dict={"username": instance.username, "email": instance.email, "user_id": instance.id}, request=kwargs.get('request'))


@receiver(pre_save, sender=Team)
def team_pre_save_handler(sender, instance: Team, **kwargs):
    if instance.pk:
        try: old_instance = Team.objects.get(pk=instance.pk); instance._previous_team_leader_id = old_instance.team_leader_id
        except Team.DoesNotExist: instance._previous_team_leader_id = None
    else: instance._previous_team_leader_id = None

@receiver(post_save, sender=Team)
def team_post_save_handler(sender, instance: Team, created: bool, **kwargs):
    actor = kwargs.get('request_user', None)
    site_name = getattr(settings, 'SITE_NAME', 'Sphinx')
    base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
    try: team_url = base_site_url + instance.get_absolute_url()
    except: team_url = f"{base_site_url}{reverse('admin:user_profiles_team_change', args=[instance.pk])}"

    if created:
        log_details = {"leader_id": instance.team_leader_id, "department_id": instance.department_id, "actor_id": actor.id if actor and hasattr(actor, 'id') else None}
        log_user_activity(actor, "TEAM_CREATED", instance, log_details, request=kwargs.get('request'))
        if instance.team_leader and instance.team_leader.get_setting('enable_email_notifications', True) and (not actor or actor.id != instance.team_leader_id):
            try:
                subject = _("Вы назначены лидером команды '{team_name}' в {site_name}").format(team_name=instance.name, site_name=site_name)
                message = _("Здравствуйте, {leader_name}.\n\nВы были назначены лидером команды '{team_name}'.\nПодробнее: {team_url}").format(leader_name=instance.team_leader.display_name, team_name=instance.name, team_url=team_url)
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [instance.team_leader.email], fail_silently=True)
            except Exception as e: logger.error(f"Failed to send team leader assignment email to {instance.team_leader.email}: {e}")
    else:
        log_details = {"updated_fields": list(kwargs.get('update_fields', [])) or "all", "actor_id": actor.id if actor and hasattr(actor, 'id') else None}
        log_user_activity(actor, "TEAM_UPDATED", instance, log_details, request=kwargs.get('request'))
        previous_leader_id = getattr(instance, '_previous_team_leader_id', None)
        if previous_leader_id is not None and instance.team_leader_id != previous_leader_id:
            old_leader = User.objects.filter(pk=previous_leader_id).first()
            team_leader_changed_signal.send(sender=Team, team=instance, new_leader=instance.team_leader, old_leader=old_leader, actor=actor, request=kwargs.get('request'))

@receiver(post_delete, sender=Team)
def team_post_delete_handler(sender, instance: Team, **kwargs):
    actor = kwargs.get('request_user', None)
    log_user_activity(actor, "TEAM_DELETED", details_dict={"team_name": instance.name, "team_id": instance.id}, request=kwargs.get('request'))

@receiver(m2m_changed, sender=TeamMembershipUser)
def team_membership_changed_handler(sender, instance, action: str, reverse: bool, model: type, pk_set: set, **kwargs):
    actor = kwargs.get('request_user', None)
    request_obj = kwargs.get('request', None)

    if isinstance(instance, User):
        user_instance = instance
        if action in ["post_add", "post_remove"]:
            for team_pk in pk_set:
                team = Team.objects.filter(pk=team_pk).first()
                if team:
                    _process_single_membership_change(team, user_instance, action, actor, request_obj)
        elif action == "post_clear":
            log_user_activity(actor or user_instance, "USER_TEAMS_CLEARED", user_instance, {"details": "All teams cleared for user"}, request=request_obj)

    elif isinstance(instance, Team):
        team_instance = instance
        if action in ["post_add", "post_remove"]:
            users_affected_qs = User.objects.filter(pk__in=pk_set)
            for user_obj in users_affected_qs:
                _process_single_membership_change(team_instance, user_obj, action, actor, request_obj)
        elif action == "post_clear":
            log_user_activity(actor or team_instance.team_leader, "TEAM_MEMBERS_CLEARED", team_instance, {"details": "All members cleared from team"}, request=request_obj)
            _send_team_list_ws_update(team_instance)
            send_websocket_notification(f"team_{team_instance.id}", "team_detail_update", {"action": "members_cleared", "id": team_instance.id})


def _process_single_membership_change(team: Team, user: User, action: str, actor: User | None, request_obj=None):
    site_name = getattr(settings, 'SITE_NAME', 'Sphinx')
    base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
    try: team_url = base_site_url + team.get_absolute_url()
    except: team_url = f"{base_site_url}{reverse('admin:user_profiles_team_change', args=[team.pk])}"

    log_verb = None
    email_subject_template = ""
    email_text_template = ""
    signal_to_send = None

    if action == "post_add":
        log_verb = "USER_ADDED_TO_TEAM"
        email_subject_template = _("Вас добавили в команду '{team_name}' в {site_name}")
        email_text_template = _("Здравствуйте, {user_name}.\n\n{actor_info} добавил(а) Вас в команду '{team_name}'.\nПодробнее: {team_url}")
        signal_to_send = user_assigned_to_team_signal
    elif action == "post_remove":
        log_verb = "USER_REMOVED_FROM_TEAM"
        email_subject_template = _("Вас удалили из команды '{team_name}' в {site_name}")
        email_text_template = _("Здравствуйте, {user_name}.\n\n{actor_info} удалил(а) Вас из команды '{team_name}'.")
        signal_to_send = user_removed_from_team_signal
    else:
        return

    log_user_activity(actor, log_verb, target_object=user, details_dict={"team_id": team.id, "team_name": team.name}, request=request_obj)

    if signal_to_send:
        signal_to_send.send(sender=TeamMembershipUser, team=team, user=user, assigner=actor if action == "post_add" else None, remover=actor if action == "post_remove" else None, request=request_obj)

    if user.get_setting('enable_email_notifications', True) and email_subject_template:
        try:
            actor_info_text = _("Администратор")
            if actor and hasattr(actor, 'display_name') and actor != user:
                actor_info_text = actor.display_name
            elif actor and hasattr(actor, 'username') and actor != user:
                 actor_info_text = actor.username


            subject = email_subject_template.format(team_name=team.name, site_name=site_name)
            message = email_text_template.format(user_name=user.display_name, actor_info=actor_info_text, team_name=team.name, team_url=team_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        except Exception as e:
            logger.error(f"Failed to send '{action}' email to {user.email} for team '{team.name}': {e}")

    _send_team_list_ws_update(team)
    
    ws_detail_action = ""
    ws_detail_payload = {"id": team.id}
    if action == "post_add":
        ws_detail_action = "member_added"
        ws_detail_payload["added_member"] = {"id": user.id, "username": user.username, "display_name": user.display_name}
    elif action == "post_remove":
        ws_detail_action = "member_removed"
        ws_detail_payload["removed_member_pk"] = user.pk
    
    if ws_detail_action:
        send_websocket_notification(f"team_{team.id}", "team_detail_update", {"action": ws_detail_action, **ws_detail_payload})


def _send_team_list_ws_update(team: Team):
    current_members_details = [{"id": u.id, "username": u.username, "display_name": u.display_name} for u in team.members.all()]
    ws_list_message = {"action": "members_changed", "id": team.id, "name": team.name, "member_count": team.members.count(), "members": current_members_details}
    send_websocket_notification("teams_list", "team_update", ws_list_message)


@receiver(pre_save, sender=Department)
def department_pre_save_handler(sender, instance: Department, **kwargs):
    if instance.pk:
        try: old_instance = Department.objects.get(pk=instance.pk); instance._previous_head_id = old_instance.head_id; instance._previous_parent_id = old_instance.parent_id
        except Department.DoesNotExist: instance._previous_head_id = None; instance._previous_parent_id = None
    else: instance._previous_head_id = None; instance._previous_parent_id = None

@receiver(post_save, sender=Department)
def department_post_save_handler(sender, instance: Department, created: bool, **kwargs):
    actor = kwargs.get('request_user', None)
    site_name = getattr(settings, 'SITE_NAME', 'Sphinx'); base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
    try: department_url = base_site_url + instance.get_absolute_url()
    except: department_url = f"{base_site_url}{reverse('admin:user_profiles_department_change', args=[instance.pk])}"

    if created:
        log_details = {"parent_id": instance.parent_id, "head_id": instance.head_id, "actor_id": actor.id if actor and hasattr(actor, 'id') else None}
        log_user_activity(actor, "DEPARTMENT_CREATED", instance, log_details, request=kwargs.get('request'))
        if instance.head and instance.head.get_setting('enable_email_notifications', True) and (not actor or actor.id != instance.head_id):
            try:
                subject = _("Вы назначены руководителем отдела '{dept_name}' в {site_name}").format(dept_name=instance.name, site_name=site_name)
                message = _("Здравствуйте, {head_name}.\n\nВы были назначены руководителем отдела '{dept_name}'.\nПодробнее: {dept_url}").format(head_name=instance.head.display_name, dept_name=instance.name, dept_url=department_url)
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [instance.head.email], fail_silently=True)
            except Exception as e: logger.error(f"Failed to send department head assignment email to {instance.head.email}: {e}")
    else:
        log_details = {"updated_fields": list(kwargs.get('update_fields', [])) or "all", "actor_id": actor.id if actor and hasattr(actor, 'id') else None}
        log_user_activity(actor, "DEPARTMENT_UPDATED", instance, log_details, request=kwargs.get('request'))
        previous_head_id = getattr(instance, '_previous_head_id', None)
        if previous_head_id is not None and instance.head_id != previous_head_id:
            old_head = User.objects.filter(pk=previous_head_id).first()
            department_head_changed_signal.send(sender=Department, department=instance, new_head=instance.head, old_head=old_head, actor=actor, request=kwargs.get('request'))

@receiver(post_delete, sender=Department)
def department_post_delete_handler(sender, instance: Department, **kwargs):
    actor = kwargs.get('request_user', None)
    log_user_activity(actor, "DEPARTMENT_DELETED", details_dict={"department_name": instance.name, "department_id": instance.id}, request=kwargs.get('request'))


@receiver(post_save, sender=JobTitle)
def job_title_post_save_handler(sender, instance: JobTitle, created: bool, **kwargs):
    actor = kwargs.get('request_user', None)
    action_ws = "create" if created else "update"
    log_verb = f"JOBTITLE_{action_ws.upper()}D"
    log_user_activity(actor, log_verb, instance, request=kwargs.get('request'))
    send_websocket_notification("jobtitles_list", "jobtitle_update", {"action": action_ws, "id": instance.id, "name": instance.name, "description": instance.description, "user_count": instance.users.count()})

@receiver(post_delete, sender=JobTitle)
def job_title_post_delete_handler(sender, instance: JobTitle, **kwargs):
    actor = kwargs.get('request_user', None)
    log_user_activity(actor, "JOBTITLE_DELETED", details_dict={"jobtitle_name": instance.name, "jobtitle_id": instance.id}, request=kwargs.get('request'))
    send_websocket_notification("jobtitles_list", "jobtitle_update", {"action": "delete", "id": instance.id, "name": instance.name})


@receiver(m2m_changed, sender=User.groups.through)
def user_groups_changed_handler(sender, instance: User, action: str, pk_set: set, reverse: bool, model: type, **kwargs):
    if not reverse and action in ["post_add", "post_remove", "post_clear"]:
        actor = kwargs.get('request_user', None)
        request_obj = kwargs.get('request', None)
        acting_user_for_log = actor if actor else instance

        groups_affected_qs = Group.objects.filter(pk__in=pk_set)
        group_names_affected = list(groups_affected_qs.values_list('name', flat=True))
        log_action_map = {"post_add": "USER_GROUPS_ADDED", "post_remove": "USER_GROUPS_REMOVED", "post_clear": "USER_GROUPS_CLEARED"}
        log_verb = log_action_map.get(action)

        if log_verb:
            log_user_activity(acting_user_for_log, log_verb, instance, {"groups": group_names_affected or _("все")}, request=request_obj)

        current_groups_list = list(instance.groups.values('id', 'name'))
        ws_message_data = {"action": "permissions_updated", "id": instance.id, "username": instance.username, "groups": current_groups_list, "is_staff": instance.is_staff, "is_superuser": instance.is_superuser}
        send_websocket_notification("users_list", "user_update", ws_message_data)
        send_websocket_notification(f"user_{instance.id}", "user_profile_update", ws_message_data)

        if instance.get_setting('enable_email_notifications', True) and actor and actor != instance:
            site_name = getattr(settings, 'SITE_NAME', 'Sphinx'); base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
            try: profile_url = base_site_url + instance.get_absolute_url()
            except: profile_url = f"{base_site_url}{reverse('admin:user_profiles_user_change', args=[instance.pk])}"
            
            action_readable_map = {"post_add": _("Вам были добавлены группы прав"), "post_remove": _("У Вас были удалены группы прав"), "post_clear": _("Все ваши группы прав были очищены")}
            action_readable = action_readable_map.get(action, _("Ваши группы прав были изменены"))
            
            if action_readable:
                try:
                    subject = _("Изменение ваших прав доступа в {site_name}").format(site_name=site_name)
                    message = _("Здравствуйте, {un}.\n\n{ar}: {ga}.\nИзменение сделано: {act}.\nТекущие группы: {cg}.\nПрофиль: {pu}").format(
                        un=instance.display_name, ar=action_readable, ga=', '.join(group_names_affected) if group_names_affected else _("не указаны"),
                        act=actor.display_name if hasattr(actor, 'display_name') else str(actor), 
                        cg=', '.join([g['name'] for g in current_groups_list]) if current_groups_list else _("нет"), pu=profile_url)
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [instance.email], fail_silently=True)
                except Exception as e: logger.error(f"Failed to send permissions change email to {instance.email}: {e}")


@receiver(user_promoted_to_staff_signal)
def process_user_promoted_to_staff(sender, user: User, actor: User = None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_user_activity(actor or user, "USER_PROMOTED_STAFF_SIGNAL", user, {"details": _("Пользователь получил права сотрудника")}, request=request_obj)
    logger.info(f"User {user.username} promoted to staff. Actor: {actor.username if actor and hasattr(actor, 'username') else 'System'}.")
    if user.get_setting('enable_email_notifications', True):
        try:
            site_name = getattr(settings, 'SITE_NAME', 'Sphinx'); base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
            profile_url = base_site_url + user.get_absolute_url()
            subject = _("Вам предоставлен статус сотрудника в {site_name}").format(site_name=site_name)
            message = _("Здравствуйте, {dn}.\n\nВам предоставлен статус сотрудника с доступом к админ-панели.\n{pu}").format(dn=user.display_name, pu=profile_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        except Exception as e: logger.error(f"Failed to send staff promotion email to {user.email}: {e}")
    try:
        staff_group_name = getattr(settings, 'DEFAULT_STAFF_GROUP_NAME', "Сотрудники")
        staff_group, created = Group.objects.get_or_create(name=staff_group_name)
        if created: logger.info(f"Default staff group '{staff_group_name}' created.")
        if not user.groups.filter(name=staff_group_name).exists(): user.groups.add(staff_group)
    except Exception as e: logger.error(f"Error adding user {user.username} to default staff group '{staff_group_name}': {e}")

@receiver(user_demoted_from_staff_signal)
def process_user_demoted_from_staff(sender, user: User, actor: User = None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_user_activity(actor or user, "USER_DEMOTED_STAFF_SIGNAL", user, {"details": _("У пользователя отозваны права сотрудника")}, request=request_obj)
    logger.info(f"User {user.username} demoted from staff. Actor: {actor.username if actor and hasattr(actor, 'username') else 'System'}.")
    if user.get_setting('enable_email_notifications', True):
        try:
            site_name = getattr(settings, 'SITE_NAME', 'Sphinx'); base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
            profile_url = base_site_url + user.get_absolute_url()
            subject = _("У вас отозван статус сотрудника в {site_name}").format(site_name=site_name)
            message = _("Здравствуйте, {dn}.\n\nУ вас отозван статус сотрудника.\n{pu}").format(dn=user.display_name, pu=profile_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        except Exception as e: logger.error(f"Failed to send staff demotion email to {user.email}: {e}")
    try:
        staff_group_name = getattr(settings, 'DEFAULT_STAFF_GROUP_NAME', "Сотрудники")
        staff_group = Group.objects.filter(name=staff_group_name).first()
        if staff_group and user.groups.filter(name=staff_group_name).exists(): user.groups.remove(staff_group)
    except Exception as e: logger.error(f"Error removing user {user.username} from default staff group '{staff_group_name}': {e}")

@receiver(user_account_activated_signal)
def process_user_account_activated(sender, user: User, actor: User = None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_user_activity(actor or user, "USER_ACCOUNT_ACTIVATED_SIGNAL", user, {"details": _("Аккаунт активирован")}, request=request_obj)
    logger.info(f"User {user.username} account activated. Actor: {actor.username if actor and hasattr(actor, 'username') else 'System'}.")
    if user.get_setting('enable_email_notifications', True):
        try:
            site_name = getattr(settings, 'SITE_NAME', 'Sphinx'); base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
            profile_url = base_site_url + user.get_absolute_url()
            subject = _("Ваш аккаунт в {site_name} активирован").format(site_name=site_name)
            message = _("Здравствуйте, {dn}.\n\nВаш аккаунт был активирован.\n{pu}").format(dn=user.display_name, pu=profile_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        except Exception as e: logger.error(f"Failed to send account activation email to {user.email}: {e}")

@receiver(user_account_deactivated_signal)
def process_user_account_deactivated(sender, user: User, actor: User = None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_user_activity(actor or user, "USER_ACCOUNT_DEACTIVATED_SIGNAL", user, {"details": _("Аккаунт деактивирован")}, request=request_obj)
    logger.info(f"User {user.username} account deactivated. Actor: {actor.username if actor and hasattr(actor, 'username') else 'System'}.")
    if user.get_setting('enable_email_notifications', True):
        try:
            site_name = getattr(settings, 'SITE_NAME', 'Sphinx'); base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
            profile_url = base_site_url + user.get_absolute_url()
            subject = _("Ваш аккаунт в {site_name} деактивирован").format(site_name=site_name)
            message = _("Здравствуйте, {dn}.\n\nВаш аккаунт был деактивирован.\n{pu}").format(dn=user.display_name, pu=profile_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
        except Exception as e: logger.error(f"Failed to send account deactivation email to {user.email}: {e}")

@receiver(user_assigned_to_team_signal)
def process_user_assigned_to_team(sender, team: Team, user: User, assigner: User = None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_user_activity(assigner or user, "USER_ASSIGNED_TO_TEAM_SIGNAL", team, {"user_assigned_id": user.id, "user_assigned_username": user.username}, request=request_obj)
    logger.info(f"User {user.username} assigned to team {team.name}. Assigner: {assigner.username if assigner and hasattr(assigner, 'username') else 'System'}.")

@receiver(user_removed_from_team_signal)
def process_user_removed_from_team(sender, team: Team, user: User, remover: User = None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_user_activity(remover or user, "USER_REMOVED_FROM_TEAM_SIGNAL", team, {"user_removed_id": user.id, "user_removed_username": user.username}, request=request_obj)
    logger.info(f"User {user.username} removed from team {team.name}. Remover: {remover.username if remover and hasattr(remover, 'username') else 'System'}.")

@receiver(department_head_changed_signal)
def process_department_head_changed(sender, department: Department, new_head: User, old_head: User = None, actor: User = None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_details = {"new_head_id": new_head.id if new_head else None, "old_head_id": old_head.id if old_head else None}
    log_user_activity(actor, "DEPARTMENT_HEAD_CHANGED_SIGNAL", department, log_details, request=request_obj)
    logger.info(f"Department '{department.name}' head changed. New: {new_head.username if new_head else 'none'}. Old: {old_head.username if old_head else 'none'}. Actor: {actor.username if actor and hasattr(actor, 'username') else 'System'}")
    site_name = getattr(settings, 'SITE_NAME', 'Sphinx'); base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
    try: department_url = base_site_url + department.get_absolute_url()
    except: department_url = f"{base_site_url}{reverse('admin:user_profiles_department_change', args=[department.pk])}"
    if new_head and new_head.get_setting('enable_email_notifications', True) and (not actor or actor.id != new_head.id):
        try:
            subject = _("Вы назначены руководителем отдела '{dept_name}' в {site_name}").format(dept_name=department.name, site_name=site_name)
            message = _("Здравствуйте, {hn}.\n\nВы назначены руководителем отдела '{dn}'.\n{du}").format(hn=new_head.display_name, dn=department.name, du=department_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [new_head.email], fail_silently=True)
        except Exception as e: logger.error(f"Failed to send new dept head email to {new_head.email}: {e}")
    if old_head and old_head.get_setting('enable_email_notifications', True) and (not actor or actor.id != old_head.id):
        try:
            subject = _("Вы больше не руководитель отдела '{dept_name}' в {site_name}").format(dept_name=department.name, site_name=site_name)
            message = _("Здравствуйте, {ohn}.\n\nВы больше не руководитель отдела '{dn}'.\nНовый: {nhn}.\n{du}").format(ohn=old_head.display_name, dn=department.name, nhn=new_head.display_name if new_head else _("не назначен"), du=department_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [old_head.email], fail_silently=True)
        except Exception as e: logger.error(f"Failed to send old dept head email to {old_head.email}: {e}")

@receiver(team_leader_changed_signal)
def process_team_leader_changed(sender, team: Team, new_leader: User, old_leader: User = None, actor: User = None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_details = {"new_leader_id": new_leader.id if new_leader else None, "old_leader_id": old_leader.id if old_leader else None}
    log_user_activity(actor, "TEAM_LEADER_CHANGED", team, log_details, request=request_obj)
    logger.info(f"Team '{team.name}' leader changed. New: {new_leader.username if new_leader else 'none'}. Old: {old_leader.username if old_leader else 'none'}. Actor: {actor.username if actor and hasattr(actor, 'username') else 'System'}")
    site_name = getattr(settings, 'SITE_NAME', 'Sphinx'); base_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').strip('/')
    try: team_url = base_site_url + team.get_absolute_url()
    except: team_url = f"{base_site_url}{reverse('admin:user_profiles_team_change', args=[team.pk])}"
    if new_leader and new_leader.get_setting('enable_email_notifications', True) and (not actor or actor.id != new_leader.id):
        try:
            subject = _("Вы назначены лидером команды '{team_name}' в {site_name}").format(team_name=team.name, site_name=site_name)
            message = _("Здравствуйте, {ln}.\n\nВы назначены лидером команды '{tn}'.\n{tu}").format(ln=new_leader.display_name, tn=team.name, tu=team_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [new_leader.email], fail_silently=True)
        except Exception as e: logger.error(f"Failed to send new team leader email to {new_leader.email}: {e}")
    if old_leader and old_leader.get_setting('enable_email_notifications', True) and (not actor or actor.id != old_leader.id):
        try:
            subject = _("Вы больше не лидер команды '{team_name}' в {site_name}").format(team_name=team.name, site_name=site_name)
            message = _("Здравствуйте, {oln}.\n\nВы больше не лидер команды '{tn}'.\nНовый: {nln}.\n{tu}").format(oln=old_leader.display_name, tn=team.name, nln=new_leader.display_name if new_leader else _("не назначен"), tu=team_url)
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [old_leader.email], fail_silently=True)
        except Exception as e: logger.error(f"Failed to send old team leader email to {old_leader.email}: {e}")

@receiver(user_email_changed_signal)
def process_user_email_changed(sender, user:User, old_email:str, new_email:str, actor:User=None, **kwargs):
    request_obj = kwargs.get('request', None)
    log_user_activity(actor or user, "USER_EMAIL_CHANGED_SIGNAL", user, {"old_email": old_email, "new_email": new_email}, request=request_obj)
    logger.info(f"User {user.username} email changed from {old_email} to {new_email}. Actor: {actor.username if actor and hasattr(actor, 'username') else 'System'}")
    site_name = getattr(settings, 'SITE_NAME', 'Sphinx')
    try:
        subject = _("Ваш email в системе {site_name} был изменен").format(site_name=site_name)
        message_to_new = _("Здравствуйте, {dn}.\n\nВаш email в {sn} изменен на {ne}.\nЕсли это не вы, свяжитесь с поддержкой.").format(dn=user.display_name, sn=site_name, ne=new_email)
        send_mail(subject, message_to_new, settings.DEFAULT_FROM_EMAIL, [new_email], fail_silently=True)
        if old_email:
            message_to_old = _("Здравствуйте.\n\nEmail для аккаунта {un} в {sn} изменен с {oe} на {ne}.\nЕсли это не вы, свяжитесь с поддержкой.").format(un=user.username, sn=site_name, oe=old_email, ne=new_email)
            send_mail(subject, message_to_old, settings.DEFAULT_FROM_EMAIL, [old_email], fail_silently=True)
    except Exception as e: logger.error(f"Failed to send email change notification for user {user.username}: {e}")