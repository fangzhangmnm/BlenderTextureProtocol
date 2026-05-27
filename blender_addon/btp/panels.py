"""N-panel UI for BTP, registered in 3D Viewport / Image Editor / Shader Editor.

Goal: an artist who has never heard of WebRTC, ICE, SDP, or HTTP should
be able to read this panel and understand what each button does.

Two access modes:
- "On this PC" — same-machine. Easier, faster, no setup. (HTTP localhost.)
- "Another device (iPad / phone / second PC)" — manual pairing for now.
  (WebRTC DataChannel with manual offer/answer paste.)
"""
import bpy

from . import signaling, webrtc


_REMOTE_STATE_LABELS = {
    "idle": ("Not connected", 'RADIOBUT_OFF'),
    "new": ("Not connected", 'RADIOBUT_OFF'),
    "connecting": ("Connecting…", 'KEYTYPE_BREAKDOWN_VEC'),
    "connected": ("Connected", 'CHECKMARK'),
    "disconnected": ("Disconnected", 'X'),
    "failed": ("Connection failed", 'CANCEL'),
    "closed": ("Closed", 'X'),
    "unavailable": ("Unavailable", 'QUESTION'),
}


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
        row = box.row()
        row.label(text="On this PC", icon='DESKTOP')

        if prefs.enable_localhost_http:
            sub = box.row()
            sub.label(text=f"Open on port {prefs.http_port}", icon='CHECKMARK')
            box.operator("btp.toggle_local_access", text="Close", icon='X')
            box.label(text="(easiest — works with apps on this PC)", icon='BLANK1')
        else:
            sub = box.row()
            sub.label(text="Closed", icon='RADIOBUT_OFF')
            box.operator("btp.toggle_local_access", text="Open for this PC", icon='PLAY')
            box.label(text="Easier than pairing. Use this if your editor is on this PC.",
                      icon='INFO')

        port_row = box.row()
        port_row.enabled = not prefs.enable_localhost_http
        port_row.prop(prefs, "http_port", text="Port")

        # ─── Cross-device access (WebRTC) ───
        box = layout.box()
        row = box.row()
        row.label(text="Another device (iPad / phone / second PC)", icon='WORLD')

        try:
            status = webrtc.cmd_status(None)
        except Exception:
            status = {"state": "unavailable"}
        conn_state = status.get("state", "idle")
        signaling_state = status.get("signaling")

        label_text, label_icon = _REMOTE_STATE_LABELS.get(conn_state,
                                                          ("Unknown", 'QUESTION'))
        box.label(text=label_text, icon=label_icon)

        is_idle = conn_state in ("idle", "unavailable")
        pending = signaling.has_pending_offer() or signaling_state == "have-local-offer"

        col = box.column(align=True)
        if is_idle and not pending:
            col.operator("btp.start_remote_session",
                         text="Open for Another Device",
                         icon='URL')
            col.separator()
            # Future: PIN flow
            r = col.row()
            r.enabled = False
            r.operator("btp.start_remote_session",
                       text="Pair via 6-digit PIN (coming)",
                       icon='LOCKED')
        elif pending and conn_state != "connected":
            col.operator("btp.show_pending_code",
                         text="Show Connection Code Again",
                         icon='COPYDOWN')
            col.operator("btp.paste_remote_response",
                         text="Paste Response from Device",
                         icon='PASTEDOWN')
            col.separator()
            col.operator("btp.close_remote_session",
                         text="Cancel",
                         icon='X')
        else:
            col.operator("btp.close_remote_session",
                         text="Disconnect",
                         icon='X')


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
