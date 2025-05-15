# room/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from .models import Room, Message, Reaction # MessageReadStatus не нужен для API напрямую

User = get_user_model()

class BasicUserSerializer(serializers.ModelSerializer):
    """ Сериализатор для краткой информации о пользователе. """
    avatar_url = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'display_name', 'avatar_url']

    def get_avatar_url(self, obj):
        # Пример: если у вас есть поле 'image' в профиле пользователя
        # profile = getattr(obj, 'userprofile', None) # 'userprofile' - related_name от OneToOneField
        # if profile and hasattr(profile, 'image') and profile.image:
        #     return profile.image.url

        # Если поле 'image' прямо на модели User (менее вероятно для стандартной)
        if hasattr(obj, 'image') and obj.image:
             return obj.image.url
        return None # Или URL для дефолтного аватара

    def get_display_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        return obj.username


class ReactionSerializer(serializers.ModelSerializer):
    user = BasicUserSerializer(read_only=True)

    class Meta:
        model = Reaction
        fields = ['id', 'user', 'emoji', 'created_at']


class ReplyMessageSerializer(serializers.ModelSerializer): # Для вложенного ответа
    user = BasicUserSerializer(read_only=True)
    content_preview = serializers.SerializerMethodField()
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'user', 'content_preview', 'has_file', 'is_deleted', 'date_added']

    def get_content_preview(self, obj):
        if obj.is_deleted:
            return _("[сообщение удалено]")
        return obj.content[:70] + '...' if obj.content and len(obj.content) > 70 else obj.content

    def get_has_file(self, obj):
        return bool(obj.file)


class MessageSerializer(serializers.ModelSerializer):
    user = BasicUserSerializer(read_only=True)
    room_slug = serializers.SlugRelatedField(source='room', slug_field='slug', read_only=True)
    reactions = serializers.SerializerMethodField() # Динамически посчитанные реакции
    reply_to = ReplyMessageSerializer(read_only=True, allow_null=True)
    file_url = serializers.FileField(source='file', read_only=True, allow_null=True) # Только URL
    filename = serializers.CharField(source='get_filename', read_only=True, allow_null=True)

    class Meta:
        model = Message
        fields = [
            'id', 'user', 'room_slug', 'content', 'file_url', 'filename', 'date_added',
            'edited_at', 'is_deleted', 'reply_to', 'reactions'
        ]
        read_only_fields = ['id', 'user', 'room_slug', 'date_added', 'edited_at', 'reactions', 'file_url', 'filename']

    def get_reactions(self, obj):
        # Этот метод будет вызван DRF. В консьюмере мы можем заполнять это поле другим способом.
        # Для примера, если бы мы хотели агрегировать здесь:
        summary = {}
        # Оптимизация: если реакции уже предзагружены с аннотациями, использовать их
        if hasattr(obj, 'prefetched_reactions_summary'):
             return obj.prefetched_reactions_summary

        # Если нет, делаем запрос (менее эффективно при сериализации списка сообщений)
        for reaction_obj in obj.reactions.select_related('user').all(): # obj.reactions - это related_name
            emoji_val = reaction_obj.emoji
            if emoji_val not in summary:
                summary[emoji_val] = {'count': 0, 'users': [], 'reacted_by_current_user': False}
            summary[emoji_val]['count'] += 1
            summary[emoji_val]['users'].append(reaction_obj.user.username)
            # Проверка, отреагировал ли текущий пользователь (если есть request в контексте)
            request = self.context.get('request')
            if request and request.user == reaction_obj.user:
                summary[emoji_val]['reacted_by_current_user'] = True
        return summary


class RoomSerializer(serializers.ModelSerializer):
    participants = BasicUserSerializer(many=True, read_only=True)
    creator = BasicUserSerializer(read_only=True)
    # last_message = MessageSerializer(source='messages.first', read_only=True) # Можно добавить, но может быть медленно

    class Meta:
        model = Room
        fields = [
            'id', 'name', 'slug', 'private', 'creator', 'participants',
            'created_at', 'updated_at', 'last_activity_at', 'is_archived'
        ]
        read_only_fields = ('slug', 'creator', 'created_at', 'updated_at', 'last_activity_at')

    def create(self, validated_data):
        # Участники добавляются во view (perform_create) или сигналом
        request_user = self.context['request'].user
        validated_data['creator'] = request_user
        room = Room.objects.create(**validated_data)
        return room