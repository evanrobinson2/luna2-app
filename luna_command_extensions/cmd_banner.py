# cmd_banner.py
import logging
from luna_command_extensions.ascii_art import show_ascii_banner
logger = logging.getLogger(__name__)


########################################################
# 1) COMMAND HANDLER FUNCTIONS
########################################################
def cmd_banner(args, loop):
    print ("\n" + show_ascii_banner("Luna Bot"))
