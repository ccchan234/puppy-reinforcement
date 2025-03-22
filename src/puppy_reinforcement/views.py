# -*- coding: utf-8 -*-

# Puppy Reinforcement Add-on for Anki
#
# Copyright (C) 2016-2023  Aristotelis P. <https://glutanimate.com/>
# Copyright (C) 2019-2020  zjosua <https://github.com/zjosua>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version, with the additions
# listed at the end of the license file that accompanied this program.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# NOTE: This program is subject to certain additional terms pursuant to
# Section 7 of the GNU Affero General Public License.  You should have
# received a copy of these additional terms immediately following the
# terms and conditions of the GNU Affero General Public License that
# accompanied this program.
#
# If not, please request a copy through one of the means of contact
# listed here: <https://glutanimate.com/contact/>.
#
# Any modifications to this file must keep this entire header intact.

from aqt.gui_hooks import add_cards_did_add_note, reviewer_did_answer_card
from aqt import gui_hooks, mw

from .config import config
from .reinforcer import PuppyReinforcer


def initialize_views(puppy_reinforcer: PuppyReinforcer):
    if config["local"]["count_reviewing"]:
        reviewer_did_answer_card.append(puppy_reinforcer.show_dog)
    if config["local"]["count_adding"]:
        add_cards_did_add_note.append(puppy_reinforcer.show_dog)
    
    # Register the bridge command for closing the notification
    gui_hooks.webview_did_receive_js_message.append(on_js_message)

def on_js_message(handled, message, context):
    """
    Handle JS messages for the Puppy Reinforcement addon
    
    This function is compatible with both older and newer Anki versions.
    For Anki 23.12.1+ it returns a bool as required by the new API.
    """
    # Import inside the function to avoid circular imports
    from .gui.notification import Notification
    
    if message == "close-puppy-reinforcement":
        # Find and close any open Notification instance
        if hasattr(Notification, "_current_instance") and Notification._current_instance:
            try:
                Notification._current_instance.hide()
            except Exception as e:
                print(f"Error closing notification: {e}")
        return (True, None)  # Mark as handled with proper return value
    
    elif message == "toggle-fullscreen":
        # Toggle fullscreen for any open notification
        if hasattr(Notification, "_current_instance") and Notification._current_instance:
            try:
                if hasattr(Notification._current_instance, "_toggle_fullscreen"):
                    Notification._current_instance._toggle_fullscreen()
            except Exception as e:
                print(f"Error toggling fullscreen: {e}")
        return (True, None)  # Mark as handled with proper return value
    
    # For Anki 23.12.1+ compatibility, we need to return the correct type
    if isinstance(handled, tuple):
        return handled  # Pass through unhandled messages with tuple format
    return handled  # Pass through unhandled messages for older versions

# Import Notification class here to avoid circular imports
from .gui.notification import Notification
