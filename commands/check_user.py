import discord
from discord.ext import commands
from discord import ui
import logging
import json
from datetime import datetime, timezone
from config import MEMBER_ROLE_ID, UNVERIFIED_ROLE_ID, USER_DATA_FILE

async def setup(bot):
    @bot.tree.command(name="checkuser", description="Check user status and roles")
    @discord.app_commands.default_permissions(administrator=True)
    async def check_user(interaction: discord.Interaction, user: discord.Member):
        """Check user status and roles (admin only)"""
        try:
            # SECURITY: Check authorization
            from main import is_authorized_guild_or_owner
            if not is_authorized_guild_or_owner(interaction):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ You are not authorized to use this command.", ephemeral=True
                    )
                return
            
            # SECURITY: Block DMs and check admin permissions
            if not interaction.guild:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
                return
            
            if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ You need Administrator permissions!", ephemeral=True)
                return
            
            member_role_id = MEMBER_ROLE_ID
            unverified_role_id = UNVERIFIED_ROLE_ID
            
            member_role = interaction.guild.get_role(member_role_id) if member_role_id else None
            unverified_role = interaction.guild.get_role(unverified_role_id) if unverified_role_id else None
            
            # Check Discord roles
            has_member_role = member_role and member_role in user.roles
            has_unverified_role = unverified_role and unverified_role in user.roles
            
            # Load user data
            from config import USER_DATA_FILE
            from utils import safe_json_read
            user_data = safe_json_read(USER_DATA_FILE, {})
            user_info = user_data.get(str(user.id), {})
            
            embed = discord.Embed(
                title=f"👤 User Status: {user.display_name}",
                description=f"User ID: `{user.id}`",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            # Discord Roles
            roles_info = []
            if has_member_role:
                roles_info.append("✅ Member Role")
            else:
                roles_info.append("❌ Member Role")
            
            if has_unverified_role:
                roles_info.append("🔒 Unverified Role")
            else:
                roles_info.append("🔓 No Unverified Role")
            
            embed.add_field(name="Discord Roles", value="\n".join(roles_info), inline=False)
            
            # User Data
            data_info = []
            if user_info.get('button_clicked_at'):
                button_time = datetime.fromtimestamp(user_info['button_clicked_at'], tz=timezone.utc)
                data_info.append(f"🔘 Button clicked: {button_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            else:
                data_info.append("❌ Button not clicked")
            
            if user_info.get('joined_at'):
                join_time = datetime.fromtimestamp(user_info['joined_at'], tz=timezone.utc)
                data_info.append(f"📥 Joined: {join_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            else:
                data_info.append("❌ Join time not recorded")
            
            data_info.append(f"✅ Has access: {user_info.get('has_access', False)}")
            data_info.append(f"🎭 Role assigned: {user_info.get('role_assigned', False)}")
            data_info.append(f"🔒 Unverified role assigned: {user_info.get('unverified_role_assigned', False)}")
            data_info.append(f"📋 Lead captured: {user_info.get('lead_captured', False)}")
            
            # Check button cooldown status
            try:
                from cogs.verification import COOLDOWN_FILE, RATE_LIMIT_SECONDS
                import time
                
                try:
                    with open(COOLDOWN_FILE, 'r') as f:
                        cooldowns = json.load(f)
                    last_click = cooldowns.get(str(user.id), 0)
                    if last_click:
                        current_time = time.time()
                        time_since_click = current_time - last_click
                        if time_since_click < RATE_LIMIT_SECONDS:
                            remaining = int(RATE_LIMIT_SECONDS - time_since_click)
                            data_info.append(f"⏳ Button cooldown: {remaining}s remaining")
                        else:
                            data_info.append("✅ Button cooldown: Expired")
                    else:
                        data_info.append("✅ Button cooldown: None")
                except FileNotFoundError:
                    data_info.append("✅ Button cooldown: No file")
                except Exception as e:
                    data_info.append(f"❓ Button cooldown: Error ({e})")
            except ImportError:
                data_info.append("❓ Button cooldown: Module not available")
            
            embed.add_field(name="User Data", value="\n".join(data_info), inline=False)

            # Verification Details (survey status, premium role, monitoring)
            verification_lines = []
            survey_status = user_info.get('survey_status', 'unknown')
            premium_role_name = user_info.get('premium_role_name', 'Unknown')
            premium_role_id = user_info.get('premium_role_id', 'N/A')

            verification_lines.append(f"📝 Survey status: {survey_status}")
            verification_lines.append(f"💼 Premium role: {premium_role_name} (ID: {premium_role_id})")

            # Check if enhanced monitoring is active for this user
            monitoring_active = False
            try:
                from cogs.webhook_handler import WebhookHandler
                bot = interaction.client if hasattr(interaction, 'client') else None
                if bot:
                    for cog in bot.cogs.values():
                        if isinstance(cog, WebhookHandler):
                            monitoring_active = str(user.id) in getattr(cog, 'active_monitors', {})
                            break
            except Exception:
                monitoring_active = False

            verification_lines.append(f"📡 Monitoring active: {monitoring_active}")
            embed.add_field(name="Verification Details", value="\n".join(verification_lines), inline=False)
            
            # Status Summary
            status = []
            lead_captured = user_info.get('lead_captured', False)
            button_clicked_at = user_info.get('button_clicked_at', 0)
            if has_member_role and user_info.get('has_access'):
                status.append("✅ **CORRECT**: User has member role and data shows access")
            elif has_member_role and not user_info.get('has_access'):
                status.append("⚠️ **MISMATCH**: User has member role but data shows no access")
            elif not has_member_role and user_info.get('has_access'):
                status.append("⚠️ **MISMATCH**: User doesn't have member role but data shows access")
            elif not has_member_role and not user_info.get('has_access') and lead_captured:
                status.append("⏳ **PENDING**: User submitted Typeform, waiting for role assignment")
            elif not has_member_role and not user_info.get('has_access') and button_clicked_at and not lead_captured:
                status.append("📋 **WAITING**: User clicked button, waiting for Typeform submission")
            elif not has_member_role and not user_info.get('has_access') and not button_clicked_at:
                status.append("📋 **NEEDS SURVEY**: User needs to click button and complete Typeform")
            else:
                status.append("✅ **CORRECT**: User doesn't have member role and data shows no access")
            
            embed.add_field(name="Status Summary", value="\n".join(status), inline=False)
            
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"Checked by {interaction.user.name}")
            
            # Admin action: restart webhook verification button
            class RestartWebhookButton(ui.Button):
                def __init__(self, target_user_id: str):
                    super().__init__(
                        style=discord.ButtonStyle.primary,
                        label="🔁 Restart Webhook Verification",
                        custom_id=f"restart_webhook_{target_user_id}"
                    )
                    self.target_user_id = target_user_id

                async def callback(self, button_interaction: discord.Interaction):
                    # Ensure only admins can trigger this
                    if not isinstance(button_interaction.user, discord.Member) or not button_interaction.user.guild_permissions.administrator:
                        if not button_interaction.response.is_done():
                            await button_interaction.response.send_message("❌ Admins only.", ephemeral=True)
                        return

                    try:
                        from cogs.webhook_handler import WebhookHandler
                        bot_ref = button_interaction.client if hasattr(button_interaction, 'client') else None
                        webhook_handler = None
                        if bot_ref:
                            for cog in bot_ref.cogs.values():
                                if isinstance(cog, WebhookHandler):
                                    webhook_handler = cog
                                    break

                        if webhook_handler:
                            await webhook_handler.start_enhanced_monitoring(button_interaction.guild, self.target_user_id)
                            if not button_interaction.response.is_done():
                                await button_interaction.response.send_message(
                                    f"🔁 Restarted webhook monitoring for user `{self.target_user_id}`.",
                                    ephemeral=True
                                )
                        else:
                            if not button_interaction.response.is_done():
                                await button_interaction.response.send_message(
                                    "⚠️ Webhook handler not available.",
                                    ephemeral=True
                                )
                    except Exception as err:
                        logging.error(f"Error restarting webhook monitoring: {err}")
                        try:
                            if not button_interaction.response.is_done():
                                await button_interaction.response.send_message("❌ Failed to restart monitoring.", ephemeral=True)
                        except Exception:
                            pass

            class AdminActionsView(ui.View):
                def __init__(self, target_user_id: int):
                    super().__init__(timeout=180)
                    self.add_item(RestartWebhookButton(str(target_user_id)))

            view = AdminActionsView(user.id)

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                
        except Exception as e:
            logging.error(f"Error checking user: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while checking the user.", ephemeral=True)
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}") 