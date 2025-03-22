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

from typing import TYPE_CHECKING

import random
import re
import base64
from pathlib import Path
from typing import List, Optional

if TYPE_CHECKING:
    from aqt.main import AnkiQt

from .libaddon.anki.configmanager import ConfigManager
from .libaddon.platform import PATH_THIS_ADDON, pathUserFiles
from .gui.notification import Notification


class PuppyReinforcer:
    _extensions = re.compile(r"\.(jpg|jpeg|png|bmp|gif)$")
    _current_screen = None
    _is_fullscreen = False

    def __init__(self, mw: "AnkiQt", config: ConfigManager):
        self._mw = mw
        self._config = config
        self._images: List[str] = []
        self._playlist: List[int] = []  # self._images indexes

        self._state = {
            "cnt": 0,
            "last": 0,
            "enc": None,
            "ivl": self._config["local"]["encourage_every"],
            "cutoff": False,
        }

        self._read_images()
        self._rebuild_playlist()
        self._shuffle_playlist()

    def show_dog(self, *args, **kwargs):
        local_config = self._config["local"]

        if local_config["reset_counter_on_new_day"]:
            self._maybe_reset_count()

        # Increment counter for stat tracking but show dog every time
        self._state["cnt"] += 1
        
        # Show image after every card review
        image_path = self._get_next_image()
        encouragement = self._get_encouragement(self._state["cnt"])
        self._show_fullscreen_image(encouragement, image_path)
        
        # No need for intermittent reinforcement anymore
        self._state["last"] = self._state["cnt"]

    def _show_fullscreen_image(self, encouragement: str, image_path: str):
        local_config = self._config["local"]
        count = self._state["cnt"]

        # Create CSS for text overlay with minimal background
        font_size = local_config["font_size"]
        text_bg_opacity = local_config["text_bg_opacity"]
        text_bg_color = local_config["text_bg_color"]
        text_color = local_config["text_color"]
        
        # Convert image path to a data URI to avoid loading restrictions
        data_uri = self._get_image_data_uri(image_path)
        
        # Using CSS to create a full-screen image with text overlay
        html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
body, html {{
    margin: 0;
    padding: 0;
    height: 100%;
    width: 100%;
    overflow: hidden;
}}
.fullscreen-container {{
    position: relative;
    width: 100%;
    height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    background-color: black;
    cursor: grab; /* Show grab cursor to indicate draggable */
}}
.fullscreen-container:active {{
    cursor: grabbing; /* Show grabbing cursor when dragging */
}}
.fullscreen-image {{
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
}}
.text-overlay {{
    position: absolute;
    bottom: 50px;
    left: 50%;
    transform: translateX(-50%);
    text-align: center;
}}
.text-container {{
    display: inline-block;
    padding: 10px 20px;
    background-color: {text_bg_color}{int(text_bg_opacity * 255):02x};
    border-radius: 8px;
    color: {text_color};
    font-size: {font_size}px;
    font-family: Arial, sans-serif;
    max-width: 80%;
}}
.click-instruction {{
    margin-top: 10px;
    font-size: {font_size - 2}px;
    opacity: 0.9;
}}
</style>
</head>
<body>
<div class="fullscreen-container">
    <img src="{data_uri}" class="fullscreen-image">
    <div class="text-overlay">
        <div class="text-container">
            <div><b>{count} {'cards' if count > 1 else 'card'} done so far!</b></div>
            <div>{encouragement}</div>
            <div class="click-instruction">Right-click for fullscreen • Press Esc to dismiss</div>
        </div>
    </div>
