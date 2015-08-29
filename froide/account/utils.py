import datetime

from django.contrib.sessions.models import Session


def merge_accounts(old_user, new_user):
    from froide.foirequest.models import (FoiRequest, PublicBodySuggestion, FoiMessage,
            FoiEvent)
    from froide.foirequestfollower.models import FoiRequestFollower
    from froide.frontpage.models import FeaturedRequest
    from froide.publicbody.models import PublicBody

    mapping = [
        (FoiRequest, 'user', None),
        (PublicBodySuggestion, 'user', None),
        (FoiMessage, 'sender_user', None),
        (FoiEvent, 'user', None),
        (FoiRequestFollower, 'user', ('user', 'request',)),
        (FeaturedRequest, 'user', None),
        (PublicBody, '_created_by', None),
        (PublicBody, '_updated_by', None),
    ]

    for klass, attr, dupe in mapping:
        klass.objects.filter(**{attr: old_user}).update(**{attr: new_user})
        if dupe is None:
            continue
        already = set()
        for obj in klass.objects.filter(**{attr: new_user}):
            tup = tuple([getattr(obj, a) for a in dupe])
            if tup in already:
                obj.delete()
            else:
                already.add(tup)


def all_unexpired_sessions_for_user(user):
    user_sessions = []
    all_sessions = Session.objects.filter(expire_date__gte=datetime.datetime.now())
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
