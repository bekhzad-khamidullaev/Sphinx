# room/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model # Используем get_user_model для User
from django.utils.translation import gettext_lazy as _
from django.templatetags.static import static # Для дефолтного аватара (если нужен)
from .models import Room, Message, Reaction, MessageReadStatus

User = get_user_model()

class BasicUserSerializer(serializers.ModelSerializer):
    """ Сериализатор для краткой информации о пользователе. """
    avatar_url = serializers.SerializerMethodField()
    display_name = serializers.CharField(source='display_name', read_only=True) # Используем свойство модели User

    class Meta:
        model = User # Указываем вашу кастомную модель User
        fields = ['id', 'username', 'display_name', 'avatar_url']

    def get_avatar_url(self, obj) -> str | None:
        request = self.context.get('request')
        if hasattr(obj, 'image') and obj.image and hasattr(obj.image, 'url') and obj.image.url:
            if request:
                try:
                    return request.build_absolute_uri(obj.image.url)
                except Exception: # Если build_absolute_uri не удался
                    return obj.image.url # Возвращаем относительный URL
            return obj.image.url
        # Опционально: вернуть URL к дефолтному аватару
        # default_avatar_path = 'img/user.svg'
        # if request:
        #     return request.build_absolute_uri(static(default_avatar_path))
        # return static(default_avatar_path)
        return None # Если аватара нет и дефолтный не используется


class ReactionSerializer(serializers.ModelSerializer):
    user = BasicUserSerializer(read_only=True) # Будет использовать обновленный BasicUserSerializer

    class Meta:
        model = Reaction
        fields = ['id', 'user', 'emoji', 'created_at']


class ReplyMessageSerializer(serializers.ModelSerializer):
    user = BasicUserSerializer(read_only=True) # Будет использовать обновленный BasicUserSerializer
    content_preview = serializers.SerializerMethodField()
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'user', 'content_preview', 'has_file', 'is_deleted', 'date_added']

    def get_content_preview(self, obj: Message) -> str:
        if obj.is_deleted:
            return _("[сообщение удалено]")
        if obj.file and not obj.content:
            return f"[{_('Файл')}: {obj.get_filename() or _('файл')}]"
        return obj.content[:70] + '...' if obj.content and len(obj.content) > 70 else obj.content

    def get_has_file(self, obj: Message) -> bool:
        return bool(obj.file)


class MessageSerializer(serializers.ModelSerializer):
    user = BasicUserSerializer(read_only=True) # Будет использовать обновленный BasicUserSerializer
    room_slug = serializers.SlugRelatedField(source='room', slug_field='slug', read_only=True)
    reactions = serializers.SerializerMethodField()
    reply_to = ReplyMessageSerializer(read_only=True, allow_null=True)
    file_url = serializers.SerializerMethodField()
    filename = serializers.CharField(source='get_filename', read_only=True, allow_null=True)
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'user', 'room_slug', 'content', 'file_url', 'filename', 'file_size_display', 'date_added',
            'edited_at', 'is_deleted', 'reply_to', 'reactions'
        ]
        read_only_fields = fields

    def get_file_url(self, obj: Message) -> str | None:
        request = self.context.get('request')
        if obj.file and hasattr(obj.file, 'url') and obj.file.url:
            try:
                if request:
                    return request.build_absolute_uri(obj.file.url)
                return obj.file.url
            except ValueError:
                return obj.file.url # Fallback
            except Exception:
                return obj.file.url # Fallback
        return None

    def get_file_size_display(self, obj: Message) -> str | None:
        if obj.file and hasattr(obj.file, 'size'):
            try:
                size = obj.file.size
                if size < 1024: return f"{size} B"
                elif size < 1024**2: return f"{size/1024:.1f} KB"
                elif size < 1024**3: return f"{size/(1024**2):.1f} MB"
                else: return f"{size/(1024**3):.1f} GB"
            except Exception: return None
        return None

    def get_reactions(self, obj: Message) -> dict:
        summary = {}
        current_user = self.context.get('consumer_user') # Или request.user

        for reaction_obj in obj.reactions.all(): # Предполагаем, что obj.reactions уже предзагружены с .select_related('user')
            emoji_val = reaction_obj.emoji
            if emoji_val not in summary:
                summary[emoji_val] = {'count': 0, 'users': [], 'reacted_by_current_user': False}
            summary[emoji_val]['count'] += 1
            summary[emoji_val]['users'].append(BasicUserSerializer(reaction_obj.user, context=self.context).data) # Передаем контекст
            if current_user and current_user == reaction_obj.user:
                summary[emoji_val]['reacted_by_current_user'] = True
        return summary


class RoomSerializer(serializers.ModelSerializer):
    participants = BasicUserSerializer(many=True, read_only=True)
    creator = BasicUserSerializer(read_only=True)
    unread_count = serializers.SerializerMethodField()
    has_unread = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            'id', 'name', 'slug', 'private', 'creator', 'participants',
            'created_at', 'updated_at', 'last_activity_at', 'is_archived',
            'unread_count', 'has_unread'
        ]
        read_only_fields = ('slug', 'creator', 'created_at', 'updated_at', 'last_activity_at', 'unread_count', 'has_unread')

    def create(self, validated_data):
        request_user = self.context['request'].user
        validated_data['creator'] = request_user
        room = Room.objects.create(**validated_data)
        if request_user not in room.participants.all():
            room.participants.add(request_user)
        return room
        
    def get_unread_count(self, obj: Room) -> int:
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return 0
        
        last_read_status = MessageReadStatus.objects.filter(user=user, room=obj).first()
        if not last_read_status or not last_read_status.last_read_message:
            return obj.messages.filter(is_deleted=False).count()
        
        return obj.messages.filter(is_deleted=False, date_added__gt=last_read_status.last_read_message.date_added).count()

    def get_has_unread(self, obj: Room) -> bool:
        return self.get_unread_count(obj) > 0