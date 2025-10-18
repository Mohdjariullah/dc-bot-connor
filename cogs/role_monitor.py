import discord
from discord.ext import commands
import logging
import asyncio
from datetime import datetime, timezone
from utils import safe_json_write, safe_json_read
from config import (
    UNVERIFIED_ROLE_ID, WELCOME_CHANNEL_ID,
    USER_DATA_FILE, get_premium_role_ids
)

class RoleMonitor(commands.Cog):
    """Monitor premium role assignments and handle verification flow"""
    
    def __init__(self, bot):
        self.bot = bot
        self.premium_role_ids = get_premium_role_ids()
        # Add cooldown tracking to prevent rapid role changes
        self.role_change_cooldowns = {}  # user_id -> timestamp
        self.cooldown_duration = 30  # 30 seconds cooldown between role changes
        logging.info(f"Role monitor initialized with premium role IDs: {list(self.premium_role_ids.keys())}")
        
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Monitor when members get premium roles assigned"""
        try:
            # Debug logging
            logging.info(f"Member update detected for {after.display_name} ({after.id})")
            
            # Skip if no premium roles configured
            if not self.premium_role_ids:
                logging.info("No premium roles configured, skipping")
                return
            
            # Skip if this is a bot user
            if after.bot:
                logging.info(f"Skipping bot user {after.display_name}")
                return
                
            # Check if any premium roles were added
            before_roles = {role.id for role in before.roles}
            after_roles = {role.id for role in after.roles}
            
            logging.info(f"Before roles: {[role.name for role in before.roles]}")
            logging.info(f"After roles: {[role.name for role in after.roles]}")
            logging.info(f"Monitoring for premium role IDs: {list(self.premium_role_ids.keys())}")
            
            # Find newly added premium roles
            new_premium_roles = []
            for role_id in self.premium_role_ids.keys():
                if role_id in after_roles and role_id not in before_roles:
                    # Get actual role name from Discord
                    role = after.guild.get_role(role_id)
                    role_name = role.name if role else f"Role_{role_id}"
                    new_premium_roles.append((role_id, role_name))
                    logging.info(f"Detected NEW {role_name} role assignment for {after.display_name} ({after.id})")
            
            if not new_premium_roles:
                return
            
            # CRITICAL: Check if this is a role restoration (not initial assignment)
            # If user was recently verified, this is likely a role restoration, not initial assignment
            user_data = safe_json_read(USER_DATA_FILE, {})
            user_id = str(after.id)
            
            # Check if user is in verified users (means they were verified and should not be reprocessed)
            user_logger_cog = after.guild._state._get_client().get_cog('UserLogger')
            if user_logger_cog and after.id in user_logger_cog.verified_users:
                logging.info(f"User {after.display_name} ({after.id}) was previously verified, skipping role removal")
                return
            
            # Check if user is already verified in user_data.json
            if user_id in user_data:
                user_info = user_data[user_id]
                if user_info.get('survey_status') == 'verified' or user_info.get('has_access', False):
                    logging.info(f"User {after.display_name} ({after.id}) already verified, skipping role removal")
                    return
                
                # Check if this is a role restoration (user has premium_role_id stored but survey_status is verified)
                # This prevents the loop when webhook handler restores roles
                if (user_info.get('premium_role_id') and 
                    user_info.get('survey_status') == 'verified'):
                    logging.info(f"User {after.display_name} ({after.id}) role restoration detected, skipping role removal")
                    return
            
            # Additional safety check: If user has been in the server for more than 1 hour
            # and is getting a premium role, it's likely a restoration, not initial assignment
            time_in_server = (datetime.now(timezone.utc) - after.joined_at).total_seconds()
            if time_in_server > 3600:  # 1 hour
                logging.info(f"User {after.display_name} ({after.id}) has been in server for {time_in_server/3600:.1f} hours, likely role restoration - skipping")
                return
            
            # Cooldown check: Prevent rapid role changes for the same user
            current_time = datetime.now(timezone.utc).timestamp()
            if after.id in self.role_change_cooldowns:
                time_since_last_change = current_time - self.role_change_cooldowns[after.id]
                if time_since_last_change < self.cooldown_duration:
                    logging.info(f"User {after.display_name} ({after.id}) is in cooldown period ({time_since_last_change:.1f}s), skipping role removal")
                    return
            
            # Update cooldown
            self.role_change_cooldowns[after.id] = current_time
                
            logging.info(f"Processing {len(new_premium_roles)} new premium role assignment(s) for {after.display_name} ({after.id}): {[role[1] for role in new_premium_roles]}")
            
            # Process each newly assigned premium role
            for role_id, role_name in new_premium_roles:
                await self.handle_premium_role_assignment(after, role_id, role_name)
                
        except Exception as e:
            logging.error(f"Error in on_member_update: {e}")
    
    async def handle_premium_role_assignment(self, member, role_id, role_name):
        """Handle when a user gets a premium role assigned"""
        try:
            guild = member.guild
            
            # Step 1: Immediately remove the premium role
            premium_role = guild.get_role(role_id)
            if premium_role and premium_role in member.roles:
                await member.remove_roles(premium_role)
                logging.info(f"Removed {role_name} role from {member.display_name} ({member.id})")
            
            # Step 2: Assign UNVERIFIED_ROLE_ID
            if UNVERIFIED_ROLE_ID:
                unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
                if unverified_role and unverified_role not in member.roles:
                    await member.add_roles(unverified_role)
                    logging.info(f"Assigned unverified role to {member.display_name} ({member.id})")
            
            # Step 3: Store user data
            user_data = safe_json_read(USER_DATA_FILE, {})
            user_id = str(member.id)
            user_data[user_id] = {
                'premium_role_id': role_id,
                'premium_role_name': role_name,
                'survey_status': 'pending',
                'role_removed_at': datetime.now(timezone.utc).timestamp()
            }
            safe_json_write(USER_DATA_FILE, user_data)
            
            # Step 4: Wait 10 seconds
            await asyncio.sleep(10)
            
            # Step 5: Ping user in #welcome-verify channel
            await self.ping_in_welcome_verify(member, role_name)
            
            # Step 6: Send DM with verification message and button
            await self.send_verification_dm(member, role_name)
            
        except Exception as e:
            logging.error(f"Error handling premium role assignment: {e}")
    
    async def cleanup_old_cooldowns(self):
        """Clean up old cooldown entries to prevent memory leaks"""
        try:
            current_time = datetime.now(timezone.utc).timestamp()
            expired_users = []
            
            for user_id, timestamp in self.role_change_cooldowns.items():
                if current_time - timestamp > self.cooldown_duration * 2:  # Keep for 2x cooldown duration
                    expired_users.append(user_id)
            
            for user_id in expired_users:
                del self.role_change_cooldowns[user_id]
            
            if expired_users:
                logging.debug(f"Cleaned up {len(expired_users)} expired cooldown entries")
                
        except Exception as e:
            logging.error(f"Error cleaning up cooldowns: {e}")
    
    async def ping_in_welcome_verify(self, member, role_name):
        """Ping user in welcome channel and delete message"""
        try:
            guild = member.guild
            
            # Use welcome channel ID directly
            welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
            
            if welcome_channel:
                # Send ping message and delete it after 6 seconds
                message = await welcome_channel.send(f"{member.mention}")
                await asyncio.sleep(6)
                await message.delete()
                logging.info(f"Ghost pinged {member.display_name} ({member.id}) in welcome channel")
            else:
                logging.warning(f"Welcome channel {WELCOME_CHANNEL_ID} not found")
                
        except Exception as e:
            logging.error(f"Error pinging in welcome channel: {e}")
    
    async def send_verification_dm(self, member, role_name):
        """Send DM with verification message and button"""
        try:
            # Send welcome DM with verification button
            embed = discord.Embed(
                title="👋 Welcome to the Server!",
                description=(
                    "To access your subscription and the community, please complete the verification process.\n\n"
                    "Click the button below to start verifying!\n\n"
                    "We're excited to have you with us!"
                ),
                color=0xF00000
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1370122090631532655/1401222798336200834/20.38.48_73b12891.jpg")
            embed.set_footer(text="Join our community today!")
            
            # Try to add a button to the welcome channel if possible
            welcome_channel_id = WELCOME_CHANNEL_ID
            if welcome_channel_id:
                welcome_channel = member.guild.get_channel(welcome_channel_id)
                if welcome_channel:
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(
                        label="Go to Verification",
                        style=discord.ButtonStyle.link,
                        url=welcome_channel.jump_url
                    ))
                    await member.send(embed=embed, view=view)
                else:
                    await member.send(embed=embed)
            else:
                await member.send(embed=embed)
                
            logging.info(f"Sent verification DM to {member.display_name} ({member.id})")
            
        except discord.Forbidden:
            logging.warning(f"Could not send DM to {member.display_name} ({member.id}) - DMs disabled")
        except Exception as e:
            logging.error(f"Error sending verification DM: {e}")


class WelcomeVerifyView(discord.ui.View):
    """View for the welcome-verify channel message"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(WelcomeVerifyButton())

