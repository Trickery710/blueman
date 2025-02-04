from gettext import gettext as _
from typing import Optional, Tuple, List

from gi.repository import GObject, GLib, Gio
from blueman.Functions import launch
from blueman.main.PluginManager import PluginManager
from blueman.plugins.AppletPlugin import AppletPlugin


class StatusIconImplementationProvider:
    def on_query_status_icon_implementation(self) -> Tuple[str, int]:
        return "GtkStatusIcon", 0


class StatusIconVisibilityHandler:
    def on_query_force_status_icon_visibility(self) -> bool:
        return False


class StatusIconProvider:
    def on_status_icon_query_icon(self) -> Optional[str]:
        return None


class StatusIcon(AppletPlugin, GObject.GObject):
    __icon__ = "bluetooth-symbolic"
    __depends__ = ["StandardItems", "Menu"]

    visible = None

    visibility_timeout: Optional[int] = None

    _implementations = None

    def on_load(self) -> None:
        GObject.GObject.__init__(self)
        self._tooltip_title = _("Bluetooth Enabled")
        self._tooltip_text = ""

        self.general_config = Gio.Settings(schema_id="org.blueman.general")
        self.general_config.connect("changed::symbolic-status-icons", self.on_symbolic_config_change)

        self.query_visibility(emit=False)

        self.parent.Plugins.connect('plugin-loaded', self._on_plugins_changed)
        self.parent.Plugins.connect('plugin-unloaded', self._on_plugins_changed)

        self._add_dbus_method("GetVisibility", (), "b", lambda: self.visible)
        self._add_dbus_signal("VisibilityChanged", "b")
        self._add_dbus_signal("ToolTipTitleChanged", "s")
        self._add_dbus_signal("ToolTipTextChanged", "s")
        self._add_dbus_method("GetToolTipTitle", (), "s", lambda: self._tooltip_title)
        self._add_dbus_method("GetToolTipText", (), "s", lambda: self._tooltip_text)
        self._add_dbus_signal("IconNameChanged", "s")
        self._add_dbus_method("GetStatusIconImplementations", (), "as", self._get_status_icon_implementations)
        self._add_dbus_method("GetIconName", (), "s", self._get_icon_name)
        self._add_dbus_method("Activate", (), "", self.parent.Plugins.StandardItems.on_devices)

    def query_visibility(self, delay_hiding: bool = False, emit: bool = True) -> None:
        if self.parent.Manager.get_adapters() or \
           any(plugin.on_query_force_status_icon_visibility()
               for plugin in self.parent.Plugins.get_loaded_plugins(StatusIconVisibilityHandler)):
            self.set_visible(True, emit)
        elif not self.visibility_timeout:
            if delay_hiding:
                self.visibility_timeout = GLib.timeout_add(2500, self.on_visibility_timeout)
            else:
                self.set_visible(False, emit)

    def on_visibility_timeout(self) -> bool:
        assert self.visibility_timeout is not None
        GLib.source_remove(self.visibility_timeout)
        self.visibility_timeout = None
        self.query_visibility()
        return False

    def set_visible(self, visible: bool, emit: bool) -> None:
        self.visible = visible
        if emit:
            self._emit_dbus_signal("VisibilityChanged", visible)

    def set_tooltip_title(self, title: str) -> None:
        self._tooltip_title = title
        self._emit_dbus_signal("ToolTipTitleChanged", title)

    def set_tooltip_text(self, text: Optional[str]) -> None:
        self._tooltip_text = "" if text is None else text
        self._emit_dbus_signal("ToolTipTextChanged", self._tooltip_text)

    def on_symbolic_config_change(self, settings: Gio.Settings, key: str) -> None:
        self.icon_should_change()

    def icon_should_change(self) -> None:
        self._emit_dbus_signal("IconNameChanged", self._get_icon_name())
        self.query_visibility()

    def on_adapter_added(self, _path: str) -> None:
        self.query_visibility()

    def on_adapter_removed(self, _path: str) -> None:
        self.query_visibility()

    def on_manager_state_changed(self, state: bool) -> None:
        self.query_visibility()
        if state:
            launch('blueman-tray', icon_name='blueman', sn=False)

    def _on_plugins_changed(self, _plugins: PluginManager, _name: str) -> None:
        implementations = self._get_status_icon_implementations()
        if not self._implementations or self._implementations != implementations:
            self._implementations = implementations

        if self.parent.manager_state:
            launch('blueman-tray', icon_name='blueman', sn=False)

    def _get_status_icon_implementations(self) -> List[str]:
        return [implementation for implementation, _ in sorted(
            (plugin.on_query_status_icon_implementation()
             for plugin in self.parent.Plugins.get_loaded_plugins(StatusIconImplementationProvider)),
            key=lambda implementation_priority: implementation_priority[1],
            reverse=True
        )] + ["GtkStatusIcon"]

    def _get_icon_name(self) -> str:
        # default icon name
        name = "blueman-tray"
        for plugin in self.parent.Plugins.get_loaded_plugins(StatusIconProvider):
            icon = plugin.on_status_icon_query_icon()
            if icon is not None:
                # status icon
                name = icon

        # depending on configuration, ensure fullcolor icons..
        name = name.replace("-symbolic", "")
        if self.general_config.get_boolean("symbolic-status-icons"):
            # or symbolic
            name = f"{name}-symbolic"

        return name
