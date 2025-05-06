# tasks/consumers.py
# -*- coding: utf-8 -*-

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import Task
from django.core.exceptions import ValidationError, ObjectDoesNotExist

logger = logging.getLogger(__name__)

class GenericConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = self.scope["url_route"]["kwargs"]["group"]
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        # This generic consumer just broadcasts what it receives.
        # Type should match a method name in the consumer.
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "broadcast_message", "message": data} # Example type
        )

    async def broadcast_message(self, event): # Handles "broadcast_message" type
        await self.send(text_data=json.dumps(event["message"]))


class TaskConsumer(AsyncWebsocketConsumer):
    DEFAULT_GROUP_NAME = "tasks_list" # General group for task list updates

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return

        # Group name can be dynamic based on URL or default
        self.group_name = (
            self.scope.get("url_route", {})
            .get("kwargs", {})
            .get("group_name", self.DEFAULT_GROUP_NAME) # Use 'group_name' if passed in URL kwargs
        )
        # Specific task updates might go to f"task_{task_id}"
        task_id_param = self.scope.get("url_route", {}).get("kwargs", {}).get("task_id")
        if task_id_param:
            self.task_specific_group_name = f"task_{task_id_param}"
            await self.channel_layer.group_add(self.task_specific_group_name, self.channel_name)
        
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(f"TaskConsumer connected user {user.id} to groups: {self.group_name}" + (f", {self.task_specific_group_name}" if task_id_param else ""))


    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, 'task_specific_group_name'):
            await self.channel_layer.group_discard(self.task_specific_group_name, self.channel_name)

    async def receive(self, text_data):
        # This consumer primarily receives messages from Django signals (server-side)
        # If client needs to send data (e.g., to update status), it should be handled here.
        # Example: Client sends message to update task status
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.send_error("Authentication required.")
            return

        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'update_status':
                task_id = data.get('task_id')
                new_status = data.get('status')
                if not task_id or not new_status:
                    await self.send_error("Task ID and new status are required.")
                    return

                await self.handle_status_update_request(task_id, new_status, user)
            else:
                logger.warning(f"TaskConsumer received unknown message type: {message_type}")
                # Optionally, broadcast to other clients if it's a chat-like feature
                # await self.channel_layer.group_send(self.group_name, {"type": "task_message", "message": data})

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format.")
        except Exception as e:
            logger.error(f"Error in TaskConsumer receive: {e}")
            await self.send_error(f"An unexpected error occurred: {str(e)}")

    @sync_to_async
    def _update_task_status(self, task_id, new_status, user):
        try:
            task = Task.objects.get(id=task_id)
            # Permission check
            if not task.has_permission(user, 'change_status'): # Assuming has_permission exists
                raise PermissionError("You do not have permission to change status for this task.")
            
            task.status = new_status
            # Pass user to save method if it's used for auditing or signals
            # setattr(task, '_updated_by_user', user) # Example
            task.save(update_fields=['status', 'updated_at']) # Add 'completion_date' if auto-set
            return task
        except ObjectDoesNotExist:
            raise ObjectDoesNotExist("Task not found.")
        except ValidationError as e:
            raise ValidationError(e.message_dict if hasattr(e, 'message_dict') else str(e))


    async def handle_status_update_request(self, task_id, new_status, user):
        try:
            task = await self._update_task_status(task_id, new_status, user)
            # Confirmation back to the requesting client
            await self.send(text_data=json.dumps({
                'type': 'status_update_confirmation',
                'task_id': task.id,
                'new_status': task.status,
                'status_display': task.status_display,
                'success': True
            }))
            # The post_save signal on Task model will send 'task_update' and 'list_update'
            # to appropriate groups automatically.
        except ObjectDoesNotExist:
            await self.send_error(f"Task {task_id} not found.", event_type='status_update_error')
        except PermissionError as e:
            await self.send_error(str(e), event_type='status_update_error')
        except ValidationError as e:
            error_messages = e.message_dict if hasattr(e, 'message_dict') else str(e)
            await self.send_error(error_messages, event_type='status_update_error')
        except Exception as e:
            logger.error(f"Error updating task status requested by client: {e}")
            await self.send_error(f"Server error during status update: {str(e)}", event_type='status_update_error')


    async def task_update(self, event): # Handles messages from Task post_save signal for task detail
        message = event["message"]
        await self.send(text_data=json.dumps(message))

    async def list_update(self, event): # Handles messages from Task post_save signal for task list
        message = event["message"]
        await self.send(text_data=json.dumps(message))
        
    async def project_update(self, event): # Handles messages from Project post_save signal
        message = event["message"]
        await self.send(text_data=json.dumps(message))

    async def send_error(self, message, event_type="error_message"):
        await self.send(text_data=json.dumps({
            'type': event_type,
            'message': message,
            'success': False
        }))


class TaskCommentConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs'].get('task_id')
        self.user = self.scope.get('user')

        if not self.task_id or not self.user or not self.user.is_authenticated:
            logger.warning(f"TaskCommentConsumer connection rejected: No task_id or user not authenticated.")
            await self.close()
            return

        has_perm = await self.check_task_permission()
        if not has_perm:
             logger.warning(f"TaskCommentConsumer connection rejected: User {self.user.username} has no view permission for task {self.task_id}.")
             await self.close()
             return

        self.room_group_name = f'task_comments_{self.task_id}'
        logger.info(f"TaskCommentConsumer connecting user {self.user.username} to {self.room_group_name}")

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            logger.info(f"TaskCommentConsumer disconnecting user {getattr(self.user, 'username', 'UnknownUser')} from {self.room_group_name}")
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def comment_message(self, event): # Type from group_send in signals.py
        message_data = event['message']
        logger.debug(f"TaskCommentConsumer sending comment message to group {self.room_group_name}: {message_data}")
        await self.send(text_data=json.dumps({
            'type': 'new_comment', # This type is for the client-side JS to handle
            'comment': message_data
        }))

    @sync_to_async
    def check_task_permission(self):
        try:
            task = Task.objects.get(pk=self.task_id)
            return task.has_permission(self.user, 'view')
        except Task.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking task permission in TaskCommentConsumer for task {self.task_id}: {e}")
            return False

# Simplified consumers for Category, Subcategory, Project, Team, User
# These are primarily for broadcasting updates triggered by model signals,
# assuming group names like "categories_list", "projects_list" etc. are used in signals.

class ModelUpdateConsumerBase(AsyncWebsocketConsumer):
    group_name_prefix = "unknown" # Override in subclass
    default_group_name_suffix = "_list"

    async def connect(self):
        user = self.scope.get('user')
        # Allow unauthenticated users for public lists, or add auth check
        # if not user or not user.is_authenticated:
        #     await self.close()
        #     return

        # Group name can be dynamic based on URL or default
        # Example: /ws/categories/  -> group "categories_list"
        # Example: /ws/project/123/updates/ -> group "project_123"
        group_kwarg = self.scope.get("url_route", {}).get("kwargs", {}).get("group_identifier")
        if group_kwarg:
            self.group_name = f"{self.group_name_prefix}_{group_kwarg}"
        else:
            self.group_name = f"{self.group_name_prefix}{self.default_group_name_suffix}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(f"{self.__class__.__name__} connected user {getattr(user, 'id', 'anonymous')} to group: {self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # This method name (e.g., 'category_update') must match the 'type' in channel_layer.group_send
    async def model_update_event(self, event): # Generic handler, specific name in group_send
        message = event["message"]
        await self.send(text_data=json.dumps(message))

    # Specific handlers that Django Channels will call based on 'type'
    async def category_update(self, event): await self.model_update_event(event)
    async def subcategory_update(self, event): await self.model_update_event(event)
    async def project_update(self, event): await self.model_update_event(event) # Already in TaskConsumer
    async def team_update(self, event): await self.model_update_event(event)
    async def user_update(self, event): await self.model_update_event(event)


class CategoryConsumer(ModelUpdateConsumerBase):
    group_name_prefix = "categories"
    # Signal for TaskCategory should send to "categories_list" with type "category_update"

class SubcategoryConsumer(ModelUpdateConsumerBase):
    group_name_prefix = "subcategories"
    # Signal for TaskSubcategory should send to "subcategories_list" with type "subcategory_update"

class ProjectConsumer(ModelUpdateConsumerBase): # This might be redundant if TaskConsumer handles project_updates
    group_name_prefix = "projects"
    # Signal for Project should send to "projects_list" with type "project_update"

class TeamConsumer(ModelUpdateConsumerBase):
    group_name_prefix = "teams"
    # Signal for Team should send to "teams_list" with type "team_update"

class UserConsumer(ModelUpdateConsumerBase):
    group_name_prefix = "users" # Careful with user-specific data vs general user list updates
    # Signal for User should send to "users_list" (or specific user group) with type "user_update"