</div>
<script>
function closeNotification() {{
    pycmd("close-puppy-reinforcement");
}}
</script>
</body>
</html>
"""

        # Ensure the active window can be used as a parent
        active_window = self._mw.app.activeWindow() or self._mw
        
        # Set fullscreen based on class variable
        use_fullscreen = PuppyReinforcer._is_fullscreen
        
        notification = Notification(
            html,
            self._mw.progress,
            # Set duration to 0 so it stays until clicked
            duration=0,
            parent=active_window,
            align_horizontal="center",
            align_vertical="center",
            space_horizontal=0,
            space_vertical=0,
            bg_color="transparent",
            fullscreen=use_fullscreen,  # Use the class variable
        )
        
        # Apply a custom method to the notification instance for toggling fullscreen
        def recreate_on_current_screen(notification_instance, fullscreen=None):
            """Recreate notification on the current screen with specified fullscreen state"""
            PuppyReinforcer._current_screen = notification_instance._current_screen
            PuppyReinforcer._is_fullscreen = fullscreen if fullscreen is not None else PuppyReinforcer._is_fullscreen
            
            # Hide current notification
            notification_instance.hide()
            
            # Show dog with updated fullscreen state
            self._show_fullscreen_image(encouragement, image_path)
            
        # Attach the method to the notification instance
        notification._recreate_on_current_screen = lambda fullscreen=None: recreate_on_current_screen(notification, fullscreen)

        # Position on the correct screen if available
        if PuppyReinforcer._current_screen:
            # Calculate the position based on the current screen
            screen_geometry = PuppyReinforcer._current_screen.geometry()
            notification.setGeometry(screen_geometry)
            
        notification.show()

    def _get_image_data_uri(self, image_path: str) -> str:
        """Convert an image file path to a data URI to avoid browser security restrictions"""
        try:
            # Read image file as binary
            with open(image_path, "rb") as img_file:
                img_data = img_file.read()
            
            # Get the image file extension and determine MIME type
            file_ext = Path(image_path).suffix.lower()
            if file_ext in ('.jpg', '.jpeg'):
                mime_type = 'image/jpeg'
            elif file_ext == '.png':
                mime_type = 'image/png'
            elif file_ext == '.gif':
                mime_type = 'image/gif'
            elif file_ext == '.bmp':
                mime_type = 'image/bmp'
            else:
                mime_type = 'image/jpeg'  # Default
            
            # Encode as base64 and create data URI
            b64_img_data = base64.b64encode(img_data).decode('utf-8')
            return f"data:{mime_type};base64,{b64_img_data}"
        except Exception as e:
            # If something goes wrong, return a placeholder or error image
            print(f"Error loading image {image_path}: {e}")
            return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAIAAADTED8xAAAACXBIWXMAAAsTAAALEwEAmpwYAAAF5mlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSLvu78iIGlkPSJXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQiPz4gPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iQWRvYmUgWE1QIENvcmUgNi4wLWMwMDIgNzkuMTY0NDYwLCAyMDIwLzA1LzEyLTE2OjA0OjE3ICAgICAgICAiPiA8cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiPiA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0iIiB4bWxuczp4bXA9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC8iIHhtbG5zOmRjPSJodHRwOi8vcHVybC5vcmcvZGMvZWxlbWVudHMvMS4xLyIgeG1sbnM6cGhvdG9zaG9wPSJodHRwOi8vbnMuYWRvYmUuY29tL3Bob3Rvc2hvcC8xLjAvIiB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIgeG1sbnM6c3RFdnQ9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9zVHlwZS9SZXNvdXJjZUV2ZW50IyIgeG1wOkNyZWF0b3JUb29sPSJBZG9iZSBQaG90b3Nob3AgMjEuMiAoV2luZG93cykiIHhtcDpDcmVhdGVEYXRlPSIyMDIzLTExLTE2VDIwOjU5OjAyLTA1OjAwIiB4bXA6TW9kaWZ5RGF0ZT0iMjAyMy0xMS0xNlQyMTowMDoxMy0wNTowMCIgeG1wOk1ldGFkYXRhRGF0ZT0iMjAyMy0xMS0xNlQyMTowMDoxMy0wNTowMCIgZGM6Zm9ybWF0PSJpbWFnZS9wbmciIHBob3Rvc2hvcDpDb2xvck1vZGU9IjMiIHBob3Rvc2hvcDpJQ0NQcm9maWxlPSJzUkdCIElFQzYxOTY2LTIuMSIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDozZWM1YzVkMS1jZDg4LTk0NDEtYTJhMS1jZTI1OTU0MGI1ODMiIHhtcE1NOkRvY3VtZW50SUQ9ImFkb2JlOmRvY2lkOnBob3Rvc2hvcDo0YjA3NWFiYS03ODI2LWRiNDctYjdlZS1mYTYwZGRmZWVkZGMiIHhtcE1NOk9yaWdpbmFsRG9jdW1lbnRJRD0ieG1wLmRpZDphMTFiZmE4ZC01N2ZlLTQ0NDgtYWM0OS1mZThjZGJhZmE3M2UiPiA8eG1wTU06SGlzdG9yeT4gPHJkZjpTZXE+IDxyZGY6bGkgc3RFdnQ6YWN0aW9uPSJjcmVhdGVkIiBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOmExMWJmYThkLTU3ZmUtNDQ0OC1hYzQ5LWZlOGNkYmFmYTczZSIgc3RFdnQ6d2hlbj0iMjAyMy0xMS0xNlQyMDo1OTowMi0wNTowMCIgc3RFdnQ6c29mdHdhcmVBZ2VudD0iQWRvYmUgUGhvdG9zaG9wIDIxLjIgKFdpbmRvd3MpIi8+IDxyZGY6bGkgc3RFdnQ6YWN0aW9uPSJzYXZlZCIgc3RFdnQ6aW5zdGFuY2VJRD0ieG1wLmlpZDozZWM1YzVkMS1jZDg4LTk0NDEtYTJhMS1jZTI1OTU0MGI1ODMiIHN0RXZ0OndoZW49IjIwMjMtMTEtMTZUMjE6MDA6MTMtMDU6MDAiIHN0RXZ0OnNvZnR3YXJlQWdlbnQ9IkFkb2JlIFBob3Rvc2hvcCAyMS4yIChXaW5kb3dzKSIgc3RFdnQ6Y2hhbmdlZD0iLyIvPiA8L3JkZjpTZXE+IDwveG1wTU06SGlzdG9yeT4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7DDuYDAAAQLklEQVR4nO3deVAUdx7H8Z8gylUuORRB8AIRQcUj8T7WK0aNmo1RK5tosuuaNVuba9fNH9nKVu2mslW7tUl2zVZtNuuRxCTe930rgnIJCAooIooCCgoCM8zTPwblVAGZh+k+vq9KClGmn68P79c8PT3TNgoJfIhcVRTfA3ARHQW4jA5wGR3gMjrAZXSAy+gAl9EBLqMDXEYHuIwOcBkd4DI6wGV0gMvoAJfRAS6jA1xGB7iMDnAZHeAyOsBldIDL6ACX0QEuowNcRge4jA5wGR3g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"

    def _read_images(self):
        default_path = Path(PATH_THIS_ADDON) / "images"
        user_path = Path(pathUserFiles())

        images = []

        for path in (user_path, default_path):
            if not path.is_dir():
                continue
            for p in path.iterdir():
                if not self._extensions.match(p.suffix.lower()):
                    continue
                images.append(str(p.resolve()))

            if images and self._config["local"]["disable_default_images"]:
                break

        self._images = images

        return images

    def _maybe_reset_count(self):
        """
        Reset on day cutoff traversal
        """
        cutoff = self._get_day_cutoff()

        if self._state["cutoff"] is False:
            # initial value, only available after profile load
            self._state["cutoff"] = cutoff
        elif self._state["cutoff"] == cutoff:
            return

        self._state["cnt"] = 0
        self._state["cutoff"] = cutoff

    def _get_day_cutoff(self) -> Optional[int]:
        if (collection := self._mw.col) is None:
            return None
        scheduler = collection.sched
        if hasattr(scheduler, "day_cutoff"):
            return scheduler.day_cutoff  # 2.1.54+
        try:
            return scheduler.dayCutoff  # type: ignore[union-attr]
        except AttributeError:
            return None

    def _rebuild_playlist(self):
        self._playlist = list(range(len(self._images)))

    def _shuffle_playlist(self):
        random.shuffle(self._playlist)

    def _get_next_image(self) -> str:
        try:
            index = self._playlist.pop()
        except IndexError:
            self._rebuild_playlist()
            self._shuffle_playlist()
            index = self._playlist.pop()
        return self._images[index]

    def _get_encouragement(self, cards: int) -> str:
        local_config = self._config["local"]
        last = self._state["enc"]
        if cards >= local_config["limit_max"]:
            lst = list(local_config["encouragements"]["max"])
        elif cards >= local_config["limit_high"]:
            lst = list(local_config["encouragements"]["high"])
        elif cards >= local_config["limit_middle"]:
            lst = list(local_config["encouragements"]["middle"])
        else:
            lst = list(local_config["encouragements"]["low"])
        if last and last in lst:
            # skip identical encouragement
            lst.remove(last)
        idx = random.randrange(len(lst))
        self._state["enc"] = lst[idx]
        return lst[idx]
