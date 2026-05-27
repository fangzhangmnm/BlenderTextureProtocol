bl_info = {
    "name": "Blender Texture Protocol",
    "blender": (4, 0, 0),
    "version": (0, 3, 0),
    "category": "Development",
    "author": "fangzhangmnm",
    "description": "Let external editors (WebPaint / AtlasMaker) read & write textures in Blender without import/export",
    "location": "View3D / Image Editor / Shader Editor > N-panel > BTP",
    "support": "TESTING",
}

import bpy

# Third-party deps (aiortc + crypto + ...) are declared in
# blender_manifest.toml's `wheels = [...]` field. Blender 4.2+ installs
# them into a per-extension isolated env so they don't pollute global
# Python — that's why we no longer manipulate sys.path here.
from . import bridge, http_server, operators, panels, signaling, webrtc


class BTPPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    enable_localhost_http: bpy.props.BoolProperty(
        name="Same-machine access (HTTP on 127.0.0.1)",
        description=(
            "When on, external editors running on this same PC can read/write "
            "Blender textures via a local HTTP server. Bound to localhost only — "
            "not exposed to LAN. Off by default; turn it on (here, or from the "
            "BTP N-panel) when an editor on this PC needs to connect."
        ),
        default=False,
        update=lambda self, ctx: _on_http_toggle(self),
    )

    http_port: bpy.props.IntProperty(
        name="Port",
        description="Port to bind on 127.0.0.1 (only editable while same-machine access is closed)",
        default=18765,
        min=1024,
        max=65535,
        update=lambda self, ctx: _on_http_toggle(self),
    )

    def draw(self, context):
        layout = self.layout
        layout.label(
            text="All session controls live in the 'BTP' tab of the N-panel in 3D Viewport / Image Editor / Shader Editor.",
            icon='INFO',
        )
        col = layout.column()
        col.prop(self, "enable_localhost_http")
        sub = col.row()
        sub.enabled = not self.enable_localhost_http
        sub.prop(self, "http_port")


def _on_http_toggle(prefs):
    if prefs.enable_localhost_http:
        http_server.start(prefs.http_port)
    else:
        http_server.stop()


def register():
    bridge.start()
    operators.register()
    signaling.register()
    panels.register()
    webrtc.register()
    bpy.utils.register_class(BTPPreferences)
    # Default-off now (consent on each session) — only start if user previously
    # turned it on and Blender restored the saved value as True.
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.enable_localhost_http:
            http_server.start(prefs.http_port)
    except (KeyError, AttributeError) as e:
        print(f"[BTP] could not check HTTP preference at register: {e}", flush=True)


def unregister():
    try:
        bpy.utils.unregister_class(BTPPreferences)
    except RuntimeError:
        pass
    http_server.stop()
    webrtc.unregister()
    panels.unregister()
    signaling.unregister()
    operators.unregister()
    bridge.stop()
