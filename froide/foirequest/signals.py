from django.db.models import signals
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from .models import FoiRequest, FoiMessage, FoiAttachment, FoiEvent, FoiProject
from .utils import send_request_user_email


def trigger_index_update(klass, instance_pk):
    """ Trigger index update by save """
    try:
        obj = klass.objects.get(pk=instance_pk)
    except klass.DoesNotExist:
        return
    obj.save()


@receiver(FoiRequest.became_overdue,
        dispatch_uid="send_notification_became_overdue")
def send_notification_became_overdue(sender, **kwargs):
    send_request_user_email(
        sender,
        _("Request became overdue"),
        render_to_string("foirequest/emails/became_overdue.txt", {
            "request": sender,
            "go_url": sender.user.get_autologin_url(sender.get_absolute_short_url()),
            "site_name": settings.SITE_NAME
        }),
    )


@receiver(FoiRequest.became_asleep,
        dispatch_uid="send_notification_became_asleep")
def send_notification_became_asleep(sender, **kwargs):
    send_request_user_email(
        sender,
        _("Request became asleep"),
        render_to_string("foirequest/emails/became_asleep.txt", {
            "request": sender,
            "go_url": sender.user.get_autologin_url(
                sender.get_absolute_short_url()
            ),
            "site_name": settings.SITE_NAME
        }),
    )


@receiver(FoiRequest.message_received,
        dispatch_uid="notify_user_message_received")
def notify_user_message_received(sender, message=None, **kwargs):
    if message.kind != 'email':
        # All non-email received messages the user actively contributed
        # Don't inform them about it
        return

    send_request_user_email(
        sender,
        _("New reply to your request"),
        render_to_string("foirequest/emails/message_received_notification.txt", {
            "message": message,
            "request": sender,
            "publicbody": message.sender_public_body,
            "go_url": sender.user.get_autologin_url(
                message.get_absolute_short_url()
            ),
            "site_name": settings.SITE_NAME
        })
    )


@receiver(FoiRequest.public_body_suggested,
        dispatch_uid="notify_user_public_body_suggested")
def notify_user_public_body_suggested(sender, suggestion=None, **kwargs):
    if sender.user == suggestion.user:
        return

    send_request_user_email(
        sender,
        _("New suggestion for a Public Body"),
        render_to_string("foirequest/emails/public_body_suggestion_received.txt", {
            "suggestion": suggestion,
            "request": sender,
            "go_url": sender.user.get_autologin_url(
                sender.get_absolute_short_url()
            ),
            "site_name": settings.SITE_NAME
        })
    )


@receiver(FoiRequest.message_sent,
        dispatch_uid="set_last_message_date_on_message_sent")
def set_last_message_date_on_message_sent(sender, message=None, **kwargs):
    if message is not None:
        sender.last_message = sender.messages[-1].timestamp
        sender.save()


@receiver(FoiRequest.message_received,
        dispatch_uid="set_last_message_date_on_message_received")
def set_last_message_date_on_message_received(sender, message=None, **kwargs):
    if message is not None:
        sender.last_message = sender.messages[-1].timestamp
        sender.save()


@receiver(FoiProject.project_created,
        dispatch_uid="send_foiproject_created_confirmation")
def send_foiproject_created_confirmation(sender, **kwargs):
    subject = _("Your Freedom of Information Project has been created")
    template = "foirequest/emails/confirm_foi_project_created.txt"

    body = render_to_string(template, {
        "request": sender,
        "site_name": settings.SITE_NAME
    })

    send_request_user_email(sender, subject, body, add_idmark=False)


@receiver(FoiRequest.message_sent,
        dispatch_uid="send_foimessage_sent_confirmation")
def send_foimessage_sent_confirmation(sender, message=None, **kwargs):
    if message.kind != 'email':
        # All non-email sent messages are not interesting to users.
        # Don't inform them about it.
        return

    messages = sender.get_messages()
    if len(messages) == 1:
        if sender.project_id is not None:
            return
        subject = _("Your Freedom of Information Request was sent")
        template = "foirequest/emails/confirm_foi_request_sent.txt"
    else:
        subject = _("Your message was sent")
        template = "foirequest/emails/confirm_foi_message_sent.txt"

    body = render_to_string(template, {
        "request": sender,
        "publicbody": message.recipient_public_body,
        "message": message,
        "site_name": settings.SITE_NAME
    })

    send_request_user_email(sender, subject, body)


# Updating public body request counts
@receiver(FoiRequest.request_to_public_body,
        dispatch_uid="foirequest_increment_request_count")
def increment_request_count(sender, **kwargs):
    if not sender.public_body:
        return
    sender.public_body.number_of_requests += 1
    sender.public_body.save()


@receiver(signals.pre_delete, sender=FoiRequest,
        dispatch_uid="foirequest_decrement_request_count")
