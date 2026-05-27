bl_info = {
    "name": "Blender Texture Protocol",
    "blender": (4, 0, 0),
    "version": (0, 2, 1),
    "category": "Development",
    "author": "fangzhangmnm",
    "description": "外部贴图编辑器（WebPaint / AtlasMaker）通过 HTTP / WebRTC 与 Blender 同步纹理",
    "location": "Edit > Preferences > Add-ons > Blender Texture Protocol",
    "support": "TESTING",
}

import bpy

# Third-party deps (aiortc + crypto + ...) are declared in
# blender_manifest.toml's `wheels = [...]` field. Blender 4.2+ installs
# them into a per-extension isolated env so they don't pollute global
# Python — that's why we no longer manipulate sys.path here.
from . import bridge, http_server, operators, webrtc


class BTPPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    enable_localhost_http: bpy.props.BoolProperty(
        name="启用 localhost HTTP 服务",
        description="允许本机应用 (AtlasMaker / curl / 脚本) 通过 127.0.0.1 访问 API。仅绑定 localhost，不暴露到局域网。默认开启，让 sibling 应用直连即用；关掉这个 toggle 后只能通过 WebRTC 牵手访问 (未来功能)。",
        default=True,
        update=lambda self, ctx: _on_http_toggle(self),
    )

    http_port: bpy.props.IntProperty(
        name="HTTP 端口",
        default=18765,
        min=1024,
        max=65535,
        update=lambda self, ctx: _on_http_toggle(self),
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "enable_localhost_http")
        sub = col.row()
        sub.enabled = self.enable_localhost_http
        sub.prop(self, "http_port")
        col.separator()
        col.label(text="WebRTC 牵手 (PIN 配对) 即将加入", icon='INFO')


def _on_http_toggle(prefs):
    if prefs.enable_localhost_http:
        http_server.start(prefs.http_port)
    else:
        http_server.stop()


def register():
    bridge.start()
    operators.register()
    webrtc.register()
    bpy.utils.register_class(BTPPreferences)
    # Honor the persisted preference on startup (default-on for sibling auto-connect).
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.enable_localhost_http:
            http_server.start(prefs.http_port)
    except (KeyError, AttributeError) as e:
        print(f"[BTP] could not auto-start HTTP server: {e}", flush=True)


def unregister():
    try:
        bpy.utils.unregister_class(BTPPreferences)
    except RuntimeError:
        pass
    http_server.stop()
    webrtc.unregister()
    operators.unregister()
    bridge.stop()
