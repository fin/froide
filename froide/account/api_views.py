from rest_framework import serializers, views, response

from oauth2_provider.contrib.rest_framework import (
    IsAuthenticatedOrTokenHasScope
)

from .models import User


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'private')

    def to_representation(self, obj):
        default = super(UserSerializer, self).to_representation(obj)
        if obj.is_superuser:
            default['is_superuser'] = True
        if obj.is_staff:
            default['is_staff'] = True
        return default


class UserEmailSerializer(UserSerializer):
    class Meta:
        model = User
        fields = UserSerializer.Meta.fields + ('email',)


class UserDetailSerializer(UserSerializer):
    full_name = serializers.SerializerMethodField()
    profile_photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = UserSerializer.Meta.fields + (
            'first_name', 'last_name', 'full_name', 'username',
            'profile_photo',
        )

    def get_full_name(self, obj):
        return obj.get_full_name()

    def profile_photo(self, obj):
        if obj.profile_photo:
            return obj.profile_photo.url
        return None


class UserEmailDetailSerializer(UserDetailSerializer):
    class Meta:
        model = User
        fields = UserDetailSerializer.Meta.fields + ('email',)


class UserFullSerializer(UserEmailDetailSerializer):
    class Meta:
        model = User
        fields = UserEmailDetailSerializer.Meta.fields + ('address',)


class ProfileView(views.APIView):
    permission_classes = [IsAuthenticatedOrTokenHasScope]
    required_scopes = ['read:user']

    def get(self, request, format=None):
        token = request.auth
        user = request.user
        if token:
            has_email = token.is_valid(['read:email'])
            has_profile = token.is_valid(['read:profile'])
            if has_email and has_profile:
                serializer = UserEmailDetailSerializer(user)
            elif has_email:
                serializer = UserEmailSerializer(user)
            elif has_profile:
                serializer = UserDetailSerializer(user)
            else:
                serializer = UserSerializer(user)
        else:
            # if token is None, user is currently logged in user
            serializer = UserFullSerializer(user)
        return response.Response(serializer.data)
