import discord
from discord.ext import commands
import logging
import re
import asyncio
import time
from datetime import datetime, timezone
from utils import safe_json_write, safe_json_read
from config import (
    UNVERIFIED_ROLE_ID, VIP_ROLE_ID, HUNDRED_K_ROLE_ID, SUBMISSION_LOGS_CHANNEL_ID,
    CALENDLY_LINK, get_verification_complete_embed
)


class WebhookHandler(commands.Cog):
    """Handle Typeform webhook messages and automatic user verification"""
    
    def __init__(self, bot):
        self.bot = bot
        # Enhanced monitoring system
        self.active_monitors = {}  # Track active monitoring tasks
        self.monitoring_config = {
            'max_attempts': 120,      # Monitor for up to ~2 hours (with backoff)
            'initial_interval': 20,   # Check every 20 seconds initially
            'max_interval': 180,      # Cap interval at 3 minutes
            'max_history': 200,       # Check last 200 messages each pass
            'backoff_multiplier': 1.3, # Slightly faster backoff
            'backoff_threshold': 10   # Start backoff after 10 attempts
        }
        
    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle incoming messages, including Typeform webhook notifications"""
        # Skip bot messages and non-guild messages
        if message.author.bot or not message.guild:
            return
            
        # Check for Typeform webhook messages
        await self.handle_typeform_webhook(message)

    async def handle_typeform_webhook(self, message):
        """Handle Typeform webhook messages and automatically verify users"""
        try:
            # Debug logging
            logging.info(f"Processing message from {message.author.name} in channel {message.channel.name} ({message.channel.id})")
            logging.info(f"Message content: {message.content}")
            
            # Check if this is a Typeform webhook message
            if not self.is_typeform_webhook_message(message):
                logging.debug("Message is not a Typeform webhook message")
                return
                
            logging.info("Typeform webhook message detected!")
                
            # Extract auth_code from the message
            auth_code = self.extract_auth_code_from_message(message)
            if not auth_code:
                # Try to extract from the raw webhook data if available
                auth_code = self.extract_auth_code_from_webhook_data(message)
                
            if not auth_code:
                logging.warning("Typeform webhook message detected but no auth_code found")
                logging.debug(f"Message content: {message.content}")
                if message.embeds:
                    logging.debug(f"Embed fields: {[f'{f.name}: {f.value}' for f in message.embeds[0].fields]}")
                return
            
            logging.info(f"Extracted auth_code: {auth_code} from Typeform webhook")
                
            # Verify the user automatically
            await self.auto_verify_user(message.guild, auth_code, message)
            
        except Exception as e:
            logging.error(f"Error handling Typeform webhook: {e}")

    def is_typeform_webhook_message(self, message):
        """Check if message is from a Typeform webhook"""
        # Check message content for Typeform webhook indicators
        content = message.content or ""
        content_lower = content.lower()
        
        # Check for Typeform webhook indicators in content
        typeform_indicators = [
            "new typeform submission",
            "typeform submission details", 
            "form:",
            "submitted:",
            "auth code:",
            "answers:"
        ]
        
        has_content_indicators = any(indicator in content_lower for indicator in typeform_indicators)
        
        # Also check embeds if they exist
        has_embed_indicators = False
        if message.embeds:
            embed = message.embeds[0]
            title = embed.title or ""
            description = embed.description or ""
            embed_content = f"{title} {description}".lower()
            has_embed_indicators = any(indicator in embed_content for indicator in typeform_indicators)
        
        # Check if it's from a webhook or app
        is_from_app = message.author.name.lower() in ["verify logs submission", "typeform", "webhook"]
        
        return has_content_indicators or has_embed_indicators or is_from_app

    def extract_auth_code_from_message(self, message):
        """Extract auth_code from Typeform webhook message"""
        try:
            # Look for auth_code in embed fields first (most common case)
            if message.embeds:
                embed = message.embeds[0]
                
                # Check embed fields for auth_code
                for field in embed.fields:
                    if field.name and field.value:
                        field_text = f"{field.name} {field.value}".lower()
                        
                        # Look for "Auth Code" field specifically (plain text, no backticks)
                        if "auth code" in field_text:
                            # Extract the value - it's plain text, no formatting
                            auth_code_value = field.value.strip()
                            
                            # Check if it's a Discord user ID (17-19 digits)
                            user_id_match = re.search(r'(\d{17,19})', auth_code_value)
                            if user_id_match:
                                logging.info(f"Found auth_code in embed field: {user_id_match.group(1)}")
                                return user_id_match.group(1)
                        
                        # Also check for URLs with auth_code parameter
                        url_match = re.search(r'auth_code[=:](\d{17,19})', field.value)
                        if url_match:
                            return url_match.group(1)
                
                # Check description for auth_code patterns
                if embed.description:
                    # Look for "Auth Code: xxxxx" pattern in description
                    auth_code_match = re.search(r'Auth Code:\s*`?(\d{17,19})`?', embed.description)
                    if auth_code_match:
                        return auth_code_match.group(1)
                    
                    # Look for auth_code in description
                    auth_code_match = re.search(r'auth_code[=:](\d{17,19})', embed.description)
                    if auth_code_match:
                        return auth_code_match.group(1)
                    
                    # Look for any Discord user ID in description
                    user_id_match = re.search(r'\b(\d{17,19})\b', embed.description)
                    if user_id_match:
                        return user_id_match.group(1)
                
                # Check embed title
                if embed.title:
                    title_match = re.search(r'\b(\d{17,19})\b', embed.title)
                    if title_match:
                        return title_match.group(1)
                        
            # Check message content for auth_code patterns
            if message.content:
                # Look for "Auth Code: xxxxx" pattern in content (with backticks)
                auth_code_match = re.search(r'\*\*Auth Code:\*\*\s*`(\d{17,19})`', message.content)
                if auth_code_match:
                    logging.info(f"Found auth_code in message content (with backticks): {auth_code_match.group(1)}")
                    return auth_code_match.group(1)
                
                # Look for "Auth Code: xxxxx" pattern in content (plain text, no backticks)
                auth_code_match = re.search(r'\*\*Auth Code:\*\*\s*(\d{17,19})', message.content)
                if auth_code_match:
                    logging.info(f"Found auth_code in message content: {auth_code_match.group(1)}")
                    return auth_code_match.group(1)
                
                # Also try without the bold formatting
                auth_code_match = re.search(r'Auth Code:\s*(\d{17,19})', message.content)
                if auth_code_match:
                    logging.info(f"Found auth_code in message content (no bold): {auth_code_match.group(1)}")
                    return auth_code_match.group(1)
                
                # Look for auth_code in content
                auth_code_match = re.search(r'auth_code[=:](\d{17,19})', message.content)
                if auth_code_match:
                    return auth_code_match.group(1)
                
                # Look for any Discord user ID in content
                user_id_match = re.search(r'\b(\d{17,19})\b', message.content)
                if user_id_match:
                    return user_id_match.group(1)
                    
            # Check for URLs in the entire message (including embeds)
            full_text = message.content or ""
            if message.embeds:
                for embed in message.embeds:
                    full_text += f" {embed.title or ''} {embed.description or ''}"
                    for field in embed.fields:
                        full_text += f" {field.name or ''} {field.value or ''}"
            
            # Look for Typeform URLs with auth_code
            typeform_url_match = re.search(r'https?://[^\s]*typeform[^\s]*auth_code[=:](\d{17,19})', full_text)
            if typeform_url_match:
                return typeform_url_match.group(1)
                    
            return None
            
        except Exception as e:
            logging.error(f"Error extracting auth_code: {e}")
            return None

    def extract_auth_code_from_webhook_data(self, message):
        """Extract auth_code from raw webhook data if available"""
        try:
            # Check if message has raw data (this would be available if the webhook
            # sends the actual Typeform webhook payload as an attachment or in content)
            
            # Look for JSON data in the message content or attachments
            content = message.content or ""
            
            # Try to find JSON data in the message
            import json
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    webhook_data = json.loads(json_match.group())
                    
                    # Check for authCode field (camelCase as shown in your webhook data)
                    if 'authCode' in webhook_data:
                        auth_code = webhook_data['authCode']
                        if auth_code and auth_code != 'Not provided':
                            # Check if it's a Discord user ID
                            user_id_match = re.search(r'(\d{17,19})', str(auth_code))
                            if user_id_match:
                                logging.info(f"Found auth_code in webhook data: {user_id_match.group(1)}")
                                return user_id_match.group(1)
                    
                    # Also check for auth_code field (snake_case)
                    if 'auth_code' in webhook_data:
                        auth_code = webhook_data['auth_code']
                        if auth_code and auth_code != 'Not provided':
                            user_id_match = re.search(r'(\d{17,19})', str(auth_code))
                            if user_id_match:
                                logging.info(f"Found auth_code in webhook data: {user_id_match.group(1)}")
                                return user_id_match.group(1)
                                
                except json.JSONDecodeError:
                    pass
            
            # Check attachments for JSON files
            for attachment in message.attachments:
                if attachment.filename.endswith('.json'):
                    try:
                        # Download and parse the JSON file
                        import aiohttp
                        import asyncio
                        
                        async def fetch_json():
                            async with aiohttp.ClientSession() as session:
                                async with session.get(attachment.url) as response:
                                    if response.status == 200:
                                        return await response.json()
                                    return None
                        
                        # Run the async function
                        webhook_data = asyncio.create_task(fetch_json())
                        if webhook_data:
                            if 'authCode' in webhook_data:
                                auth_code = webhook_data['authCode']
                                if auth_code and auth_code != 'Not provided':
                                    user_id_match = re.search(r'(\d{17,19})', str(auth_code))
                                    if user_id_match:
                                        logging.info(f"Found auth_code in JSON attachment: {user_id_match.group(1)}")
                                        return user_id_match.group(1)
                    except Exception as e:
                        logging.error(f"Error processing JSON attachment: {e}")
            
            return None
            
        except Exception as e:
            logging.error(f"Error extracting auth_code from webhook data: {e}")
            return None

    async def auto_verify_user(self, guild, user_id, webhook_message, skip_logs_check=False):
        """Automatically verify premium user based on auth_code from Typeform webhook"""
        try:
            # Step 1: Extract auth_code (already done in calling function)
            logging.info(f"Processing Typeform submission for user {user_id}")
            
            # Step 2: Verify auth_code exists in SUBMISSION_LOGS_CHANNEL_ID (unless skipped)
            if not skip_logs_check:
                logging.info(f"Checking auth_code {user_id} in submission logs channel {SUBMISSION_LOGS_CHANNEL_ID}")
                if not await self.verify_auth_code_in_logs(guild, user_id):
                    logging.warning(f"Auth code {user_id} not found in submission logs channel")
                    return
                logging.info(f"Auth code {user_id} found in submission logs - proceeding with verification")
            else:
                logging.info(f"Skipping logs check for user {user_id}")
            
            # Check if user exists in the guild
            user = guild.get_member(int(user_id))
            if not user:
                logging.warning(f"User {user_id} not found in guild {guild.id}")
                return
                
            # Load user data
            user_data = safe_json_read('user_data.json', {})
            
            if user_id not in user_data:
                logging.warning(f"User {user_id} not found in user data - not a premium user")
                return
                
            user_info = user_data[user_id]
            
            # Check if already verified
            if user_info.get('survey_status') == 'verified':
                logging.info(f"User {user_id} already verified, skipping")
                return
            
            # Check if this is a premium user
            premium_role_id = user_info.get('premium_role_id')
            premium_role_name = user_info.get('premium_role_name')
            if not premium_role_id or not premium_role_name:
                logging.warning(f"User {user_id} has no premium role stored - not a premium user")
                return
                
            # Mark as verified
            user_info['survey_status'] = 'verified'
            user_data[user_id] = user_info
            safe_json_write('user_data.json', user_data)
            
            # Remove unverified role
            if UNVERIFIED_ROLE_ID:
                unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
                if unverified_role and unverified_role in user.roles:
                    await user.remove_roles(unverified_role)
                    logging.info(f"Removed unverified role from user {user_id}")
            
            # Action 1: Restore premium role using stored role ID
            premium_role = guild.get_role(premium_role_id)
            
            if premium_role:
                await user.add_roles(premium_role)
                logging.info(f"Restored premium role '{premium_role_name}' (ID: {premium_role_id}) to user {user_id}")
                
                # Action 2: Send DM with verification complete message and call link
                embed = get_verification_complete_embed(premium_role_name)
            else:
                logging.error(f"Premium role with ID {premium_role_id} ('{premium_role_name}') not found in guild")
                embed = discord.Embed(
                    title="⚠️ Verification Complete",
                    description=(
                        f"Your survey has been submitted, but we couldn't find your **{premium_role_name}** role.\n\n"
                        "Please contact support to restore your premium access.\n\n"
                        "Thank you for completing the verification!"
                    ),
                    color=0xffa500
                )
            
            # Send confirmation DM to user
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                logging.warning(f"Could not send DM to user {user_id}")
                
            # Log the auto-verification
            logging.info(f"Auto-verified premium user {user_id} ({user.display_name}) via Typeform webhook")
            
            # Add reaction to the webhook message to indicate processing
            try:
                await webhook_message.add_reaction("✅")
            except:
                pass
                
        except Exception as e:
            logging.error(f"Error in auto_verify_user: {e}")

    async def verify_auth_code_in_logs(self, guild, auth_code):
        """Verify that auth_code exists in SUBMISSION_LOGS_CHANNEL_ID"""
        try:
            # Get the submission logs channel
            if not SUBMISSION_LOGS_CHANNEL_ID:
                logging.warning("SUBMISSION_LOGS_CHANNEL_ID not set in environment variables")
                return True  # Skip verification if not configured
            
            logs_channel = guild.get_channel(SUBMISSION_LOGS_CHANNEL_ID)
            if not logs_channel:
                logging.error(f"Submission logs channel {SUBMISSION_LOGS_CHANNEL_ID} not found")
                return False
            
            # Search for the auth_code in recent messages (last 200 messages)
            async for message in logs_channel.history(limit=200):
                # Check message content for auth_code
                if auth_code in message.content:
                    logging.info(f"Found auth_code {auth_code} in submission logs")
                    return True
                
                # Check embed fields for auth_code
                if message.embeds:
                    for embed in message.embeds:
                        # Check embed description
                        if embed.description and auth_code in embed.description:
                            logging.info(f"Found auth_code {auth_code} in embed description")
                            return True
                        
                        # Check embed fields
                        for field in embed.fields:
                            if field.value and auth_code in field.value:
                                logging.info(f"Found auth_code {auth_code} in embed field")
                                return True
            
            logging.warning(f"Auth_code {auth_code} not found in submission logs channel")
            return False
            
        except Exception as e:
            logging.error(f"Error verifying auth_code in logs: {e}")
            return False

    async def start_enhanced_monitoring(self, guild, user_id):
        """Start enhanced continuous monitoring for a user"""
        try:
            # Check if already monitoring this user
            if user_id in self.active_monitors:
                logging.info(f"User {user_id} already being monitored, skipping")
                return
            
            # Wait initial delay
            await asyncio.sleep(10)
            
            # Check early exit conditions
            if await self._should_stop_monitoring(user_id):
                return
            
            # Create monitoring task
            monitoring_task = asyncio.create_task(
                self._continuous_monitor(guild, user_id)
            )
            
            # Track the task
            self.active_monitors[user_id] = {
                'task': monitoring_task,
                'started_at': time.time(),
                'guild_id': guild.id
            }
            
            logging.info(f"Started enhanced webhook monitoring for user {user_id}")
            
        except Exception as e:
            logging.error(f"Error starting enhanced monitoring for user {user_id}: {e}")

    async def _continuous_monitor(self, guild, user_id):
        """Main monitoring loop with retry logic and exponential backoff"""
        try:
            # Get monitoring configuration
            config = self.monitoring_config
            check_interval = config['initial_interval']
            last_checked_message_id = await self._get_latest_message_id(guild)
            
            logging.info(f"Starting continuous monitoring for user {user_id} (max {config['max_attempts']} attempts)")
            
            for attempt in range(1, config['max_attempts'] + 1):
                try:
                    # Check exit conditions
                    if await self._should_stop_monitoring(user_id):
                        logging.info(f"User {user_id} verification completed, stopping monitoring")
                        return
                    
                    # Perform monitoring check
                    found_webhook = await self._check_for_webhook_in_monitoring(
                        guild, user_id, last_checked_message_id, config['max_history']
                    )
                    
                    if found_webhook:
                        logging.info(f"Successfully verified user {user_id} via enhanced monitoring (attempt {attempt})")
                        return
                    
                    # Update last checked message ID for next iteration (move watermark forward)
                    latest_id = await self._get_latest_message_id(guild)
                    if latest_id:
                        last_checked_message_id = latest_id
                    
                    # Calculate next check interval (exponential backoff)
                    if attempt > config['backoff_threshold']:
                        check_interval = min(
                            check_interval * config['backoff_multiplier'],
                            config['max_interval']
                        )
                    
                    logging.debug(f"Monitoring attempt {attempt}/{config['max_attempts']} for user {user_id} - next check in {check_interval}s")
                    
                    # Wait before next check
                    await asyncio.sleep(check_interval)
                    
                except Exception as check_error:
                    logging.error(f"Error in monitoring attempt {attempt} for user {user_id}: {check_error}")
                    # Wait longer on error
                    await asyncio.sleep(min(check_interval * 2, config['max_interval']))
            
            # Monitoring timed out
            await self._handle_monitoring_timeout(guild, user_id, config['max_attempts'])
            
        except Exception as e:
            logging.error(f"Critical error in continuous monitoring for user {user_id}: {e}")
        finally:
            # Clean up monitoring task
            if user_id in self.active_monitors:
                del self.active_monitors[user_id]

    async def _should_stop_monitoring(self, user_id):
        """Check if monitoring should stop (user verified or left server)"""
        try:
            # Check if user is verified
            user_data = safe_json_read('user_data.json', {})
            if user_id in user_data and user_data[user_id].get('survey_status') == 'verified':
                return True
            
            # Check if user is still in any monitored guild
            for monitor_info in self.active_monitors.values():
                guild = self.bot.get_guild(monitor_info['guild_id'])
                if guild:
                    member = guild.get_member(int(user_id))
                    if not member:
                        logging.info(f"User {user_id} left guild {guild.id}, stopping monitoring")
                        return True
            
            return False
            
        except Exception as e:
            logging.error(f"Error checking stop conditions for user {user_id}: {e}")
            return False

    async def _check_for_webhook_in_monitoring(self, guild, user_id, last_message_id, max_history):
        """Check for webhook messages containing the user ID during monitoring"""
        try:
            if not SUBMISSION_LOGS_CHANNEL_ID:
                logging.warning("SUBMISSION_LOGS_CHANNEL_ID not set")
                return False
            
            logs_channel = guild.get_channel(SUBMISSION_LOGS_CHANNEL_ID)
            if not logs_channel:
                logging.error(f"Webhook channel {SUBMISSION_LOGS_CHANNEL_ID} not found")
                return False
            
            messages_checked = 0

            if last_message_id:
                # Only fetch messages AFTER the last checked message to catch new ones
                try:
                    after_obj = discord.Object(id=last_message_id)
                    history_iter = logs_channel.history(limit=max_history, after=after_obj)
                except Exception:
                    history_iter = logs_channel.history(limit=max_history)
            else:
                history_iter = logs_channel.history(limit=max_history)

            async for message in history_iter:
                
                messages_checked += 1
                
                # Check if this message contains the user ID
                if user_id in message.content:
                    logging.info(f"Found user {user_id} in webhook message during monitoring")
                    try:
                        # Call verification directly
                        await self.auto_verify_user(guild, user_id, message, skip_logs_check=True)
                        return True
                    except Exception as verify_error:
                        logging.error(f"Error verifying user {user_id}: {verify_error}")
                        # Continue monitoring even if verification fails
            
            logging.debug(f"Checked {messages_checked} messages for user {user_id}, no webhook found")
            return False
            
        except Exception as e:
            logging.error(f"Error checking for webhook for user {user_id}: {e}")
            return False

    async def _get_latest_message_id(self, guild):
        """Get the ID of the latest message in the webhook channel"""
        try:
            if not SUBMISSION_LOGS_CHANNEL_ID:
                return None
            
            logs_channel = guild.get_channel(SUBMISSION_LOGS_CHANNEL_ID)
            if not logs_channel:
                return None
            
            async for message in logs_channel.history(limit=1):
                return message.id
            
            return None
            
        except Exception as e:
            logging.error(f"Error getting latest message ID: {e}")
            return None

    async def _handle_monitoring_timeout(self, guild, user_id, max_attempts):
        """Handle monitoring timeout by notifying user"""
        try:
            logging.warning(f"Webhook monitoring timed out for user {user_id} after {max_attempts} attempts")
            
            # Send timeout notification to user
            user = guild.get_member(int(user_id))
            if user:
                embed = discord.Embed(
                    title="⏰ Verification Timeout",
                    description=(
                        "We didn't receive your survey submission automatically.\n\n"
                        "**What to do next:**\n"
                        "• If you completed the survey, please contact support\n"
                        "• If you haven't completed it yet, please do so using the link provided\n"
                        "• You can try the verification process again\n\n"
                        "We're here to help! Please reach out if you need assistance."
                    ),
                    color=0xffa500
                )
                embed.set_footer(text="This is an automated message - no action required if you haven't submitted yet")
                
                try:
                    await user.send(embed=embed)
                    logging.info(f"Sent timeout notification to user {user_id}")
                except discord.Forbidden:
                    logging.warning(f"Could not send timeout notification to user {user_id} - DMs disabled")
                except Exception as send_error:
                    logging.error(f"Error sending timeout notification to user {user_id}: {send_error}")
            
        except Exception as e:
            logging.error(f"Error handling monitoring timeout for user {user_id}: {e}")

    @commands.command(name="test_webhook")
    @commands.has_permissions(administrator=True)
    async def test_webhook(self, ctx, user_id: str = None):
        """Test webhook detection and verification flow"""
        if not user_id:
            user_id = str(ctx.author.id)
        
        # Create a test message that matches the actual Typeform webhook format
        test_content = f"""🎯 **New Typeform Submission**

**Form:** 1 - 1 Mentorship
**Submitted:** {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}
**Auth Code:** `{user_id}`

**Answers:**
**Question 1:** Test answer"""
        
        # Create a test embed
        test_embed = discord.Embed(
            title="Typeform Submission Details",
            description=f"Form ID: VkuOahlj\nTotal Answers: 1\nSubmitted At: {datetime.now().strftime('%m/%d/%Y, %I:%M:%S %p')}",
            color=0x00ff00
        )
        
        test_embed.add_field(name="Auth Code", value=user_id, inline=True)
        
        await ctx.send(
            f"🧪 **Test Webhook Message**\nThis simulates a Typeform webhook to test verification:\n\n{test_content}",
            embed=test_embed
        )
        
        # Test the extraction
        auth_code = self.extract_auth_code_from_message(ctx.message)
        if auth_code:
            await ctx.send(f"✅ Auth code extracted: `{auth_code}`")
        else:
            await ctx.send("❌ No auth code found in test message")

async def setup(bot):
    await bot.add_cog(WebhookHandler(bot))
