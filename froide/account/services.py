import hashlib
import re
import hmac
from urllib.parse import urlencode

from django.conf import settings
from django.template.defaultfilters import slugify
from django.template.loader import render_to_string
from django.utils.crypto import constant_time_compare
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from froide.helper.text_utils import replace_custom, replace_word
from froide.helper.db_utils import save_obj_unique
from froide.helper.email_sending import send_mail

from .models import User
from . import account_activated


def get_user_for_email(email):
    try:
        return User.objects.get(email=email)
    except User.DoesNotExist:
        return False


class AccountService(object):
    def __init__(self, user):
        self.user = user

    @classmethod
    def get_username_base(self, firstname, lastname):
        base = ""
        first = slugify(firstname)
        last = slugify(lastname)
        if first and last:
            base = "%s.%s" % (first[0], last)
        elif last:
            base = last
        elif first:
            base = first
        else:
            base = "user"
        base = base[:27]
        return base

    @classmethod
    def create_user(cls, **data):
        existing_user = get_user_for_email(data['user_email'])
        if existing_user:
            return existing_user, None, False

        user = User(
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['user_email']
        )
        username_base = cls.get_username_base(user.first_name, user.last_name)

        user.is_active = False
        if 'password' in data:
            password = data['password']
        else:
            password = User.objects.make_random_password()
        user.set_password(password)

        user.private = data['private']

        for key in ('address', 'organization', 'organization_url'):
            setattr(user, key, data.get(key, ''))

        # ensure username is unique
        user.username = username_base
        save_obj_unique(user, 'username', postfix_format='_{count}')

        return user, password, True

    def confirm_account(self, secret, request_id=None):
        if not self.check_confirmation_secret(secret, request_id):
            return False
        self.user.is_active = True
        self.user.save()
        account_activated.send_robust(sender=self.user)
        return True

    def get_autologin_url(self, url):
        return settings.SITE_URL + reverse('account-go', kwargs={
            "user_id": self.user.id,
            "secret": self.generate_autologin_secret(),
            "url": url
        })

    def check_autologin_secret(self, secret):
        return constant_time_compare(self.generate_autologin_secret(), secret)

    def generate_autologin_secret(self):
        to_sign = [str(self.user.pk)]
        if self.user.last_login:
            to_sign.append(self.user.last_login.strftime("%Y-%m-%dT%H:%M:%S"))
        return hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            (".".join(to_sign)).encode('utf-8'),
            digestmod=hashlib.md5
        ).hexdigest()

    def check_confirmation_secret(self, secret, *args):
        return constant_time_compare(
                secret,
                self.generate_confirmation_secret(*args)
        )

    def generate_confirmation_secret(self, *args):
        if self.user.email is None:
            return ''
        to_sign = [str(self.user.pk), self.user.email]
        for a in args:
            to_sign.append(str(a))
        if self.user.last_login:
            to_sign.append(self.user.last_login.strftime("%Y-%m-%dT%H:%M:%S"))
        return hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            (".".join(to_sign)).encode('utf-8'),
            digestmod=hashlib.md5
        ).hexdigest()

    def send_confirmation_mail(self, request_id=None, password=None,
                               reference=None, redirect_url=None):
        secret = self.generate_confirmation_secret(request_id)
        url_kwargs = {"user_id": self.user.pk, "secret": secret}
        if request_id:
            url_kwargs['request_id'] = request_id
        url = reverse('account-confirm', kwargs=url_kwargs)

        params = {}
        if reference:
            params['ref'] = reference.encode('utf-8')
        if redirect_url:
            params['next'] = redirect_url.encode('utf-8')
        if params:
            url = '%s?%s' % (url, urlencode(params))

        templates = []
        html_templates = []
        subject_templates = []
        if reference is not None:
            ref = reference.split(':', 1)[0]
            template_name = 'account/emails/{}/confirmation_mail'.format(
                ref
            )
            templates.append(template_name + '.txt')
            html_templates.append(template_name + '.html')
            subject_templates.append(
                'account/emails/{}/confirmation_mail_subject.txt'.format(ref)
            )

        templates.append('account/emails/confirmation_mail.txt')
        html_templates.append('account/emails/confirmation_mail.html')
        subject_templates.append('account/emails/confirmation_mail_subject.txt')

        context = {
            'url': settings.SITE_URL + url,
            'password': password,
            'name': self.user.get_full_name(),
            'site_name': settings.SITE_NAME,
            'site_url': settings.SITE_URL
        }

        message = render_to_string(templates, context)
        html_message = render_to_string(html_templates, context)

        subject = render_to_string(subject_templates, context)

        self.user.send_mail(
            subject, message,
            ignore_active=True,
            html=html_message
        )

    def send_confirm_action_mail(self, url, title, reference=None, redirect_url=None,
                                 template='account/emails/confirm_action.txt'):
        secret_url = self.get_autologin_url(url)

        params = {}
        if reference:
            params['ref'] = reference.encode('utf-8')
        if redirect_url:
            params['next'] = redirect_url.encode('utf-8')
        if params:
            secret_url = '%s?%s' % (secret_url, urlencode(params))

        message = render_to_string(
            template, {
                'url': secret_url,
                'title': title,
                'name': self.user.get_full_name(),
                'site_name': settings.SITE_NAME,
                'site_url': settings.SITE_URL
            }
        )

        # Translators: Mail subject
        subject = str(_("%(site_name)s: please confirm your action") % {
            "site_name": settings.SITE_NAME
        })
        self.user.send_mail(
            subject,
            message,
        )

    def send_reminder_mail(self, reference=None, redirect_url=None,
                           template='account/emails/account_reminder.txt'):
        secret_url = self.get_autologin_url(reverse('account-show'))

        message = render_to_string(
            template, {
                'url': secret_url,
                'name': self.user.get_full_name(),
                'site_name': settings.SITE_NAME,
                'site_url': settings.SITE_URL
            }
        )

        # Translators: Mail subject
        subject = str(_("%(site_name)s: account reminder") % {
            "site_name": settings.SITE_NAME
        }),
        self.user.send_mail(
            subject,
            message,
        )

    def send_email_change_mail(self, email):
        secret = self.generate_confirmation_secret(email)
        url_kwargs = {
            "user_id": self.user.pk,
            "secret": secret,
            "email": email
        }
        url = '%s%s?%s' % (
            settings.SITE_URL,
            reverse('account-change_email'),
            urlencode(url_kwargs)
        )
        message = render_to_string('account/emails/change_email.txt', {
            'url': url,
            'name': self.user.get_full_name(),
            'site_name': settings.SITE_NAME,
            'site_url': settings.SITE_URL
        })
        # Translators: Mail subject
        subject = str(_("%(site_name)s: please confirm your new email address") % {
            "site_name": settings.SITE_NAME
        })
        send_mail(
            subject,
            message,
            email
        )

    def apply_name_redaction(self, content, replacement=''):
        if not self.user.private:
            return content

        if self.user.is_deleted:
            # No more info present about user to redact
            return content

        needles = [
            self.user.last_name, self.user.first_name,
            self.user.get_full_name()
        ]
        if self.user.organization:
            needles.append(self.user.organization)

        needles = [re.escape(n) for n in needles]

        for needle in needles:
            content = re.sub(needle, replacement, content, flags=re.I | re.U)

        return content

    def apply_message_redaction(self, content, replacements=None):
        if replacements is None:
            replacements = {}

        if self.user.is_deleted:
            # No more info present about user to redact
            return content

        if self.user.address and replacements.get('address') is not False:
            for line in self.user.address.splitlines():
                if line.strip():
                    content = content.replace(line,
                            replacements.get('address',
                                str(_("<< Address removed >>")))
                    )

        if self.user.email and replacements.get('email') is not False:
            content = content.replace(self.user.email,
                    replacements.get('email',
                    str(_("<< Email removed >>")))
            )

        if not self.user.private or replacements.get('name') is False:
            return content

        name_replacement = replacements.get('name',
                str(_("<< Name removed >>")))

        content = replace_custom(settings.FROIDE_CONFIG['greetings'],
                name_replacement, content)

        content = replace_word(self.user.last_name, name_replacement, content)
        content = replace_word(self.user.first_name, name_replacement, content)
        content = replace_word(self.user.get_full_name(), name_replacement, content)

        if self.user.organization:
            content = replace_word(self.user.organization, name_replacement, content)

        return content
