# -*- coding: utf-8 -*-

# Puppy Reinforcement Add-on for Anki
#
# Copyright (C) 2016-2023  Aristotelis P. <https://glutanimate.com/>
# Copyright (C) 2019-2020  zjosua <https://github.com/zjosua>
# Copyright (C) 2016-2023  Ankitects Pty Ltd and contributors
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

"""
Customizable notification pop-up
"""


from typing import Optional, cast

from aqt.progress import ProgressManager
from aqt.qt import (
    QColor,
    QFrame,
    QLabel,
    QMouseEvent,
    QPalette,
    QPoint,
    QResizeEvent,
    Qt,
    QTimer,
    QWidget,
    QWebEngineView,
    QSize,
    QVBoxLayout,
    QScreen,
    QKeyEvent,
)
from aqt.utils import tr
from aqt.webview import AnkiWebView

from ..libaddon.platform import is_anki_version_in_range

# Check Anki version to handle API differences
try:
    from aqt.utils import mungeQA
except ImportError:
    # For Anki 23.10+ the function was renamed/moved
    from anki.utils import mungeQA

class Notification(QLabel):
    _current_timer: Optional[QTimer] = None
    _current_instance: Optional["Notification"] = None

    silentlyClose = True

    def __init__(
        self,
        text: str,
        progress_manager: ProgressManager,
        parent: QWidget,
        duration: int = 3000,
        align_horizontal: str = "left",
        align_vertical: str = "bottom",
        space_horizontal: int = 0,
        space_vertical: int = 0,
        fg_color: str = "#000000",
        bg_color: str = "#FFFFFF",
        fullscreen: bool = False,
        **kwargs,
    ):
        super().__init__(text, parent=parent, **kwargs)
        self._progress_manager = progress_manager
        self._duration = duration
        self._align_horizontal = align_horizontal
        self._align_vertical = align_vertical
        self._space_horizontal = space_horizontal
        self._space_vertical = space_vertical
        self._fullscreen = fullscreen
        
        # Initialize drag tracking variables
        self._dragging = False
        self._drag_position = None
        self._current_screen = None
        
        if fullscreen:
            # For fullscreen mode, use WebView for better rendering
            self.web = AnkiWebView(parent=self)
            self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self.web.setFixedSize(QSize(parent.width(), parent.height()))
            
            # Set up the webview to fill the label
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.web)
            self.setLayout(layout)
            
            # Process our HTML and add necessary bridge commands
            try:
                # Try the newer Anki 23.12+ API
                self.web.stdHtml(
                    body=text,
                    css="",
                    js=[],
                    context=None,
                    body_classes=[]
                )
            except TypeError:
                # Fall back to older Anki API
                try:
                    self.web.stdHtml(text, js=[])
                except TypeError:
                    # Most basic fallback
                    self.web.stdHtml(text)
                    
            # Set custom JavaScript to handle right-click only
            self.web.eval("""
                document.addEventListener('DOMContentLoaded', function() {
                    // No longer make text overlay clickable to dismiss
                    
                    // Handle right-click on container to toggle fullscreen
                    document.addEventListener('contextmenu', function(event) {
                        event.preventDefault(); // Prevent default context menu
                        pycmd('toggle-fullscreen');
                    });

                    // Add keyboard listener for Escape key
                    document.addEventListener('keydown', function(event) {
                        if (event.key === 'Escape') {
                            pycmd('close-puppy-reinforcement');
                        }
                    });
                });
            """)
            
            if hasattr(self.web, 'onBridgeCmd'):
                self.web.onBridgeCmd = self._on_bridge_cmd
            
            # Set up the window for fullscreen mode
            self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
            self.setFixedSize(parent.width(), parent.height())
        else:
            # Standard non-fullscreen mode
            self.setFrameStyle(QFrame.Shape.Panel)
            self.setLineWidth(2)
            self.setWindowFlags(Qt.WindowType.ToolTip)
            
        # Set up appearance
        palette = QPalette()
        if bg_color != "transparent":
            palette.setColor(QPalette.ColorRole.Window, QColor(bg_color))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(fg_color))
            self.setPalette(palette)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setStyleSheet("background-color: transparent;")

        # Make sure we can capture keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Save current screen
        self._save_current_screen()

    def _save_current_screen(self):
        """Save the current screen information"""
        parent = self._parent()
        if parent:
            self._current_screen = parent.screen()

    def _on_bridge_cmd(self, cmd: str):
        """Handle bridge commands safely for Anki 23.12.1+"""
        if cmd == "close-puppy-reinforcement":
            self.hide()
            return True
        elif cmd == "toggle-fullscreen":
            self._toggle_fullscreen()
            return True
        return False

    def _toggle_fullscreen(self):
        """Toggle between fullscreen and normal mode"""
        if self._fullscreen:
            # Switch to normal mode
            self._fullscreen = False
            self.hide()
            # Recreate notification in normal mode on the same screen
            self._recreate_on_current_screen(fullscreen=False)
        else:
            # Switch to fullscreen mode
            self._fullscreen = True
            self.hide()
            # Recreate notification in fullscreen mode on the same screen
            self._recreate_on_current_screen(fullscreen=True)

    def _recreate_on_current_screen(self, fullscreen=None):
        """Recreate notification on the current screen with specified fullscreen state"""
        # This method would be called from reinforcer.py
        # We'll return the current screen information
        # We don't implement the recreation logic here as it would need reinforcer.py changes
        pass

    def keyPressEvent(self, evt: QKeyEvent):
        """Handle key press events - dismiss on Escape"""
        if evt.key() == Qt.Key.Key_Escape:
            self.hide()
            evt.accept()
        else:
            super().keyPressEvent(evt)

    def show(self) -> None:
        # TODO: drop dependency on mw
        Notification._close_singleton()
        super().show()
        Notification._current_instance = self
        
        # Make sure we have focus to receive key events
        self.setFocus()
        
        # Only set a timer if duration is greater than 0
        if self._duration > 0:
            if is_anki_version_in_range("2.1.54"):
                Notification._current_timer = self._progress_manager.timer(
                    self._duration, Notification._close_singleton, False, parent=self.parent()
                )
            else:
                Notification._current_timer = self._progress_manager.timer(
                    self._duration, Notification._close_singleton, False
                )

    def mousePressEvent(self, evt: QMouseEvent):
        """Handle mouse press event for dragging"""
        if evt.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_position = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()
            evt.accept()
        elif evt.button() == Qt.MouseButton.RightButton and not self._fullscreen:
            # Right-click in normal mode toggles to fullscreen
            self._toggle_fullscreen()
            evt.accept()
        else:
            super().mousePressEvent(evt)

    def mouseMoveEvent(self, evt: QMouseEvent):
        """Handle mouse move event for dragging"""
        if self._dragging and evt.buttons() & Qt.MouseButton.LeftButton:
            self.move(evt.globalPosition().toPoint() - self._drag_position)
            evt.accept()
        else:
            super().mouseMoveEvent(evt)

    def mouseReleaseEvent(self, evt: QMouseEvent):
        """Handle mouse release event"""
        if self._dragging and evt.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            # Update the current screen based on new position
            self._save_current_screen()
            evt.accept()
        else:
            super().mouseReleaseEvent(evt)

    def resizeEvent(self, event: QResizeEvent) -> None:
        # true geometry is only known once resizeEvent fires
        if self._fullscreen:
            # Set fullscreen geometry
            parent = self._parent()
            self.setGeometry(0, 0, parent.width(), parent.height())
            if hasattr(self, 'web'):
                self.web.setFixedSize(QSize(parent.width(), parent.height()))
        else:
            # Standard positioning
            self._set_position()
        super().resizeEvent(event)

    def _set_position(self):
        if self._fullscreen:
            # Fullscreen doesn't need repositioning
            return
            
        align_horizontal = self._align_horizontal
        align_vertical = self._align_vertical

        parent = self._parent()

        if align_horizontal == "left":
            x: float = 0 + self._space_horizontal
        elif align_horizontal == "right":
            x = parent.width() - self.width() - self._space_horizontal
        elif align_horizontal == "center":
            x = (parent.width() - self.width()) / 2
        else:
            raise ValueError(f"Alignment value {align_horizontal} is not supported")

        if align_vertical == "top":
            y: float = 0 + self._space_vertical
        elif align_vertical == "bottom":
            y = parent.height() - self.height() - self._space_vertical
        elif align_vertical == "center":
            y = (parent.height() - self.height()) / 2
        else:
            raise ValueError(f"Alignment value {align_vertical} is not supported")

        self.move(parent.mapToGlobal(QPoint(int(x), int(y))))
        # Workaround for tooltips appearing squashed on Qt 6.6:
        self.setMinimumWidth(self.width())
        self.setMinimumHeight(self.height())
        self.update()

    def _parent(self) -> QWidget:  # pyqt stubs workaround
        return cast(QWidget, self.parent())

    @classmethod
    def _close_singleton(cls):
        if cls._current_instance:
            try:
                cls._current_instance.deleteLater()
            except:  # noqa: E722
                # already deleted as parent window closed
                pass
            cls._current_instance = None
        if cls._current_timer:
            cls._current_timer.stop()
            cls._current_timer = None
