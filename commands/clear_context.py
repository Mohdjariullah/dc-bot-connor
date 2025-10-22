import discord
from discord.ext import commands
import json
import logging
import os
import io
from config import CONVERSATION_CONTEXT_FILE

async def setup(bot):
    @bot.tree.command(name="clear_context", description="Clear all AI conversation context messages (Owner only)")
    async def clear_context(interaction: discord.Interaction):
        """Clear all AI conversation context messages - Owner only command"""
        try:
            # SECURITY: Check if user is bot owner
            from main import OWNER_USER_IDS
            if interaction.user.id not in OWNER_USER_IDS:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ This command is only available to bot owners.", ephemeral=True
                    )
                return
            
            # Check if the conversation context file exists
            if not os.path.exists(CONVERSATION_CONTEXT_FILE):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "✅ Conversation context file doesn't exist (already empty).", ephemeral=True
                    )
                return
            
            # Read the current content before clearing
            try:
                with open(CONVERSATION_CONTEXT_FILE, 'r') as f:
                    context_data = f.read()
                
                # Send the file content to ALL owners via DM
                from main import OWNER_USER_IDS
                owners_dm_sent = 0
                owners_dm_failed = []
                initiator_name = interaction.user.name
                initiator_id = interaction.user.id
                
                for owner_id in OWNER_USER_IDS:
                    try:
                        owner_user = interaction.client.get_user(owner_id)
                        if owner_user is None:
                            try:
                                owner_user = await interaction.client.fetch_user(owner_id)
                            except Exception:
                                owner_user = None
                        
                        if owner_user is None:
                            owners_dm_failed.append(owner_id)
                            continue
                        
                        # Create a fresh Discord file object per send
                        file_content = discord.File(
                            io.BytesIO(context_data.encode('utf-8')),
                            filename='data/ai_conversation_context_backup.json'
                        )
                        await owner_user.send(
                            content=(
                                "📄 **AI Conversation Context Backup**\n"
                                f"Initiated by: **{initiator_name}** (ID: `{initiator_id}`)\n\n"
                                "Here's the conversation context that was cleared:"
                            ),
                            file=file_content
                        )
                        logging.info(f"Conversation context backup sent to owner {owner_id}")
                        owners_dm_sent += 1
                    except discord.Forbidden:
                        logging.warning(f"Could not send DM to owner {owner_id} - DMs may be disabled")
                        owners_dm_failed.append(owner_id)
                    except Exception as dm_error:
                        logging.error(f"Error sending DM to owner {owner_id}: {dm_error}")
                        owners_dm_failed.append(owner_id)
                
                # Clear the conversation context file by writing an empty object
                with open(CONVERSATION_CONTEXT_FILE, 'w') as f:
                    json.dump({}, f, indent=2)
                
                logging.info(f"Conversation context cleared by owner {interaction.user.id} ({interaction.user.name})")
                
                if owners_dm_sent > 0 and not owners_dm_failed:
                    dm_status = f" and backup sent to all {owners_dm_sent} owners via DM"
                elif owners_dm_sent > 0 and owners_dm_failed:
                    dm_status = f" and backup sent to {owners_dm_sent} owner(s) (failed for {len(owners_dm_failed)})"
                else:
                    dm_status = " (couldn't DM any owners - DMs may be disabled)"
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"✅ All AI conversation context messages have been cleared successfully!{dm_status}\n"
                        f"👤 Initiated by: **{initiator_name}** (ID: `{initiator_id}`)", ephemeral=True
                    )
                    
            except Exception as file_error:
                logging.error(f"Error clearing conversation context file: {file_error}")
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Failed to clear conversation context file. Check logs for details.", ephemeral=True
                    )
                    
        except Exception as e:
            logging.error(f"Error in clear_context command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while processing the command.", ephemeral=True
                    )
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")
