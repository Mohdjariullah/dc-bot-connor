import asyncio
import io
import time
import discord
from discord.ext import commands
from discord import app_commands
import logging
import json
import os
from datetime import datetime, timezone
from .verification import VerificationView
from config import (
    GUILD_ID, WELCOME_CHANNEL_ID, LOGS_CHANNEL_ID, UNVERIFIED_ROLE_ID,
    PREMIUM_ROLE_ID, VIP_ROLE_ID, HUNDRED_K_ROLE_ID, MEMBER_ROLE_ID,
    USER_DATA_FILE, WELCOME_MESSAGE_FILE, get_welcome_embed, ROLE_ASSIGNMENT_DELAY,
    LOGGED_MEMBERS_FILE
)
from utils import safe_json_read, safe_json_write
from main import get_or_create_welcome_message

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.role_assignment_task = None
        self.cooldown_cleanup_task = None
        self.logged_members = set()  # Track members that have been logged
        self.member_join_timestamps = {}  # Track when each member was last processed
        self.load_logged_members()

    @commands.Cog.listener()
    async def on_ready(self):
        """Setup welcome channel when bot is ready (persistent message)"""
        try:
            guild = self.bot.get_guild(GUILD_ID) if GUILD_ID and hasattr(self.bot, 'get_guild') else None
            if not guild:
                logging.error(f"Guild with ID {GUILD_ID} not found")
                return
            if not WELCOME_CHANNEL_ID:
                logging.error("WELCOME_CHANNEL_ID is not set in environment variables")
                return
            welcome_channel = self.bot.get_channel(WELCOME_CHANNEL_ID)
            if not welcome_channel:
                logging.error(f"Welcome channel with ID {WELCOME_CHANNEL_ID} not found")
                return
            
            # Use centralized welcome embed
            embed = get_welcome_embed()
            
            # Use persistent message logic
            msg = await get_or_create_welcome_message(welcome_channel, embed, VerificationView())
            logging.info(f"Welcome message is now persistent: {msg.jump_url}")
            
            # Start role assignment loop
            self.role_assignment_task = self.bot.loop.create_task(self.role_assignment_loop())
            
            # Start cooldown cleanup loop
            self.cooldown_cleanup_task = self.bot.loop.create_task(self.cleanup_cooldowns_loop())
            
            # Start logged members cleanup loop
            self.logged_members_cleanup_task = self.bot.loop.create_task(self.cleanup_logged_members_loop())
            
            # Sync user data with actual Discord roles to prevent incorrect assignments
            await self.sync_user_data_with_roles()
        except Exception as e:
            logging.error(f"Error in on_ready welcome setup: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle new member joins - only process premium users"""
        try:
            guild_id = GUILD_ID
            unverified_role_id = UNVERIFIED_ROLE_ID
            
            if not guild_id or not unverified_role_id:
                logging.error("GUILD_ID or UNVERIFIED_ROLE_ID not set")
                return
            
            guild = member.guild
            if guild.id != guild_id:
                return
            
            # Enhanced duplicate prevention with timestamp tracking
            current_time = time.time()
            user_id = str(member.id)
            
            # Check if this member was processed recently (within 30 seconds)
            last_processed = self.member_join_timestamps.get(user_id, 0)
            if current_time - last_processed < 30:
                logging.info(f"Duplicate member join event for {member.display_name} ({member.id}) - skipping log (processed {current_time - last_processed:.1f}s ago)")
                return
            
            # Update timestamp immediately to prevent duplicates
            self.member_join_timestamps[user_id] = current_time
            
            # Check if this member has already been logged (additional safety)
            if user_id in self.logged_members:
                logging.info(f"Member {member.display_name} ({member.id}) already in logged_members - skipping log")
                return
            
            # Check if user is already verified (prevent reprocessing)
            user_logger_cog = self.bot.get_cog('UserLogger')
            if user_logger_cog and member.id in user_logger_cog.verified_users:
                logging.info(f"Member {member.display_name} ({member.id}) is already verified - skipping processing")
                return
            
            # Check for premium roles using role IDs - only process premium users
            premium_role_detected = None
            premium_role_ids = {}
            
            # Build premium role mapping dynamically - all 3 premium roles
            if PREMIUM_ROLE_ID:
                premium_role_ids[PREMIUM_ROLE_ID] = None  # Will be filled with actual role name
            if VIP_ROLE_ID:
                premium_role_ids[VIP_ROLE_ID] = None  # Will be filled with actual role name
            if HUNDRED_K_ROLE_ID:
                premium_role_ids[HUNDRED_K_ROLE_ID] = None  # Will be filled with actual role name
            
            for role in member.roles:
                if role.id in premium_role_ids:
                    premium_role_detected = role
                    premium_role_name = role.name  # Get actual role name from Discord
                    logging.info(f"Detected premium role '{premium_role_name}' (ID: {role.id}) for {member.display_name} ({member.id})")
                    break
            
            # If no premium role detected, do nothing (Carl-bot handles normal users)
            if not premium_role_detected:
                logging.info(f"No premium role detected for {member.display_name} ({member.id}) - Carl-bot will handle")
                return
            
            # Mark as logged immediately to prevent duplicates
            self.logged_members.add(user_id)
            self.save_logged_members()
            
            logging.info(f"Processing premium user join for {member.display_name} ({member.id}) with {premium_role_detected.name}")
            
            # Get the unverified role
            unverified_role = guild.get_role(unverified_role_id)
            if not unverified_role:
                logging.error(f"Unverified role {unverified_role_id} not found")
                return
            
            # Remove the premium role
            await member.remove_roles(premium_role_detected)
            logging.info(f"Removed premium role '{premium_role_detected.name}' from {member.display_name} ({member.id})")
            
            # Store premium role info in user data (simplified schema)
            try:
                from utils import safe_json_read, safe_json_write
                user_data = safe_json_read(USER_DATA_FILE, {})
                user_data[user_id] = {
                    'premium_role_id': premium_role_detected.id,
                    'premium_role_name': premium_role_name,
                    'survey_status': 'pending'
                }
                safe_json_write(USER_DATA_FILE, user_data)
            except ImportError:
                # Fallback to direct file operations
                try:
                    user_data = safe_json_read(USER_DATA_FILE, {})
                except FileNotFoundError:
                    user_data = {}
                
                user_data[user_id] = {
                    'premium_role_id': premium_role_detected.id,
                    'premium_role_name': premium_role_name,
                    'survey_status': 'pending'
                }
                
                safe_json_write(USER_DATA_FILE, user_data)
            
            # Assign unverified role
            if unverified_role not in member.roles:
                await member.add_roles(unverified_role)
                logging.info(f"Assigned unverified role to {member.display_name} ({member.id})")
            
            # Send premium welcome DM and ping in #verify
            await self.send_premium_welcome_dm(member, premium_role_name)
            await self.ping_in_verify_channel(member, premium_role_name)
            
            # Log to logs channel (only for premium users)
            logs_channel_id = LOGS_CHANNEL_ID
            if logs_channel_id:
                logs_channel = guild.get_channel(logs_channel_id)
                if logs_channel:
                    embed = discord.Embed(
                        title="👋 Premium Member Joined",
                        description=f"**{member.mention}** has joined with {premium_role_name} tier",
                        color=0x00ff00,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
                    embed.add_field(name="Premium Tier", value=f"**{premium_role_name}**", inline=True)
                    embed.add_field(name="Status", value="⏳ Awaiting verification", inline=True)
                    embed.set_thumbnail(url=member.display_avatar.url)
                    
                    try:
                        await logs_channel.send(embed=embed)
                        logging.info(f"Successfully logged premium member join for {member.display_name} ({member.id})")
                    except discord.Forbidden:
                        logging.warning(f"Bot doesn't have permission to send messages to logs channel {logs_channel_id}")
                    except Exception as e:
                        logging.error(f"Error sending log message: {e}")
            
            # Log to user logger cog (only for premium users who join)
            try:
                user_logger_cog = self.bot.get_cog('UserLogger')
                if user_logger_cog:
                    await user_logger_cog.log_user_login(member)
            except Exception as e:
                logging.error(f"Error logging to user logger: {e}")
                
        except Exception as e:
            logging.error(f"Error handling member join for {member.id}: {e}")
            # Remove from logged_members if there was an error
            self.logged_members.discard(str(member.id))
            self.save_logged_members()

    def load_logged_members(self):
        """Load logged members from file"""
        try:
            data = safe_json_read(LOGGED_MEMBERS_FILE, {})
            self.logged_members = set(data.get('logged_members', []))
            logging.info(f"Loaded {len(self.logged_members)} logged members")
            
            # Clean up old entries (keep only recent ones, older than 1 hour)
            current_time = time.time()
            cleaned_members = set()
            for member_id in self.logged_members:
                # For now, just keep all entries but we could add timestamp tracking later
                cleaned_members.add(member_id)
            
            if len(cleaned_members) != len(self.logged_members):
                self.logged_members = cleaned_members
                self.save_logged_members()
                logging.info(f"Cleaned up logged members: {len(self.logged_members)} remaining")
                    
        except FileNotFoundError:
            self.logged_members = set()
            logging.info("No logged members file found, starting fresh")
        except Exception as e:
            logging.error(f"Error loading logged members: {e}")
            self.logged_members = set()

    def save_logged_members(self):
        """Save logged members to file"""
        try:
            safe_json_write(LOGGED_MEMBERS_FILE, {'logged_members': list(self.logged_members)})
        except Exception as e:
            logging.error(f"Error saving logged members: {e}")

    async def role_assignment_loop(self):
        """Background task to assign member roles and remove unverified roles"""
        while True:
            try:
                await self.check_and_assign_roles()
                await asyncio.sleep(5)  # Check every 5 seconds for faster processing
            except Exception as e:
                logging.error(f"Error in role assignment loop: {e}")
                await asyncio.sleep(10)  # Wait longer on error

    async def cleanup_cooldowns_loop(self):
        """Background task to clean up expired button cooldowns"""
        while True:
            try:
                await self.cleanup_expired_cooldowns()
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logging.error(f"Error in cooldown cleanup loop: {e}")
                await asyncio.sleep(600)  # Wait longer on error

    async def cleanup_expired_cooldowns(self):
        """Clean up expired button cooldowns from file"""
        try:
            from .verification import COOLDOWN_FILE, RATE_LIMIT_SECONDS
            import time
            
            try:
                with open(COOLDOWN_FILE, 'r') as f:
                    cooldowns = json.load(f)
            except FileNotFoundError:
                return
            except Exception as e:
                logging.error(f"Error reading cooldown file: {e}")
                return
            
            current_time = time.time()
            expired_users = []
            
            for user_id, last_click in cooldowns.items():
                if current_time - last_click >= RATE_LIMIT_SECONDS:
                    expired_users.append(user_id)
            
            # Remove expired cooldowns
            for user_id in expired_users:
                del cooldowns[user_id]
            
            if expired_users:
                try:
                    with open(COOLDOWN_FILE, 'w') as f:
                        json.dump(cooldowns, f, indent=2)
                    logging.info(f"Cleaned up {len(expired_users)} expired button cooldowns")
                except Exception as e:
                    logging.error(f"Error saving cleaned cooldowns: {e}")
                    
        except Exception as e:
            logging.error(f"Error in cleanup_expired_cooldowns: {e}")
            
            # Report critical error to owners
            try:
                await self.report_critical_error("Cooldown Cleanup Error", f"Error in cleanup_expired_cooldowns: {e}")
            except Exception as report_error:
                logging.error(f"Failed to report critical error: {report_error}")

    async def check_and_assign_roles(self):
        """Check if any users need role assignment - optimized for concurrent users"""
        try:
            # Load user data
            from utils import safe_json_read
            user_data = safe_json_read(USER_DATA_FILE, {})
            if not user_data:
                return
            
            current_time = datetime.now(timezone.utc).timestamp()
            delay_seconds = ROLE_ASSIGNMENT_DELAY
            
            # Create a list of users to remove (can't modify dict while iterating)
            users_to_remove = []
            users_to_process = []
            
            # First pass: identify users to process and remove
            for user_id_str, data in user_data.items():
                user_id = int(user_id_str)
                
                # Check if user is still in the guild
                guild_id = GUILD_ID
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                member = guild.get_member(user_id)
                if not member:
                    # User left the server, mark for removal
                    users_to_remove.append(user_id_str)
                    logging.info(f"User {user_id} left the server, will remove from data")
                    continue
                
                # Only assign member role if user submitted the form and doesn't already have it
                button_clicked_at = data.get('button_clicked_at', 0)
                lead_captured = data.get('lead_captured', False)
                if button_clicked_at and lead_captured and not data.get('has_access', False) and not data.get('role_assigned', False):
                    if current_time - button_clicked_at >= delay_seconds:
                        users_to_process.append((user_id_str, data, member))
            
            # Process users in batches to avoid overwhelming Discord API
            batch_size = 10  # Process 10 users at a time
            for i in range(0, len(users_to_process), batch_size):
                batch = users_to_process[i:i + batch_size]
                
                # Process batch concurrently
                tasks = []
                for user_id_str, data, member in batch:
                    task = self.process_user_role_assignment(user_id_str, data, member, user_data)
                    tasks.append(task)
                
                # Wait for batch to complete
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            
            # Remove users who left the server
            for user_id_str in users_to_remove:
                del user_data[user_id_str]
                logging.info(f"Removed user {user_id_str} from data (left server)")
            
            # Save updated data if any users were removed
            if users_to_remove:
                from utils import safe_json_write
                safe_json_write(USER_DATA_FILE, user_data)
                    
        except Exception as e:
            logging.error(f"Error checking role assignments: {e}")
            
            # Report critical error to owners
            try:
                await self.report_critical_error("Role Assignment Error", f"Error in role assignment loop: {e}")
            except Exception as report_error:
                logging.error(f"Failed to report critical error: {report_error}")
    
    async def process_user_role_assignment(self, user_id_str, data, member, user_data):
        """Process role assignment for a single user"""
        try:
            user_id = int(user_id_str)
            
            # Check if user actually has member role before assigning
            member_role_id = MEMBER_ROLE_ID
            if member_role_id:
                guild = self.bot.get_guild(GUILD_ID)
                if guild:
                    member_role = guild.get_role(member_role_id)
                    if member_role and member_role not in member.roles:
                        await self.assign_member_role(user_id)
                        # Remove unverified role when they get member role
                        await self.remove_unverified_role(user_id)
                    else:
                        # User already has member role, just update data
                        data['has_access'] = True
                        data['role_assigned'] = True
                        user_data[user_id_str] = data
                        logging.info(f"User {user_id} already has member role, updated data")
        except Exception as e:
            logging.error(f"Error processing role assignment for user {user_id_str}: {e}")

    async def assign_member_role(self, user_id):
        """Assign member role to user"""
        try:
            guild_id = GUILD_ID
            member_role_id = MEMBER_ROLE_ID
            logs_channel_id = LOGS_CHANNEL_ID
            
            if not guild_id or not member_role_id:
                logging.error("GUILD_ID or MEMBER_ROLE_ID not set")
                return
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logging.error(f"Guild {guild_id} not found")
                return
            
            member = guild.get_member(user_id)
            if not member:
                logging.info(f"Member {user_id} not found in guild (likely left)")
                return
            
            role = guild.get_role(member_role_id)
            if not role:
                logging.error(f"Role {member_role_id} not found")
                return
            
            if role in member.roles:
                logging.info(f"User {user_id} already has member role")
                # Update user data to reflect they already have the role
                from utils import safe_json_read
                user_data = safe_json_read(USER_DATA_FILE, {})
                
                user_id_str = str(user_id)
                if user_id_str in user_data:
                    user_data[user_id_str]['has_access'] = True
                    user_data[user_id_str]['role_assigned'] = True
                    
                    with open(USER_DATA_FILE, 'w') as f:
                        json.dump(user_data, f, indent=2)
                return
            
            await member.add_roles(role)
            logging.info(f"Assigned member role to user {user_id}")
            
            # Log to logs channel
            if logs_channel_id:
                logs_channel = guild.get_channel(logs_channel_id)
                if logs_channel:
                    embed = discord.Embed(
                        title="✅ Member Role Assigned",
                        description=f"**{member.mention}** has been assigned the Member role",
                        color=0x00ff00,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="User ID", value=f"`{user_id}`", inline=True)
                    embed.add_field(name="Role", value=f"✅ Member", inline=True)
                    embed.set_thumbnail(url=member.display_avatar.url)
                    
                    try:
                        await logs_channel.send(embed=embed)
                    except discord.Forbidden:
                        logging.warning(f"Bot doesn't have permission to send messages to logs channel {logs_channel_id}")
                    except Exception as e:
                        logging.error(f"Error sending log message: {e}")
            
            # Update user data
            try:
                with open(USER_DATA_FILE, 'r') as f:
                    user_data = json.load(f)
            except FileNotFoundError:
                user_data = {}
            
            user_id_str = str(user_id)
            if user_id_str in user_data:
                user_data[user_id_str]['has_access'] = True
                user_data[user_id_str]['role_assigned'] = True
                
                safe_json_write(USER_DATA_FILE, user_data)
            
        except Exception as e:
            logging.error(f"Error assigning member role to {user_id}: {e}")
            
            # Report critical error to owners
            try:
                await self.report_critical_error("Member Role Assignment Error", f"Failed to assign member role to user {user_id}: {e}")
            except Exception as report_error:
                logging.error(f"Failed to report critical error: {report_error}")

    async def remove_unverified_role(self, user_id):
        """Remove unverified role from user"""
        try:
            guild_id = GUILD_ID
            unverified_role_id = UNVERIFIED_ROLE_ID
            logs_channel_id = LOGS_CHANNEL_ID
            
            if not guild_id or not unverified_role_id:
                logging.error("GUILD_ID or UNVERIFIED_ROLE_ID not set")
                return
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logging.error(f"Guild {guild_id} not found")
                return
            
            member = guild.get_member(user_id)
            if not member:
                logging.info(f"Member {user_id} not found in guild (likely left)")
                return
            
            role = guild.get_role(unverified_role_id)
            if not role:
                logging.error(f"Role {unverified_role_id} not found")
                return
            
            if role not in member.roles:
                logging.info(f"User {user_id} doesn't have unverified role")
                return
            
            await member.remove_roles(role)
            logging.info(f"Removed unverified role from user {user_id}")
            
            # Log to logs channel
            if logs_channel_id:
                logs_channel = guild.get_channel(logs_channel_id)
                if logs_channel:
                    embed = discord.Embed(
                        title="🔓 Unverified Role Removed",
                        description=f"**{member.mention}** has had their Unverified role removed",
                        color=0xffa500,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="User ID", value=f"`{user_id}`", inline=True)
                    embed.add_field(name="Role Removed", value=f"🔓 Unverified", inline=True)
                    embed.set_thumbnail(url=member.display_avatar.url)
                    
                    try:
                        await logs_channel.send(embed=embed)
                    except discord.Forbidden:
                        logging.warning(f"Bot doesn't have permission to send messages to logs channel {logs_channel_id}")
                    except Exception as e:
                        logging.error(f"Error sending log message: {e}")
            
            # Update user data to mark unverified role as removed
            try:
                with open(USER_DATA_FILE, 'r') as f:
                    user_data = json.load(f)
            except FileNotFoundError:
                user_data = {}
            
            user_id_str = str(user_id)
            if user_id_str in user_data:
                user_data[user_id_str]['unverified_role_assigned'] = False
                
                safe_json_write(USER_DATA_FILE, user_data)
            
        except Exception as e:
            logging.error(f"Error removing unverified role from {user_id}: {e}")

    async def sync_user_data_with_roles(self):
        """Sync user data with actual Discord roles to prevent incorrect assignments"""
        try:
            guild_id = GUILD_ID
            member_role_id = MEMBER_ROLE_ID
            unverified_role_id = UNVERIFIED_ROLE_ID
            
            if not guild_id:
                logging.error("GUILD_ID not set")
                return
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logging.error(f"Guild {guild_id} not found")
                return
            
            # Load user data
            try:
                with open(USER_DATA_FILE, 'r') as f:
                    user_data = json.load(f)
            except FileNotFoundError:
                logging.info("No user data file found, skipping sync")
                return
            
            member_role = guild.get_role(member_role_id) if member_role_id else None
            unverified_role = guild.get_role(unverified_role_id) if unverified_role_id else None
            
            updated = False
            users_to_remove = []
            
            for user_id_str, data in user_data.items():
                user_id = int(user_id_str)
                member = guild.get_member(user_id)
                
                if not member:
                    # User left the server, mark for removal
                    users_to_remove.append(user_id_str)
                    logging.info(f"User {user_id} left the server, will remove from sync data")
                    continue
                
                # Check if user has member role
                has_member_role = member_role and member_role in member.roles
                has_unverified_role = unverified_role and unverified_role in member.roles
                
                # Update data to match actual Discord state
                if data.get('has_access', False) != has_member_role:
                    data['has_access'] = has_member_role
                    data['role_assigned'] = has_member_role
                    updated = True
                    logging.info(f"Synced member role status for user {user_id}: {has_member_role}")
                
                if data.get('unverified_role_assigned', False) != has_unverified_role:
                    data['unverified_role_assigned'] = has_unverified_role
                    updated = True
                    logging.info(f"Synced unverified role status for user {user_id}: {has_unverified_role}")
                
                # If user has member role but no button click recorded, reset their data
                if has_member_role and not data.get('button_clicked_at', 0):
                    data['button_clicked_at'] = 0
                    updated = True
                    logging.info(f"Reset button click data for user {user_id} - they have member role but no click recorded")
            
            # Remove users who left the server
            for user_id_str in users_to_remove:
                del user_data[user_id_str]
                logging.info(f"Removed user {user_id_str} from sync data (left server)")
                updated = True
            
            if updated:
                safe_json_write(USER_DATA_FILE, user_data)
                logging.info("User data synced with Discord roles")
            
        except Exception as e:
            logging.error(f"Error syncing user data with roles: {e}")

    async def send_premium_welcome_dm(self, member, premium_role_name):
        """Send premium welcome DM to user with verification channel link"""
        try:
            # Get welcome verify channel
            guild = member.guild
            welcome_verify_channel = None
            
            # Look for welcome-verify channel
            for channel in guild.text_channels:
                if channel.name == 'welcome-verify':
                    welcome_verify_channel = channel
                    break
            
            # Use centralized verification DM embed
            from config import get_verification_dm_embed
            embed = get_verification_dm_embed()
            
            # Create view with button
            view = discord.ui.View()
            
            if welcome_verify_channel:
                # Add button to go to welcome-verify channel
                button = discord.ui.Button(
                    label="Go to Verification",
                    style=discord.ButtonStyle.primary,
                    emoji="🔗"
                )
                
                async def button_callback(interaction):
                    if interaction.user.id != member.id:
                        await interaction.response.send_message("This button is not for you!", ephemeral=True)
                        return
                    
                    await interaction.response.send_message(
                        f"Please visit {welcome_verify_channel.mention} to complete your verification!",
                        ephemeral=True
                    )
                
                button.callback = button_callback
                view.add_item(button)
            else:
                embed.add_field(
                    name="⚠️ Notice",
                    value="Please visit the #welcome-verify channel to complete your verification.",
                    inline=False
                )
            
            await member.send(embed=embed, view=view)
            logging.info(f"Sent premium welcome DM to {member.display_name} ({member.id}) with {premium_role_name} tier")
            
        except discord.Forbidden:
            logging.warning(f"Could not send premium welcome DM to {member.display_name} ({member.id}) - DMs disabled")
        except Exception as e:
            logging.error(f"Error sending premium welcome DM to {member.display_name} ({member.id}): {e}")

    async def ping_in_verify_channel(self, member, premium_role_name):
        """Ghost ping user in #verify channel and delete message"""
        try:
            guild = member.guild
            verify_channel = None
            
            # Look for verify channel
            for channel in guild.text_channels:
                if channel.name == 'verify':
                    verify_channel = channel
                    break
            
            if verify_channel:
                # Send ghost ping message and delete it after 30 seconds
                message = await verify_channel.send(f"{member.mention}")
                await asyncio.sleep(30)
                await message.delete()
                logging.info(f"Ghost pinged user {member.display_name} ({member.id}) in #verify channel")
            else:
                logging.warning("Verify channel not found - cannot ping user")
                
        except Exception as e:
            logging.error(f"Error ghost pinging user in verify channel: {e}")

    async def report_critical_error(self, error_type, error_message):
        """Report critical errors to owners via logs and DM"""
        try:
            # Import the error reporting function
            from .verification import report_critical_error
            await report_critical_error(error_type, error_message, self.bot)
        except Exception as e:
            logging.error(f"Error in welcome cog error reporting: {e}")

    async def cleanup_logged_members_loop(self):
        """Background task to clean up old logged members"""
        while True:
            try:
                await self.cleanup_old_logged_members()
                await asyncio.sleep(3600)  # Check every hour
            except Exception as e:
                logging.error(f"Error in logged members cleanup loop: {e}")
                await asyncio.sleep(7200)  # Wait longer on error

    async def cleanup_old_logged_members(self):
        """Clean up old logged members (older than 24 hours)"""
        try:
            current_time = time.time()
            
            # Clean up old timestamps (older than 1 hour)
            old_timestamps = []
            for user_id, timestamp in self.member_join_timestamps.items():
                if current_time - timestamp > 3600:  # 1 hour
                    old_timestamps.append(user_id)
            
            for user_id in old_timestamps:
                del self.member_join_timestamps[user_id]
            
            if old_timestamps:
                logging.info(f"Cleaned up {len(old_timestamps)} old member join timestamps")
            
            # For logged_members, clear if too many entries
            if len(self.logged_members) > 1000:  # If we have more than 1000 logged members
                self.logged_members.clear()
                self.save_logged_members()
                logging.info("Cleared logged members set (too many entries)")
                
        except Exception as e:
            logging.error(f"Error cleaning up old logged members: {e}")

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self.role_assignment_task:
            self.role_assignment_task.cancel()
        if self.cooldown_cleanup_task:
            self.cooldown_cleanup_task.cancel()
        if hasattr(self, 'logged_members_cleanup_task') and self.logged_members_cleanup_task:
            self.logged_members_cleanup_task.cancel()

async def setup(bot):
    await bot.add_cog(Welcome(bot))