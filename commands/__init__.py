import logging
from discord.ext import commands
import importlib

# Commands package
from .help import setup as help_setup
from .refresh import setup as refresh_setup
from .daily_access import setup as daily_access_setup
from .fix_user_roles import setup as fix_user_roles_setup
from .remove_member_role import setup as remove_member_role_setup
from .check_user import setup as check_user_setup
from .view_leads import setup as view_leads_setup
from .ai_channel import setup as ai_channel_setup
from .verify_webhook import setup as verify_webhook_setup

async def setup(bot: commands.Bot) -> None:
    """Add admin commands to the bot."""
    logger = logging.getLogger(__name__)
    msg = "Loaded commands.{}"
    
    await help_setup(bot)
    logger.debug(msg.format("help"))
    
    await refresh_setup(bot)
    logger.debug(msg.format("refresh"))
    
    await daily_access_setup(bot)
    logger.debug(msg.format("daily_access"))
    
    await fix_user_roles_setup(bot)
    logger.debug(msg.format("fix_user_roles"))

    await remove_member_role_setup(bot)
    logger.debug(msg.format("remove_member_role"))

    await check_user_setup(bot)
    logger.debug(msg.format("check_user"))
    
    await view_leads_setup(bot)
    logger.debug(msg.format("view_leads"))
    
    await ai_channel_setup(bot)
    logger.debug(msg.format("ai_channel"))
    
    await verify_webhook_setup(bot)
    logger.debug(msg.format("verify_webhook"))