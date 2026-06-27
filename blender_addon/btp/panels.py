"""N-panel UI for BTP, registered in 3D Viewport / Image Editor / Shader Editor.

Goal: an artist who has never heard of HTTP should be able to read this panel
and understand what each button does.

Access model:
- "On this PC" — same-machine, localhost HTTP. Open it here (per-session consent).
- Another device (iPad / phone / second PC) — point the editor at an HTTPS URL
  that reaches this server; easiest is `tailscale serve` (see the BTP README).
  No pairing UI here: the editor just needs a reachable URL.
"""
import bpy


class _BTP_PT_panel_base:
    bl_label = "BTP"
    bl_category = "BTP"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[__package__].preferences

        layout.label(text="Let external editors read/write textures", icon='OUTLINER_OB_IMAGE')

        # ─── Same-machine access (HTTP localhost) ───
        box = layout.box()
        box.row().label(text="On this PC", icon='DESKTOP')

        if prefs.enable_localhost_http:
            box.row().label(text=f"Open on port {prefs.http_port}", icon='CHECKMARK')
            box.operator("btp.toggle_local_access", text="Close", icon='X')
            box.label(text="(easiest — works with apps on this PC)", icon='BLANK1')
        else:
            box.row().label(text="Closed", icon='RADIOBUT_OFF')
            box.operator("btp.toggle_local_access", text="Open for this PC", icon='PLAY')
            box.label(text="Open this when an editor on this PC needs to connect.", icon='INFO')

        port_row = box.row()
        port_row.enabled = not prefs.enable_localhost_http
        port_row.prop(prefs, "http_port", text="Port")

        # ─── Another device (direct HTTPS, no pairing) ───
        box = layout.box()
        box.row().label(text="Another device (iPad / phone / second PC)", icon='WORLD')
        box.label(text="Point the editor at an HTTPS URL that reaches this PC.", icon='URL')
        box.label(text="Easiest: run  tailscale serve  (see BTP README).", icon='BLANK1')


class BTP_PT_panel_view3d(_BTP_PT_panel_base, bpy.types.Panel):
    bl_idname = "BTP_PT_panel_view3d"
    bl_space_type = "VIEW_3D"


class BTP_PT_panel_image(_BTP_PT_panel_base, bpy.types.Panel):
    bl_idname = "BTP_PT_panel_image"
    bl_space_type = "IMAGE_EDITOR"


class BTP_PT_panel_node(_BTP_PT_panel_base, bpy.types.Panel):
    bl_idname = "BTP_PT_panel_node"
    bl_space_type = "NODE_EDITOR"


_CLASSES = (
    BTP_PT_panel_view3d,
    BTP_PT_panel_image,
    BTP_PT_panel_node,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
