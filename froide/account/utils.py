from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.contrib.sessions.models import Session

from froide.helper.email_sending import send_mail

from . import account_canceled, account_merged
from .models import User


EXPIRE_UNCONFIRMED_USERS_AGE = timedelta(days=30)
CANCEL_DEACTIVATED_USERS_AGE = timedelta(days=100)


def send_mail_users(subject, body, users,
              **kwargs):
    for user in users:
        send_mail_user(
            subject, body, user,
            **kwargs
        )


def send_mail_user(subject, body, user: User,
                   ignore_active=False, **kwargs):
    if not ignore_active and not user.is_active:
        return
    if not user.email:
        return

    return send_mail(subject, body, user.email, bounce_check=False, **kwargs)


def send_template_mail(user: User, subject: str, body: str, **kwargs):
    mail_context = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'name': user.get_full_name(),
        'url': user.get_autologin_url('/'),
    }
    user_subject = subject.format(**mail_context)
    user_body = body.format(**mail_context)
    return user.send_mail(
        user_subject,
        user_body,
        **kwargs
    )


def merge_accounts(old_user, new_user):
    account_merged.send(
        sender=User, old_user=old_user, new_user=new_user
    )
    start_cancel_account_process(old_user)


def move_ownership(model, attr, old_user, new_user, dupe=None):
    model.objects.filter(**{attr: old_user}).update(**{attr: new_user})
    if dupe is None:
        return
    already = set()
    for obj in model.objects.filter(**{attr: new_user}):
        tup = tuple([getattr(obj, a) for a in dupe])
        if tup in already:
            obj.delete()
        else:
            already.add(tup)


def all_unexpired_sessions_for_user(user):
    user_sessions = []
    all_sessions = Session.objects.filter(expire_date__gte=timezone.now())
    for session in all_sessions:
        session_data = session.get_decoded()
        if user.pk == session_data.get('_auth_user_id'):
            user_sessions.append(session.pk)
    return Session.objects.filter(pk__in=user_sessions)


def delete_all_unexpired_sessions_for_user(user, session_to_omit=None):
    session_list = all_unexpired_sessions_for_user(user)
    if session_to_omit is not None:
        session_list.exclude(session_key=session_to_omit.session_key)
    session_list.delete()


def start_cancel_account_process(user):
    from .tasks import cancel_account_task

    user.private = True
    user.email = None
    user.is_active = False
    user.set_unusable_password()
    user.date_deactivated = timezone.now()

    user.save()
    delete_all_unexpired_sessions_for_user(user)

    # Asynchronously delete account
    # So more expensive anonymization can run in the background
    cancel_account_task.delay(user.pk)


def cancel_user(user):
    with transaction.atomic():
        account_canceled.send(sender=User, user=user)

    user.organization = ''
    user.organization_url = ''
    user.private = True
    user.newsletter = False
    user.terms = False
    user.address = ''
    user.profile_text = ''
    user.profile_photo.delete()
    user.save()
    user.first_name = ''
    user.last_name = ''
    user.is_trusted = False
    user.is_staff = False
    user.is_superuser = False
    user.is_active = False
    user.date_deactivated = timezone.now()
    user.is_deleted = True
    user.date_left = timezone.now()
    user.email = None
    user.set_unusable_password()
    user.username = 'u%s' % user.pk
    user.save()
    delete_all_unexpired_sessions_for_user(user)


def delete_unconfirmed_users():
    time_ago = timezone.now() - EXPIRE_UNCONFIRMED_USERS_AGE
    expired_users = User.objects.filter(
        is_active=False,
        is_deleted=False,
        last_login__isnull=True,
        date_joined__lt=time_ago
    )
    for user in expired_users:
        start_cancel_account_process(user)


def delete_deactivated_users():
    time_ago = timezone.now() - CANCEL_DEACTIVATED_USERS_AGE
    expired_users = User.objects.filter(
        is_active=False,
        is_deleted=False,
        date_deactivated__lt=time_ago
    )
    for user in expired_users:
        start_cancel_account_process(user)
