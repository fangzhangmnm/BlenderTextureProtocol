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


_CLASSES = (
    BTP_OT_create_texture,
    BTP_OT_update_texture,
    BTP_OT_rename_texture,
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
