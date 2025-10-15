import discord
from discord import ui
import json
import logging
from datetime import datetime, timezone
import time
import asyncio
from utils import safe_json_write, safe_json_read, report_critical_error
from config import (
    MEMBER_ROLE_ID, UNVERIFIED_ROLE_ID, USER_DATA_FILE, COOLDOWN_FILE, 
    LEAD_DATA_FILE, RATE_LIMIT_SECONDS, TYPEFORM_LINK, get_survey_embed
)


class OnboardingButton(ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="🔒 Book Your Onboarding Call",
            custom_id="book_onboarding"
        )
        # Load cooldowns from file
        self.button_cooldowns = self.load_cooldowns()

    def load_cooldowns(self):
        """Load cooldowns from file"""
        try:
            data = safe_json_read(COOLDOWN_FILE, {})
            # Filter out expired cooldowns
            current_time = time.time()
            cooldowns = {}
            for user_id_str, last_click in data.items():
                if current_time - last_click < RATE_LIMIT_SECONDS:
                    cooldowns[user_id_str] = last_click
            return cooldowns
        except Exception as e:
            logging.error(f"Error loading cooldowns: {e}")
            return {}

    def save_cooldowns(self):
        """Save cooldowns to file"""
        safe_json_write(COOLDOWN_FILE, self.button_cooldowns)

    def cleanup_expired_cooldowns(self):
        """Remove expired cooldowns from memory and file"""
        current_time = time.time()
        expired_users = []
        
        for user_id, last_click in self.button_cooldowns.items():
            if current_time - last_click >= RATE_LIMIT_SECONDS:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self.button_cooldowns[user_id]
        
        if expired_users:
            self.save_cooldowns()
            logging.debug(f"Cleaned up {len(expired_users)} expired cooldowns")

    async def callback(self, interaction: discord.Interaction):
        """Handle button click with rate limiting"""
        user_id = str(interaction.user.id)
        current_time = time.time()
        
        # Clean up expired cooldowns periodically
        if len(self.button_cooldowns) > 100:  # Clean up when we have many cooldowns
            self.cleanup_expired_cooldowns()
        
        # Check rate limit
        last_click = self.button_cooldowns.get(user_id, 0)
        if current_time - last_click < RATE_LIMIT_SECONDS:
            remaining_time = int(RATE_LIMIT_SECONDS - (current_time - last_click))
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"⏳ Please wait **{remaining_time} seconds** before trying again.",
                        ephemeral=True
                    )
            except Exception as e:
                logging.error(f"Error sending rate limit response: {e}")
            logging.info(f"Rate limited user {user_id} - {remaining_time}s remaining")
            return
        
        logging.info(f"Button callback triggered for user {interaction.user.id}")
        
        try:
            # Load user data
            user_data = safe_json_read(USER_DATA_FILE, {})
            
            # Check roles
            member_role_id = MEMBER_ROLE_ID
            unverified_role_id = UNVERIFIED_ROLE_ID
            
            has_member_role = False
            has_unverified_role = False
            
            if interaction.guild:
                if member_role_id:
                    member_role = interaction.guild.get_role(member_role_id)
                    if member_role and member_role in interaction.user.roles:
                        has_member_role = True
                
                if unverified_role_id:
                    unverified_role = interaction.guild.get_role(unverified_role_id)
                    if unverified_role and unverified_role in interaction.user.roles:
                        has_unverified_role = True
            
            # Check if user already has member role AND doesn't have unverified role
            if has_member_role and not has_unverified_role:
                embed = discord.Embed(
                    title="✅ Already Verified!",
                    description="You already have access to the community.",
                    color=0x00ff00
                )
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logging.error(f"Error sending already verified response: {e}")
                logging.info(f"User {user_id} already has member role and no unverified role")
                return
            
            # Check if user is in user_data.json (only users who went through premium role assignment)
            if user_id not in user_data:
                # User not in user_data.json - they shouldn't be using this button
                embed = discord.Embed(
                    title="❌ Access Denied",
                    description="This verification is only for premium users. Please contact support if you believe this is an error.",
                    color=0xff0000
                )
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logging.error(f"Error sending access denied response: {e}")
                logging.info(f"User {user_id} not in user_data.json - tried to use verification button")
                return
            
            # Get user data
            existing_data = user_data.get(user_id, {})
            premium_role_id = existing_data.get('premium_role_id')
            premium_role_name = existing_data.get('premium_role_name')
            
            # If user doesn't have unverified role, add it
            unverified_role_actually_assigned = False
            if not has_unverified_role and unverified_role_id and interaction.guild:
                unverified_role = interaction.guild.get_role(unverified_role_id)
                if unverified_role:
                    try:
                        await interaction.user.add_roles(unverified_role)
                        has_unverified_role = True
                        unverified_role_actually_assigned = True
                        logging.info(f"Added unverified role to user {user_id}")
                    except Exception as e:
                        logging.error(f"Error adding unverified role to user {user_id}: {e}")
                        # Continue processing even if role assignment fails
            else:
                # User already has unverified role
                unverified_role_actually_assigned = has_unverified_role
            
            # Update user data to mark as having clicked the button (waiting for Typeform submission)
            user_data = safe_json_read(USER_DATA_FILE, {})
            existing_data = user_data.get(user_id, {})
            user_data[user_id] = {
                'username': interaction.user.display_name,
                'button_clicked_at': current_time,
                'premium_role_id': existing_data.get('premium_role_id'),
                'premium_role_name': existing_data.get('premium_role_name'),
                'survey_status': 'pending',
                'unverified_role_assigned': unverified_role_actually_assigned
            }
            safe_json_write(USER_DATA_FILE, user_data)
            
            # Update cooldown AFTER successful processing
            self.button_cooldowns[user_id] = current_time
            self.save_cooldowns()
            
            # Use centralized survey embed
            embed = get_survey_embed("Premium", user_id)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Start enhanced webhook monitoring for this user
            await self.start_enhanced_webhook_monitoring(interaction.guild, user_id)
            
            logging.info(f"Showed Typeform link to user {user_id}")
            
        except Exception as e:
            logging.error(f"Error in button callback: {e}")
            
            # Report critical error to owners
            try:
                # Get bot instance from interaction
                bot = interaction.client if hasattr(interaction, 'client') else None
                await report_critical_error("Button Callback Error", f"Error in onboarding button callback: {e}", bot, interaction)
            except Exception as report_error:
                logging.error(f"Failed to report critical error: {report_error}")
            
            # Try to send user-friendly error message
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again later.", 
                        ephemeral=True
                    )
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")
    
    async def start_webhook_monitoring(self, guild, user_id):
        """Start monitoring webhook channel for user ID after 10 seconds"""
        try:
            # Wait 10 seconds
            await asyncio.sleep(10)
            
            # Import webhook handler to access verification logic
            from .webhook_handler import WebhookHandler
            
            # Get webhook handler instance
            webhook_handler = None
            # Get bot instance from the guild
            bot = guild._state._get_client()
            if bot:
                for cog in bot.cogs.values():
                    if isinstance(cog, WebhookHandler):
                        webhook_handler = cog
                        break
            
            if webhook_handler:
                # Monitor webhook channel for this user ID
                await self.monitor_webhook_channel(guild, user_id, webhook_handler)
                logging.info(f"Started webhook monitoring for user {user_id}")
            else:
                logging.warning("WebhookHandler not found - cannot start webhook monitoring")
                
        except Exception as e:
            logging.error(f"Error starting webhook monitoring for user {user_id}: {e}")
    
    async def monitor_webhook_channel(self, guild, user_id, webhook_handler):
        """Monitor webhook channel for user ID and verify if found"""
        try:
            from config import SUBMISSION_LOGS_CHANNEL_ID
            
            if not SUBMISSION_LOGS_CHANNEL_ID:
                logging.warning("SUBMISSION_LOGS_CHANNEL_ID not set - cannot monitor webhook channel")
                return
            
            logs_channel = guild.get_channel(SUBMISSION_LOGS_CHANNEL_ID)
            if not logs_channel:
                logging.error(f"Webhook channel {SUBMISSION_LOGS_CHANNEL_ID} not found")
                return
            
            logging.info(f"Monitoring webhook channel for user {user_id}")
            
            # Check recent messages for the user ID
            async for message in logs_channel.history(limit=50):
                if user_id in message.content:
                    logging.info(f"Found user {user_id} in webhook channel - proceeding with verification")
                    # Call verification directly
                    await webhook_handler.auto_verify_user(guild, user_id, message, skip_logs_check=True)
                    return
            
            logging.info(f"User {user_id} not found in recent webhook messages")
                
        except Exception as e:
            logging.error(f"Error monitoring webhook channel for user {user_id}: {e}")
    
    async def start_enhanced_webhook_monitoring(self, guild, user_id):
        """Start enhanced webhook monitoring using the consolidated system"""
        try:
            # Get webhook handler instance
            from .webhook_handler import WebhookHandler
            
            # Get bot instance from the guild
            bot = guild._state._get_client()
            if bot:
                # Find webhook handler
                webhook_handler = None
                for cog in bot.cogs.values():
                    if isinstance(cog, WebhookHandler):
                        webhook_handler = cog
                        break
                
                if webhook_handler:
                    # Start enhanced monitoring using the consolidated system
                    await webhook_handler.start_enhanced_monitoring(guild, user_id)
                    logging.info(f"Started enhanced webhook monitoring for user {user_id}")
                else:
                    logging.warning("WebhookHandler not found - cannot start enhanced monitoring")
            else:
                logging.error("Bot instance not found - cannot start enhanced monitoring")
                
        except Exception as e:
            logging.error(f"Error starting enhanced webhook monitoring for user {user_id}: {e}")
            # Fallback to old monitoring system
            await self.start_webhook_monitoring(guild, user_id)


