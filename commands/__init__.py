import logging
from discord.ext import commands
import importlib

# Commands package
from .help import setup as help_setup
from .refresh import setup as refresh_setup
from .fix_user_roles import setup as fix_user_roles_setup
from .remove_member_role import setup as remove_member_role_setup
from .check_user import setup as check_user_setup
from .ai_channel import setup as ai_channel_setup
from .clear_context import setup as clear_context_setup
from .clear_dm import setup as clear_dm_setup
async def setup(bot: commands.Bot) -> None:
    """Add admin commands to the bot."""
    logger = logging.getLogger(__name__)
    msg = "Loaded commands.{}"
    
    await help_setup(bot)
    logger.debug(msg.format("help"))
    
    await refresh_setup(bot)
    logger.debug(msg.format("refresh"))
    
    await fix_user_roles_setup(bot)
    logger.debug(msg.format("fix_user_roles"))

    await remove_member_role_setup(bot)
    logger.debug(msg.format("remove_member_role"))

    await check_user_setup(bot)
    logger.debug(msg.format("check_user"))
           
    await ai_channel_setup(bot)
    logger.debug(msg.format("ai_channel"))
    
    await clear_context_setup(bot)
    logger.debug(msg.format("clear_context"))

    await clear_dm_setup(bot)
    logger.debug(msg.format("clear_dm"))