class WelcomeVerifyButton(discord.ui.Button):
    """Button to start verification process"""
    
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="Start Verification",
            emoji="📋"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click"""
        try:
            user_id = str(interaction.user.id)
            
            # Load user data
            user_data = safe_json_read(USER_DATA_FILE, {})
            user_info = user_data.get(user_id, {})
            
            if not user_info:
                await interaction.response.send_message(
                    "❌ No premium role detected. Please contact support if you believe this is an error.",
                    ephemeral=True
                )
                return
            
            premium_role_name = user_info.get('premium_role_name', 'Premium')
            
            # Create embed with Typeform link
            embed = discord.Embed(
                title="📋 Complete Your Survey to Restore Premium Access",
                description=(
                    f"Welcome back! We've detected your **{premium_role_name}** tier.\n\n"
                    "Complete this quick survey to restore your premium access and get started with The VoCreations Mentorship!\n\n"
                    "👉 **Click the link below to complete the survey**\n\n"
                    "**What happens next?**\n"
                    "1. Complete the survey using the link below\n"
                    "2. We'll automatically restore your premium role\n"
                    "3. You'll have full access to the community!"
                ),
                color=0x00ff00
            )
            
            # Add Typeform link with user ID as hash fragment (not query)
            typeform_link = f"https://form.typeform.com/to/VkuOahlj#auth_code={user_id}"
            embed.add_field(
                name="🔗 Complete Survey",
                value=f"## 👉 **[Click here to fill out the survey]({typeform_link})** 👈",
                inline=False
            )
            
            # Add user ID info for debugging
            embed.add_field(
                name="📋 Your User ID",
                value=f"`{user_id}` (keep this for reference)",
                inline=False
            )
            
            embed.set_footer(text="We'll automatically verify you once you submit the survey!")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Update user data to mark as having clicked the button
            user_data = safe_json_read(USER_DATA_FILE, {})
            existing_data = user_data.get(user_id, {})
            user_data[user_id] = {
                'premium_role_id': existing_data.get('premium_role_id'),
                'premium_role_name': existing_data.get('premium_role_name'),
                'survey_status': 'pending',
                'button_clicked_at': datetime.now(timezone.utc).timestamp()
            }
            safe_json_write(USER_DATA_FILE, user_data)
            
            # Log user verification click
            try:
                user_logger_cog = interaction.client.get_cog('UserLogger')
                if user_logger_cog:
                    await user_logger_cog.log_verification_click(interaction.user)
            except Exception as e:
                logging.error(f"Error logging verification click: {e}")
            
            logging.info(f"Showed Typeform link to user {user_id} via welcome verify button")
            
        except Exception as e:
            logging.error(f"Error in welcome verify button callback: {e}")
            try:
                await interaction.response.send_message(
                    "❌ An error occurred. Please try again later.",
                    ephemeral=True
                )
            except:
                pass

    @commands.Cog.listener()
    async def on_ready(self):
        """Setup periodic cleanup task when bot is ready"""
        # Start periodic cleanup task
        asyncio.create_task(self.periodic_cleanup())
    
    async def periodic_cleanup(self):
        """Periodic cleanup task to prevent memory leaks"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                await self.cleanup_old_cooldowns()
            except Exception as e:
                logging.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

async def setup(bot):
    await bot.add_cog(RoleMonitor(bot))