class WelcomeVerifyButton(ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="Confirm Your Survey",
            custom_id="confirm_survey"
        )
        # Load cooldowns from file
        self.button_cooldowns = self.load_cooldowns()

    def load_cooldowns(self):
        """Load cooldowns from file"""
        try:
            data = safe_json_read(COOLDOWN_FILE, {})
            # Filter out expired cooldowns
            current_time = time.time()
            cooldowns = {}
            for user_id_str, last_click in data.items():
                if current_time - last_click < RATE_LIMIT_SECONDS:
                    cooldowns[user_id_str] = last_click
            return cooldowns
        except Exception as e:
            logging.error(f"Error loading cooldowns: {e}")
            return {}

    def save_cooldowns(self):
        """Save cooldowns to file"""
        safe_json_write(COOLDOWN_FILE, self.button_cooldowns)

    async def callback(self, interaction: discord.Interaction):
        """Handle welcome verify button click with rate limiting"""
        user_id = str(interaction.user.id)
        current_time = time.time()
        
        # Clean up expired cooldowns periodically
        if len(self.button_cooldowns) > 100:  # Clean up when we have many cooldowns
            self.cleanup_expired_cooldowns()
        
        # Check rate limit
        last_click = self.button_cooldowns.get(user_id, 0)
        if current_time - last_click < RATE_LIMIT_SECONDS:
            remaining_time = int(RATE_LIMIT_SECONDS - (current_time - last_click))
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"⏳ Please wait **{remaining_time} seconds** before trying again.",
                        ephemeral=True
                    )
            except Exception as e:
                logging.error(f"Error sending rate limit response: {e}")
            logging.info(f"Rate limited user {user_id} - {remaining_time}s remaining")
            return
        
        logging.info(f"Welcome verify button callback triggered for user {interaction.user.id}")
        
        try:
            # Load user data
            user_data = safe_json_read(USER_DATA_FILE, {})
            user_info = user_data.get(user_id, {})
            
            # Check roles
            member_role_id = MEMBER_ROLE_ID
            unverified_role_id = UNVERIFIED_ROLE_ID
            
            has_member_role = False
            has_unverified_role = False
            
            if interaction.guild:
                if member_role_id:
                    member_role = interaction.guild.get_role(member_role_id)
                    if member_role and member_role in interaction.user.roles:
                        has_member_role = True
                
                if unverified_role_id:
                    unverified_role = interaction.guild.get_role(unverified_role_id)
                    if unverified_role and unverified_role in interaction.user.roles:
                        has_unverified_role = True
            
            # Check if user already has member role AND doesn't have unverified role
            if has_member_role and not has_unverified_role:
                embed = discord.Embed(
                    title="✅ Already Verified!",
                    description="You already have access to the community.",
                    color=0x00ff00
                )
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logging.error(f"Error sending already verified response: {e}")
                logging.info(f"User {user_id} already has member role and no unverified role")
                return
            
            # Check if user is in user_data.json (only users who went through premium role assignment)
            if user_id not in user_data:
                # User not in user_data.json - they shouldn't be using this button
                embed = discord.Embed(
                    title="❌ Access Denied",
                    description="This verification is only for premium users. Please contact support if you believe this is an error.",
                    color=0xff0000
                )
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logging.error(f"Error sending access denied response: {e}")
                logging.info(f"User {user_id} not in user_data.json - tried to use welcome verify button")
                return
            
            # Get premium role info
            premium_role_name = user_info.get('premium_role_name', 'Premium')
            
            # If user doesn't have unverified role, add it
            unverified_role_actually_assigned = False
            if not has_unverified_role and unverified_role_id and interaction.guild:
                unverified_role = interaction.guild.get_role(unverified_role_id)
                if unverified_role:
                    try:
                        await interaction.user.add_roles(unverified_role)
                        has_unverified_role = True
                        unverified_role_actually_assigned = True
                        logging.info(f"Added unverified role to user {user_id} via welcome verify button")
                    except Exception as e:
                        logging.error(f"Error adding unverified role to user {user_id}: {e}")
                        # Continue processing even if role assignment fails
            else:
                # User already has unverified role
                unverified_role_actually_assigned = has_unverified_role
            
            # Use centralized survey embed
            embed = get_survey_embed(premium_role_name, user_id)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Start enhanced webhook monitoring for this user
            await self.start_enhanced_webhook_monitoring(interaction.guild, user_id)
            
            # Update user data to mark as having clicked the button (waiting for Typeform submission)
            user_data = safe_json_read(USER_DATA_FILE, {})
            existing_data = user_data.get(user_id, {})
            user_data[user_id] = {
                'username': interaction.user.display_name,
                'button_clicked_at': current_time,
                'premium_role_id': existing_data.get('premium_role_id'),
                'premium_role_name': existing_data.get('premium_role_name'),
                'survey_status': 'pending',
                'unverified_role_assigned': unverified_role_actually_assigned
            }
            safe_json_write(USER_DATA_FILE, user_data)
            
            # Update cooldown AFTER successful processing
            self.button_cooldowns[user_id] = current_time
            self.save_cooldowns()
            
            logging.info(f"Showed Typeform link to user {user_id} via welcome verify button")
            
        except Exception as e:
            logging.error(f"Error in welcome verify button callback: {e}")
            
            # Report critical error to owners
            try:
                # Get bot instance from interaction
                bot = interaction.client if hasattr(interaction, 'client') else None
                await report_critical_error("Welcome Verify Button Error", f"Error in welcome verify button callback: {e}", bot, interaction)
            except Exception as report_error:
                logging.error(f"Failed to report critical error: {report_error}")
            
            # Try to send user-friendly error message
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again later.", 
                        ephemeral=True
                    )
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")

    def cleanup_expired_cooldowns(self):
        """Remove expired cooldowns from memory and file"""
        current_time = time.time()
        expired_users = []
        
        for user_id, last_click in self.button_cooldowns.items():
            if current_time - last_click >= RATE_LIMIT_SECONDS:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self.button_cooldowns[user_id]
        
        if expired_users:
            self.save_cooldowns()
            logging.debug(f"Cleaned up {len(expired_users)} expired cooldowns")
    
    async def start_webhook_monitoring(self, guild, user_id):
        """Start monitoring webhook channel for user ID after 10 seconds"""
        try:
            # Wait 10 seconds
            await asyncio.sleep(10)
            
            # Import webhook handler to access verification logic
            from .webhook_handler import WebhookHandler
            
            # Get webhook handler instance
            webhook_handler = None
            # Get bot instance from the guild
            bot = guild._state._get_client()
            if bot:
                for cog in bot.cogs.values():
                    if isinstance(cog, WebhookHandler):
                        webhook_handler = cog
                        break
            
            if webhook_handler:
                # Monitor webhook channel for this user ID
                await self.monitor_webhook_channel(guild, user_id, webhook_handler)
                logging.info(f"Started webhook monitoring for user {user_id}")
            else:
                logging.warning("WebhookHandler not found - cannot start webhook monitoring")
                
        except Exception as e:
            logging.error(f"Error starting webhook monitoring for user {user_id}: {e}")
    
    async def monitor_webhook_channel(self, guild, user_id, webhook_handler):
        """Monitor webhook channel for user ID and verify if found"""
        try:
            from config import SUBMISSION_LOGS_CHANNEL_ID
            
            if not SUBMISSION_LOGS_CHANNEL_ID:
                logging.warning("SUBMISSION_LOGS_CHANNEL_ID not set - cannot monitor webhook channel")
                return
            
            logs_channel = guild.get_channel(SUBMISSION_LOGS_CHANNEL_ID)
            if not logs_channel:
                logging.error(f"Webhook channel {SUBMISSION_LOGS_CHANNEL_ID} not found")
                return
            
            logging.info(f"Monitoring webhook channel for user {user_id}")
            
            # Check recent messages for the user ID
            async for message in logs_channel.history(limit=50):
                if user_id in message.content:
                    logging.info(f"Found user {user_id} in webhook channel - proceeding with verification")
                    # Call verification directly
                    await webhook_handler.auto_verify_user(guild, user_id, message, skip_logs_check=True)
                    return
            
            logging.info(f"User {user_id} not found in recent webhook messages")
                
        except Exception as e:
            logging.error(f"Error monitoring webhook channel for user {user_id}: {e}")
    
    async def start_enhanced_webhook_monitoring(self, guild, user_id):
        """Start enhanced webhook monitoring using the consolidated system"""
        try:
            # Get webhook handler instance
            from .webhook_handler import WebhookHandler
            
            # Get bot instance from the guild
            bot = guild._state._get_client()
            if bot:
                # Find webhook handler
                webhook_handler = None
                for cog in bot.cogs.values():
                    if isinstance(cog, WebhookHandler):
                        webhook_handler = cog
                        break
                
                if webhook_handler:
                    # Start enhanced monitoring using the consolidated system
                    await webhook_handler.start_enhanced_monitoring(guild, user_id)
                    logging.info(f"Started enhanced webhook monitoring for user {user_id}")
                else:
                    logging.warning("WebhookHandler not found - cannot start enhanced monitoring")
            else:
                logging.error("Bot instance not found - cannot start enhanced monitoring")
                
        except Exception as e:
            logging.error(f"Error starting enhanced webhook monitoring for user {user_id}: {e}")
            # Fallback to old monitoring system
            await self.start_webhook_monitoring(guild, user_id)

class VerificationView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(OnboardingButton())

class WelcomeVerifyView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(WelcomeVerifyButton())

async def setup(bot):
    # This cog doesn't need any setup, just the VerificationView class
    pass 