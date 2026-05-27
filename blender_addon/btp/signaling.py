"""User-facing operators driven from the N-panel.

Blender-as-offerer flow (artist-friendly labels — no jargon in UI strings):
1. `btp.start_remote_session` — Blender generates the connection code (offer)
   and shows it in a dialog with a Copy button. Auto-copied to clipboard.
2. `btp.paste_remote_response`  — User pastes the device's response (answer)
   back into Blender; the channel opens.
3. `btp.close_remote_session`   — Tear down current connection.
4. `btp.toggle_local_access`    — Start/stop the same-machine HTTP server
   (alternative to the property toggle for cleaner panel UX).

Implementation labels use plain language: "another device", "this PC",
"connection code", "device's response". WebRTC / HTTP terms appear only
in property descriptions / tooltips for users who care.
"""
import bpy

from . import webrtc


# Stash between operator invocations (start → show offer dialog).
_pending_offer_envelope: str = ""


class BTP_OT_copy_text(bpy.types.Operator):
    bl_idname = "btp.copy_text"
    bl_label = "Copy"
    bl_description = "Copy the given text to the system clipboard"
    bl_options = {'INTERNAL'}

    text: bpy.props.StringProperty()

    def execute(self, context):
        context.window_manager.clipboard = self.text
        self.report({'INFO'}, f"Copied {len(self.text)} characters")
        return {'FINISHED'}


class BTP_OT_toggle_local_access(bpy.types.Operator):
    bl_idname = "btp.toggle_local_access"
    bl_label = "Toggle Same-Machine Access"
    bl_description = "Open or close the same-PC connection (HTTP on 127.0.0.1)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        prefs.enable_localhost_http = not prefs.enable_localhost_http
        if prefs.enable_localhost_http:
            self.report({'INFO'}, "Same-machine access open")
        else:
            self.report({'INFO'}, "Same-machine access closed")
        return {'FINISHED'}


class BTP_OT_start_remote_session(bpy.types.Operator):
    bl_idname = "btp.start_remote_session"
    bl_label = "Open for Another Device"
    bl_description = "Generate a connection code another device can use to pair with this Blender"
    bl_options = {'REGISTER'}

    code: bpy.props.StringProperty(
        name="Connection code",
        description="Send this to the device you want to connect (paste into the app)",
        default="",
    )

    def invoke(self, context, event):
        global _pending_offer_envelope
        try:
            result = webrtc.cmd_create_offer(None)
        except Exception as e:
            self.report({'ERROR'}, f"Could not create session: {e}")
            return {'CANCELLED'}
        self.code = result["offer_envelope"]
        _pending_offer_envelope = self.code
        context.window_manager.clipboard = self.code
        return context.window_manager.invoke_props_dialog(self, width=720)

    def draw(self, context):
        layout = self.layout
        layout.label(text="① Send this connection code to your other device:", icon='COPYDOWN')
        layout.prop(self, "code", text="")
        row = layout.row()
        op = row.operator("btp.copy_text", text="Copy code", icon='COPYDOWN')
        op.text = self.code
        row.label(text=f"({len(self.code)} chars)")
        layout.separator()
        col = layout.column(align=True)
        col.label(text="② The device will produce a response code", icon='INFO')
        col.label(text="③ Come back here and click 'Paste Response' in the BTP panel")
        col.separator()
        col.label(text="(Code is already on your clipboard.)")

    def execute(self, context):
        context.window_manager.clipboard = self.code
        return {'FINISHED'}


class BTP_OT_show_pending_code(bpy.types.Operator):
    """Re-show the still-active offer code (in case user lost the clipboard
    before pasting it on the other device)."""
    bl_idname = "btp.show_pending_code"
    bl_label = "Show Connection Code"
    bl_description = "Re-display the current pending connection code"
    bl_options = {'REGISTER'}

    code: bpy.props.StringProperty(default="")

    def invoke(self, context, event):
        if not _pending_offer_envelope:
            self.report({'ERROR'}, "No active pending session")
            return {'CANCELLED'}
        self.code = _pending_offer_envelope
        context.window_manager.clipboard = self.code
        return context.window_manager.invoke_props_dialog(self, width=720)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Connection code (re-copied to clipboard):", icon='INFO')
        layout.prop(self, "code", text="")
        op = layout.operator("btp.copy_text", text="Copy code", icon='COPYDOWN')
        op.text = self.code

    def execute(self, context):
        return {'FINISHED'}


class BTP_OT_paste_remote_response(bpy.types.Operator):
    bl_idname = "btp.paste_remote_response"
    bl_label = "Paste Response from Device"
    bl_description = "Paste the response code the device produced after entering your connection code"
    bl_options = {'REGISTER'}

    response: bpy.props.StringProperty(
        name="Device's response",
        description="Paste the response code you got from the other device",
        default="",
    )

    def invoke(self, context, event):
        cb = context.window_manager.clipboard
        if cb and (cb.startswith("BTP1:") or cb.startswith("v=0")):
            self.response = cb
        return context.window_manager.invoke_props_dialog(self, width=720)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Paste the response code from the other device:", icon='PASTEDOWN')
        layout.prop(self, "response", text="")
        layout.label(text="(Auto-filled if your clipboard already contains the response.)",
                     icon='INFO')

    def execute(self, context):
        global _pending_offer_envelope
        s = self.response.strip()
        if not s:
            self.report({'ERROR'}, "Response code is empty")
            return {'CANCELLED'}
        if not (s.startswith("BTP1:") or s.startswith("v=0")):
            self.report({'ERROR'}, "Doesn't look like a response code")
            return {'CANCELLED'}
        try:
            webrtc.cmd_set_remote_answer({"sdp": s})
        except Exception as e:
            self.report({'ERROR'}, f"Could not apply response: {e}")
            return {'CANCELLED'}
        _pending_offer_envelope = ""
        self.report({'INFO'}, "Response accepted. The device should be connected shortly.")
        return {'FINISHED'}


class BTP_OT_close_remote_session(bpy.types.Operator):
    bl_idname = "btp.close_remote_session"
    bl_label = "Disconnect Device"
    bl_description = "Close the current cross-device connection"
    bl_options = {'REGISTER'}

    def execute(self, context):
        global _pending_offer_envelope
        try:
            webrtc.cmd_close(None)
        except Exception as e:
            self.report({'ERROR'}, f"Could not close: {e}")
            return {'CANCELLED'}
        _pending_offer_envelope = ""
        self.report({'INFO'}, "Device disconnected")
        return {'FINISHED'}


def has_pending_offer() -> bool:
    """For panels.py to choose between 'Open' vs 'Paste Response' buttons."""
    return bool(_pending_offer_envelope)


_CLASSES = (
    BTP_OT_copy_text,
    BTP_OT_toggle_local_access,
    BTP_OT_start_remote_session,
    BTP_OT_show_pending_code,
    BTP_OT_paste_remote_response,
    BTP_OT_close_remote_session,
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
