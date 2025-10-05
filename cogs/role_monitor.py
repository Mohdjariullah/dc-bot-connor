import discord
from discord.ext import commands
import logging
import os
import asyncio
from datetime import datetime, timezone
from utils import safe_json_write, safe_json_read

# Role IDs from environment variables
UNVERIFIED_ROLE_ID = int(os.getenv('UNVERIFIED_ROLE_ID', 0))
VIP_ROLE_ID = int(os.getenv('VIP_ROLE_ID', 0))
HUNDRED_K_ROLE_ID = int(os.getenv('HUNDRED_K_ROLE_ID', 0))
SUBMISSION_LOGS_CHANNEL_ID = int(os.getenv('SUBMISSION_LOGS_CHANNEL_ID', 0))
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID', 0))

USER_DATA_FILE = 'user_data.json'

class RoleMonitor(commands.Cog):
    """Monitor premium role assignments and handle verification flow"""
    
    def __init__(self, bot):
        self.bot = bot
        self.premium_role_ids = {}
        
        # Build premium role IDs from environment variables
        if VIP_ROLE_ID:
            self.premium_role_ids[VIP_ROLE_ID] = 'VIP'
        if HUNDRED_K_ROLE_ID:
            self.premium_role_ids[HUNDRED_K_ROLE_ID] = '100k'
        
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Monitor when members get premium roles assigned"""
        try:
            # Check if any premium roles were added
            before_roles = {role.id for role in before.roles}
            after_roles = {role.id for role in after.roles}
            
            # Find newly added premium roles
            new_premium_roles = []
            for role_id, role_name in self.premium_role_ids.items():
                if role_id in after_roles and role_id not in before_roles:
                    new_premium_roles.append((role_id, role_name))
            
            if not new_premium_roles:
                return
                
            logging.info(f"Detected premium role assignment(s) for {after.display_name} ({after.id}): {[role[1] for role in new_premium_roles]}")
            
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
    
    async def ping_in_welcome_verify(self, member, role_name):
        """Ping user in #welcome-verify channel and delete message"""
        try:
            guild = member.guild
            welcome_verify_channel = None
            
            # Find welcome-verify channel
            for channel in guild.text_channels:
                if channel.name == 'welcome-verify':
                    welcome_verify_channel = channel
                    break
            
            if welcome_verify_channel:
                # Send ping message and delete it after 6 seconds
                message = await welcome_verify_channel.send(f"{member.mention}")
                await asyncio.sleep(6)
                await message.delete()
                logging.info(f"Ghost pinged {member.display_name} ({member.id}) in #welcome-verify channel")
            else:
                logging.warning("welcome-verify channel not found")
                
        except Exception as e:
            logging.error(f"Error pinging in welcome-verify channel: {e}")
    
    async def send_verification_dm(self, member, role_name):
        """Send DM with verification message and button"""
        try:
            # Welcome channel ID from environment
            welcome_channel_id = WELCOME_CHANNEL_ID
            
            # Create the main message text
            message_text = f"Hey {member.display_name}, we noticed you've been assigned the **{role_name}** role.\nPlease complete the verification survey to unlock your access."
            
            # Create embed like the image shows
            embed = discord.Embed(
                title="👋 Welcome to the Server!",
                description=(
                    "To access your subscription and the community, please complete the verification process.\n"
                    "Click the button below to start verifying!\n"
                    "We're excited to have you with us!\n"
                    "Join our community today!"
                ),
                color=0x00ff00
            )
            
            # Add the welcome channel ID as a field if available
            if welcome_channel_id:
                embed.add_field(
                    name="📋 Welcome Channel",
                    value=f"<#{welcome_channel_id}>",
                    inline=False
                )
            
            # Create view with button
            view = VerificationDMView()
            
            await member.send(content=message_text, embed=embed, view=view)
            logging.info(f"Sent verification DM to {member.display_name} ({member.id})")
            
        except discord.Forbidden:
            logging.warning(f"Could not send DM to {member.display_name} ({member.id}) - DMs disabled")
        except Exception as e:
            logging.error(f"Error sending verification DM: {e}")

class VerificationDMView(discord.ui.View):
    """View for the verification DM button"""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VerificationDMButton())

class VerificationDMButton(discord.ui.Button):
    """Button to redirect to verification channel"""
    
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="Start Verification",
            emoji="🔗"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click"""
        try:
            # Welcome channel ID from environment
            welcome_channel_id = WELCOME_CHANNEL_ID
            
            if welcome_channel_id:
                # Create Discord message link to the welcome channel
                guild_id = interaction.guild.id if interaction.guild else 0
                message_link = f"https://discord.com/channels/{guild_id}/{welcome_channel_id}"
                
                await interaction.response.send_message(
                    f"Please visit <#{welcome_channel_id}> to complete your verification!\n\n[Click here to go directly to the channel]({message_link})",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Please visit the welcome channel to complete your verification!",
                    ephemeral=True
                )
                
        except Exception as e:
            logging.error(f"Error in verification DM button callback: {e}")
            try:
                await interaction.response.send_message(
                    "An error occurred. Please try again later.",
                    ephemeral=True
                )
            except:
                pass

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
            
            # Add Typeform link with user ID parameter
            typeform_link = f"https://form.typeform.com/to/VkuOahlj#auth_code={user_id}"
            embed.add_field(
                name="🔗 Complete Survey",
                value=f"[Click here to fill out the survey]({typeform_link})",
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

async def setup(bot):
    await bot.add_cog(RoleMonitor(bot))