def decrement_request_count(sender, instance=None, **kwargs):
    if not instance.public_body:
        return
    instance.public_body.number_of_requests -= 1
    if instance.public_body.number_of_requests < 0:
        instance.public_body.number_of_requests = 0
    instance.public_body.save()


# Indexing

@receiver(signals.post_save, sender=FoiMessage,
        dispatch_uid='foimessage_delayed_update')
def foimessage_delayed_update(instance=None, created=False, **kwargs):
    if created and kwargs.get('raw', False):
        return
    trigger_index_update(FoiRequest, instance.request_id)


@receiver(signals.post_delete, sender=FoiMessage,
        dispatch_uid='foimessage_delayed_remove')
def foimessage_delayed_remove(instance, **kwargs):
    trigger_index_update(FoiRequest, instance.request_id)


@receiver(signals.post_save, sender=FoiAttachment,
        dispatch_uid='foiattachment_delayed_update')
def foiattachment_delayed_update(instance, created=False, **kwargs):
    if created and kwargs.get('raw', False):
        return
    trigger_index_update(FoiRequest, instance.belongs_to.request_id)


@receiver(signals.post_delete, sender=FoiAttachment,
        dispatch_uid='foiattachment_delayed_remove')
def foiattachment_delayed_remove(instance, **kwargs):
    try:
        if (instance.belongs_to is not None and
                    instance.belongs_to.request_id is not None):
            trigger_index_update(FoiRequest, instance.belongs_to.request_id)
    except FoiMessage.DoesNotExist:
        pass


# Event creation

@receiver(FoiRequest.message_sent, dispatch_uid="create_event_message_sent")
def create_event_message_sent(sender, message, **kwargs):
    FoiEvent.objects.create_event("message_sent", sender, user=sender.user,
            public_body=message.recipient_public_body)


@receiver(FoiRequest.message_received,
        dispatch_uid="create_event_message_received")
def create_event_message_received(sender, message=None, **kwargs):
    FoiEvent.objects.create_event("message_received", sender,
            user=sender.user,
            public_body=message.sender_public_body)


@receiver(FoiAttachment.attachment_published,
    dispatch_uid="create_event_followers_attachments_approved")
def create_event_followers_attachments_approved(sender, **kwargs):
    FoiEvent.objects.create_event("attachment_published",
            sender.belongs_to.request,
            user=sender.belongs_to.request.user,
            public_body=sender.belongs_to.request.public_body)


@receiver(FoiRequest.status_changed,
        dispatch_uid="create_event_status_changed")
def create_event_status_changed(sender, **kwargs):
    resolution = kwargs['resolution']
    data = kwargs['data']
    if data.get('costs', 0) > 0:
        FoiEvent.objects.create_event("reported_costs", sender,
                user=sender.user,
                public_body=sender.public_body, amount=data['costs'])
    elif resolution == "refused" and data['refusal_reason']:
        FoiEvent.objects.create_event("request_refused", sender,
                user=sender.user,
                public_body=sender.public_body, reason=data['refusal_reason'])
    elif resolution == "partially_successful" and data['refusal_reason']:
        FoiEvent.objects.create_event("partially_successful", sender,
                user=sender.user,
                public_body=sender.public_body, reason=data['refusal_reason'])
    else:
        FoiEvent.objects.create_event("status_changed", sender, user=sender.user,
            public_body=sender.public_body,
            status=FoiRequest.get_readable_status(resolution))


@receiver(FoiRequest.made_public,
        dispatch_uid="create_event_made_public")
def create_event_made_public(sender, **kwargs):
    FoiEvent.objects.create_event("made_public", sender, user=sender.user,
            public_body=sender.public_body)


@receiver(FoiRequest.public_body_suggested,
        dispatch_uid="create_event_public_body_suggested")
def create_event_public_body_suggested(sender, suggestion=None, **kwargs):
    FoiEvent.objects.create_event("public_body_suggested", sender, user=suggestion.user,
            public_body=suggestion.public_body)


@receiver(FoiRequest.became_overdue,
        dispatch_uid="create_event_became_overdue")
def create_event_became_overdue(sender, **kwargs):
    FoiEvent.objects.create_event("became_overdue", sender)


@receiver(FoiRequest.set_concrete_law,
        dispatch_uid="create_event_set_concrete_law")
def create_event_set_concrete_law(sender, **kwargs):
    FoiEvent.objects.create_event("set_concrete_law", sender,
            user=sender.user, name=kwargs['name'])


@receiver(FoiRequest.escalated,
    dispatch_uid="create_event_escalated")
def create_event_escalated(sender, **kwargs):
    FoiEvent.objects.create_event("escalated", sender,
            user=sender.user, public_body=sender.law.mediator)
