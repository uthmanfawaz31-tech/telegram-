import asyncio
import datetime
import logging
import random
import re
from typing import List, Dict, Any, Tuple, Optional

from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from app.core.config import settings

logger = logging.getLogger(__name__)

EMOJIS = ["✨", "🚀", "📢", "💬", "🔥", "💡", "🌟", "🎯", "📌", "✅", "⚡", "💎"]

class TelegramService:
    def __init__(self, session_string: Optional[str] = None, api_id: Optional[str] = None, api_hash: Optional[str] = None):
        self.api_id = int(api_id) if (api_id and str(api_id).strip().isdigit()) else (int(settings.TELEGRAM_API_ID) if (settings.TELEGRAM_API_ID and str(settings.TELEGRAM_API_ID).strip().isdigit()) else None)
        self.api_hash = (api_hash.strip() if api_hash else settings.TELEGRAM_API_HASH.strip()) if (api_hash or settings.TELEGRAM_API_HASH) else ""
        
        self.session_string = session_string
        self.client = TelegramClient(
            StringSession(session_string),
            self.api_id or 0,
            self.api_hash or ""
        )

    async def connect(self):
        if not self.api_id or not self.api_hash:
            logger.error("TELEGRAM_API_ID or TELEGRAM_API_HASH is missing")
            raise ValueError("Telegram API credentials (ID and Hash) are required. Please configure them in Settings.")
        
        if not self.client.is_connected():
            await self.client.connect()

    async def disconnect(self):
        try:
            if self.client.is_connected():
                await self.client.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting client: {e}")

    async def send_otp(self, phone: str):
        await self.connect()
        logger.info(f"Sending OTP request for {phone}")
        return await self.client.send_code_request(phone)

    async def sign_in(self, phone: str, code: str, phone_code_hash: str, password: Optional[str] = None) -> Tuple[Any, str]:
        await self.connect()
        try:
            user = await self.client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            session_str = self.client.session.save()
            return user, session_str
        except errors.SessionPasswordNeededError:
            if password:
                user = await self.client.sign_in(password=password)
                session_str = self.client.session.save()
                return user, session_str
            else:
                raise errors.SessionPasswordNeededError("2FA_REQUIRED")
        except Exception as e:
            logger.error(f"Sign in error: {e}")
            raise e

    async def sign_in_password(self, password: str) -> Tuple[Any, str]:
        await self.connect()
        try:
            user = await self.client.sign_in(password=password)
            session_str = self.client.session.save()
            return user, session_str
        except Exception as e:
            logger.error(f"2FA sign in error: {e}")
            raise e

    async def get_me(self) -> Any:
        await self.connect()
        return await self.client.get_me()

    async def get_dialogs(self) -> List[Dict[str, Any]]:
        """
        Fetch all groups and channels where user is a participant.
        Detects group type, member count, and posting capability.
        """
        await self.connect()
        dialogs = await self.client.get_dialogs()
        result = []

        for d in dialogs:
            if not (d.is_group or d.is_channel):
                continue

            entity = d.entity
            peer_id = str(d.id)
            title = d.name or getattr(entity, 'title', f"Chat {peer_id}")
            username = getattr(entity, 'username', None)
            
            # Determine specific entity type
            is_megagroup = getattr(entity, 'megagroup', False) or getattr(entity, 'gigagroup', False)
            if d.is_channel and not is_megagroup:
                entity_type = "channel"
            elif is_megagroup:
                entity_type = "supergroup"
            else:
                entity_type = "group"

            # Member count
            participants_count = getattr(entity, 'participants_count', 0) or 0

            # Check send permissions
            can_send = True
            try:
                # Channels: check if user is admin or broadcast permitted
                if entity_type == "channel":
                    can_send = getattr(entity, 'creator', False) or (getattr(entity, 'admin_rights', None) and getattr(entity.admin_rights, 'post_messages', False))
                else:
                    # Groups: check default restrictions
                    default_banned = getattr(entity, 'default_banned_rights', None)
                    if default_banned and getattr(default_banned, 'send_messages', False):
                        can_send = False
            except Exception:
                can_send = True

            result.append({
                "peer_id": peer_id,
                "title": title,
                "username": username,
                "entity_type": entity_type,
                "members_count": participants_count,
                "can_send_messages": bool(can_send),
                "is_group": d.is_group,
                "is_channel": d.is_channel
            })

        return result

    async def join_group(self, group_link: str) -> Dict[str, Any]:
        """
        Join group via invite link (t.me/+hash, t.me/joinchat/hash) or public @username
        """
        await self.connect()
        from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
        from telethon.tl.functions.channels import JoinChannelRequest

        clean_link = group_link.strip()
        try:
            if "t.me/+" in clean_link or "t.me/joinchat/" in clean_link:
                hash_part = clean_link.split("+")[-1] if "t.me/+" in clean_link else clean_link.split("/")[-1]
                updates = await self.client(ImportChatInviteRequest(hash_part))
                chat = updates.chats[0] if (hasattr(updates, 'chats') and updates.chats) else None
                return {
                    "success": True,
                    "peer_id": str(chat.id) if chat else "",
                    "title": getattr(chat, 'title', 'Joined Chat') if chat else 'Joined Chat',
                    "entity_type": "supergroup" if getattr(chat, 'megagroup', False) else "group"
                }
            else:
                # Username or public link
                username = clean_link.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").split("/")[0]
                result = await self.client(JoinChannelRequest(username))
                chat = result.chats[0] if (hasattr(result, 'chats') and result.chats) else None
                return {
                    "success": True,
                    "peer_id": str(chat.id) if chat else "",
                    "title": getattr(chat, 'title', username) if chat else username,
                    "entity_type": "channel" if getattr(chat, 'broadcast', False) else "supergroup"
                }
        except Exception as e:
            logger.error(f"Join group error: {e}")
            raise e

    async def send_humanized_message(
        self,
        peer_id: Any,
        template_text: str,
        group_name: str = "Group",
        simulate_typing: bool = True,
        typing_duration: float = 2.0,
        media_path: Optional[str] = None,
        media_url: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Sends message with anti-spam safeguards:
        1. Resolves dynamic spintax and placeholders.
        2. Simulates realistic 'typing...' or 'uploading document' action.
        3. Supports sending media (image/video) with text caption!
        4. Gracefully handles captions > 1024 characters (Telegram's media caption limit).
        5. Automatically falls back to text-only message if a group restricts media.
        6. Handles FloodWait and permission restrictions safely.
        """
        try:
            if not self.client.is_connected():
                await self.connect()
        except Exception as e:
            logger.warning(f"Connection attempt issue: {e}")
        
        # Resolve spintax and dynamic variables
        resolved_message = self.render_template(template_text, group_name=group_name)

        # Convert peer_id to int if numeric string
        target_peer = int(peer_id) if str(peer_id).lstrip('-').isdigit() else peer_id

        # Human simulation: send typing or uploading media action if enabled
        if simulate_typing and typing_duration > 0:
            try:
                actual_duration = max(0.5, min(typing_duration, 4.0))
                action_type = 'document' if (media_path or media_url) else 'typing'
                async with self.client.action(target_peer, action_type):
                    await asyncio.sleep(actual_duration)
            except Exception as e:
                logger.warning(f"Typing action warning for {peer_id}: {e}")

        # Determine media target
        media_target = None
        if media_path and os.path.exists(media_path):
            media_target = media_path
        elif media_url and (media_url.startswith("http://") or media_url.startswith("https://")):
            media_target = media_url
        elif media_url and media_url.startswith("data:"):
            try:
                import base64
                import io
                _, b64 = media_url.split(",", 1) if "," in media_url else ("", media_url)
                file_bytes = io.BytesIO(base64.b64decode(b64))
                file_bytes.name = "media.png" if "image" in media_url[:30] else "media.mp4"
                media_target = file_bytes
            except Exception as e:
                logger.warning(f"Failed to decode base64 data url: {e}")

        # Send message with retry on FloodWait or temporary socket drop
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not self.client.is_connected():
                    await self.connect()

                if media_target:
                    # Reset stream position if BytesIO
                    if hasattr(media_target, "seek"):
                        media_target.seek(0)

                    try:
                        # Telegram caption limit is strictly 1024 characters for regular MTProto accounts.
                        # If message is longer than 1024 characters, sending caption directly will fail with MediaCaptionTooLongError.
                        if len(resolved_message) <= 1024:
                            await self.client.send_file(
                                target_peer,
                                media_target,
                                caption=resolved_message if resolved_message else None
                            )
                        else:
                            # Deliver media first, followed immediately by the full long message!
                            await self.client.send_file(target_peer, media_target)
                            await self.client.send_message(target_peer, resolved_message)
                    except (errors.MediaCaptionTooLongError, ValueError):
                        # Caption length or markdown entity parsing error: send media then full text, or fallback to text
                        try:
                            if hasattr(media_target, "seek"):
                                media_target.seek(0)
                            await self.client.send_file(target_peer, media_target)
                            await self.client.send_message(target_peer, resolved_message)
                        except Exception:
                            await self.client.send_message(target_peer, resolved_message)
                    except (errors.ChatSendMediaForbiddenError,
                            errors.ChatSendPhotosForbiddenError,
                            errors.ChatSendVideosForbiddenError,
                            errors.ChatSendDocsForbiddenError,
                            errors.PhotoInvalidDimensionsError,
                            errors.PhotoCropSizeSmallError,
                            Exception) as media_err:
                        # Any media permission restriction or upload glitch: fall back seamlessly to sending the text message!
                        logger.warning(f"Media sending issue for {peer_id} ({media_err}), falling back to text-only delivery")
                        await self.client.send_message(target_peer, resolved_message)
                else:
                    await self.client.send_message(target_peer, resolved_message)

                return True, resolved_message, None
            except errors.FloodWaitError as fwe:
                logger.warning(f"Telegram FloodWait for {fwe.seconds}s on {peer_id}")
                if attempt < max_retries - 1 and fwe.seconds <= 120:
                    await asyncio.sleep(fwe.seconds + 2)
                    continue
                return False, resolved_message, f"FloodWaitError: rate limited for {fwe.seconds}s"
            except errors.ChatWriteForbiddenError:
                return False, resolved_message, "Permission Denied: User cannot send messages in this group"
            except errors.UserBannedInChannelError:
                return False, resolved_message, "User is banned from posting in this channel/group"
            except errors.ChatAdminRequiredError:
                return False, resolved_message, "Only admins can post messages here"
            except errors.SlowModeWaitError as smwe:
                return False, resolved_message, f"Slow mode active (wait {smwe.seconds}s)"
            except (ConnectionError, asyncio.TimeoutError, errors.RPCError) as ce:
                logger.warning(f"Network hiccup on {peer_id} (attempt {attempt+1}/{max_retries}): {ce}")
                await asyncio.sleep(2)
                try:
                    await self.connect()
                except Exception:
                    pass
                if attempt < max_retries - 1:
                    continue
                return False, resolved_message, f"Connection error: {ce}"
            except Exception as e:
                return False, resolved_message, str(e)

        return False, resolved_message, "Failed to send after retries"

    @classmethod
    def parse_spintax(cls, text: str) -> str:
        """
        Recursively resolves spintax like: {Hello|Hi|Greetings} {world|friends}!
        """
        pattern = re.compile(r'\{([^{}]*)\}')
        while True:
            match = pattern.search(text)
            if not match:
                break
            options = match.group(1).split('|')
            text = text[:match.start()] + random.choice(options) + text[match.end():]
        return text

    @classmethod
    def render_template(cls, text: str, group_name: str = "Group") -> str:
        """
        Replaces variables and evaluates spintax safely:
        - NEVER allows dynamic placeholders ({group_name}, etc.) to corrupt URLs!
        - Strips any accidental tags glued directly onto link slugs (e.g. wa.link/xyz{group_name}).
        - Masks all URLs during spintax & variable replacement to preserve links 100% intact.
        """
        if not text:
            return ""

        # 1. Clean accidental tags glued directly onto URLs (e.g. https://wa.link/xyz{group_name})
        cleaned = text
        while re.search(r'(https?://[^\s{}]+)\{[a-zA-Z0-9_| ]+\}', cleaned):
            cleaned = re.sub(r'(https?://[^\s{}]+)\{[a-zA-Z0-9_| ]+\}', r'\1', cleaned)

        # 2. Extract and mask all URLs with safe placeholders so spintax / variable engines never touch links
        url_matches = re.findall(r'https?://[^\s]+', cleaned)
        url_map = {}
        for idx, url in enumerate(url_matches):
            placeholder = f"__TELEPRO_LINK_{idx}__"
            url_map[placeholder] = url
            cleaned = cleaned.replace(url, placeholder, 1)

        now = datetime.datetime.now()
        hour = now.hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 18:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        # 3. Replace dynamic variables in the message body
        rendered = cleaned.replace("{group_name}", group_name)
        rendered = rendered.replace("{date}", now.strftime("%B %d, %Y"))
        rendered = rendered.replace("{time}", now.strftime("%I:%M %p"))
        rendered = rendered.replace("{greeting}", greeting)
        
        # Replace each {random_emoji} with a different random choice
        while "{random_emoji}" in rendered:
            rendered = rendered.replace("{random_emoji}", random.choice(EMOJIS), 1)

        # 4. Parse spintax variations
        rendered = cls.parse_spintax(rendered)

        # 5. Restore original, untouched URLs
        for placeholder, original_url in url_map.items():
            rendered = rendered.replace(placeholder, original_url)

        return rendered
