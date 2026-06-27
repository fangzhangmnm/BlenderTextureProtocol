"""
Internal Operators that wrap mutating API actions.

Blender pushes a memfile undo snapshot when an Operator with
`bl_options = {'UNDO'}` returns {'FINISHED'}. This is more reliable than
calling `bpy.ops.ed.undo_push()` manually, especially for actions that add /
remove datablocks (which manual undo_push sometimes misses depending on the
calling context — e.g. timer callbacks).

Operators are flagged 'INTERNAL' so they don't appear in the operator search
list. They take only string properties so they can be invoked from
`bpy.ops.btp.*(name=..., png_path=...)` from the API handlers (which run on
the main thread via bridge.dispatch_to_main).
"""
import json
import math

import bpy


class BTP_OT_create_texture(bpy.types.Operator):
    bl_idname = "btp.create_texture"
    bl_label = "BTP: Create Texture"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty()
    png_path: bpy.props.StringProperty()

    def execute(self, context):
        try:
            img = bpy.data.images.load(self.png_path)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load image: {e}")
            return {'CANCELLED'}
        img.name = self.name
        img.file_format = "PNG"
        img.pack()
        img.filepath = ""
        img.update_tag()
        return {'FINISHED'}


class BTP_OT_update_texture(bpy.types.Operator):
    bl_idname = "btp.update_texture"
    bl_label = "BTP: Update Texture"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty()
    png_path: bpy.props.StringProperty()

    def execute(self, context):
        img = bpy.data.images.get(self.name)
        if img is None:
            self.report({'ERROR'}, f"Image not found: {self.name}")
            return {'CANCELLED'}
        try:
            img.source = "FILE"
            img.filepath = self.png_path
            img.reload()
            img.file_format = "PNG"
            img.pack()
            img.filepath = ""
            img.update_tag()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to update {self.name}: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class BTP_OT_rename_texture(bpy.types.Operator):
    bl_idname = "btp.rename_texture"
    bl_label = "BTP: Rename Texture"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty()
    new_name: bpy.props.StringProperty()

    def execute(self, context):
        img = bpy.data.images.get(self.name)
        if img is None:
            self.report({'ERROR'}, f"Image not found: {self.name}")
            return {'CANCELLED'}
        if self.new_name in bpy.data.images:
            self.report({'ERROR'}, f"Image already exists: {self.new_name}")
            return {'CANCELLED'}
        img.name = self.new_name
        return {'FINISHED'}


# ── Reference images (ADR-0001) ─────────────────────────────────────────────
# A reference is a metadata-only placement: an Image Empty that *links* a texture
# by name. Pixels live in bpy.data.images (sent via the texture endpoints); this
# operator only places/updates the empty. Identity = the custom prop btp_ref,
# so we find-and-update our own object without clobbering the user's namespace.
#
# Image-empty API: the displayed picture IS obj.data; empty_display_size sets the
# longest edge (aspect comes from the image automatically — ADR's "longest edge=1"
# maps straight to display_size=1 and stays stable when the image is relinked).

# Best-effort orthographic orientations (radians). A default image empty lies in
# its local XY plane (normal +Z). NOTE: verify these in Blender — untested angles.
_VIEW_ROT = {
    "top":    (0.0,          0.0, 0.0),
    "bottom": (math.pi,      0.0, 0.0),
    "front":  (math.pi / 2,  0.0, 0.0),
    "back":   (math.pi / 2,  0.0, math.pi),
    "right":  (math.pi / 2,  0.0, math.pi / 2),
    "left":   (math.pi / 2,  0.0, -math.pi / 2),
    "camera": (math.pi / 2,  0.0, 0.0),   # TODO: face active camera; falls back to front
}


def find_reference_empty(name):
    for obj in bpy.data.objects:
        if obj.type == 'EMPTY' and obj.get("btp_ref") == name:
            return obj
    return None


class BTP_OT_upsert_reference(bpy.types.Operator):
    bl_idname = "btp.upsert_reference"
    bl_label = "BTP: Upsert Reference Image"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty()
    image: bpy.props.StringProperty()
    placement_json: bpy.props.StringProperty()
    opacity: bpy.props.FloatProperty(default=1.0)

    def execute(self, context):
        img = bpy.data.images.get(self.image)
        if img is None:
            self.report({'ERROR'}, f"Image not found: {self.image}")
            return {'CANCELLED'}
        obj = find_reference_empty(self.name)
        if obj is None:
            obj = bpy.data.objects.new(self.name, None)
            obj["btp_ref"] = self.name
            context.scene.collection.objects.link(obj)
        obj.empty_display_type = 'IMAGE'
        obj.data = img                       # relink → aspect follows the new image
        obj.empty_display_size = 1.0         # ADR-0001: longest edge = 1
        try:
            obj.use_empty_image_alpha = True
            obj.color[3] = max(0.0, min(1.0, self.opacity))
        except Exception:
            pass
        try:
            placement = json.loads(self.placement_json) if self.placement_json else {}
        except Exception:
            placement = {}
        self._apply_placement(obj, placement)
        obj.update_tag()
        return {'FINISHED'}

    def _apply_placement(self, obj, placement):
        if placement.get("mode") == "transform":
            loc = (placement.get("location") or [0, 0, 0])[:3]
            rot = (placement.get("rotation") or [0, 0, 0])[:3]
            obj.location = loc
            obj.rotation_euler = rot
            scl = placement.get("scale")
            if scl:
                obj.scale = scl[:3]
        else:  # "view" (default): axis-aligned plane at origin
            view = placement.get("view", "front")
            obj.location = (0.0, 0.0, 0.0)
            obj.rotation_euler = _VIEW_ROT.get(view, _VIEW_ROT["front"])


class BTP_OT_delete_reference(bpy.types.Operator):
    bl_idname = "btp.delete_reference"
    bl_label = "BTP: Delete Reference Image"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty()

    def execute(self, context):
        obj = find_reference_empty(self.name)
        if obj is None:
            return {'CANCELLED'}
        bpy.data.objects.remove(obj, do_unlink=True)
        return {'FINISHED'}


# ── Same-machine access toggle (moved here when the WebRTC signaling module was
#    removed; it's a plain localhost-HTTP control, no WebRTC) ─────────────────
class BTP_OT_toggle_local_access(bpy.types.Operator):
    bl_idname = "btp.toggle_local_access"
    bl_label = "Toggle Same-Machine Access"
    bl_description = "Open or close the same-PC connection (HTTP on 127.0.0.1)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        prefs.enable_localhost_http = not prefs.enable_localhost_http
        msg = "Same-machine access open" if prefs.enable_localhost_http else "Same-machine access closed"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


_CLASSES = (
    BTP_OT_create_texture,
    BTP_OT_update_texture,
    BTP_OT_rename_texture,
    BTP_OT_upsert_reference,
    BTP_OT_delete_reference,
    BTP_OT_toggle_local_access,
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
