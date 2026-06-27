"""
v1 API handlers. All run on Blender's main thread (via bridge).

Endpoints:
    GET    /v1/scene
    GET    /v1/textures
    GET    /v1/textures/{name}
    GET    /v1/textures/{name}/data
    PUT    /v1/textures/{name}/data
    POST   /v1/textures              (header X-BTP-Name: <name>)
    POST   /v1/textures/{name}/rename
    GET    /v1/selection
    POST   /v1/exec
    GET    /v1/references
    GET    /v1/references/{name}
    PUT    /v1/references/{name}    (upsert: { image, placement, opacity })
    DELETE /v1/references/{name}

ID is the image's `name` (Blender enforces uniqueness with .001 suffix).
URL component must be percent-encoded. Rename uses an explicit endpoint.
"""
import json
import os
import re
import tempfile
from urllib.parse import parse_qs, unquote, urlparse

import bpy


JSON_CT = "application/json; charset=utf-8"


def _call_with_ui_context(callable_fn, *args, **kwargs):
    """
    Run callable_fn() with a temp_override that gives it a window+screen
    context. Required because bpy.app.timers callbacks (which is how the
    bridge runs handlers on main thread) don't carry a full UI context,
    and bpy.ops.* + undo push silently skip without it.
    """
    wm = bpy.context.window_manager
    if wm and wm.windows:
        win = wm.windows[0]
        try:
            with bpy.context.temp_override(window=win, screen=win.screen):
                return callable_fn(*args, **kwargs)
        except Exception:
            raise
    return callable_fn(*args, **kwargs)


def _push_undo(message):
    """Explicit undo checkpoint, belt-and-suspenders on top of operator's
    `bl_options={'UNDO'}` push (which doesn't always fire from timer
    context)."""
    def _do():
        try:
            bpy.ops.ed.undo_push(message=message)
        except Exception as e:
            print(f"[BTP] undo_push failed: {e}", flush=True)
    _call_with_ui_context(_do)


_CONTENT_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "JPEG2000": "image/jp2",
    "TARGA": "image/x-tga",
    "TARGA_RAW": "image/x-tga",
    "TIFF": "image/tiff",
    "BMP": "image/bmp",
    "OPEN_EXR": "image/x-exr",
    "OPEN_EXR_MULTILAYER": "image/x-exr",
    "HDR": "image/vnd.radiance",
    "WEBP": "image/webp",
}


def handle(method, path, body, headers):
    parsed = urlparse(path)
    path_only = parsed.path
    query = parse_qs(parsed.query)
    headers = _normalize_headers(headers)
    for route_method, pattern, fn in _ROUTES:
        if route_method != method:
            continue
        match = re.match(pattern, path_only)
        if match:
            args = [unquote(g) for g in match.groups()]
            return fn(*args, body=body, query=query, headers=headers)
    return _error(404, "not_found", f"No route for {method} {path_only}")


def _normalize_headers(headers):
    if not headers:
        return {}
    return {k.lower(): v for k, v in headers.items()}


def _json(obj, status=200, extra_headers=None):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    h = {"Content-Type": JSON_CT}
    if extra_headers:
        h.update(extra_headers)
    return (status, h, body)


def _error(status, code, message, details=None):
    err = {"error": {"code": code, "message": message}}
    if details:
        err["error"]["details"] = details
    return _json(err, status=status)


def _is_user_image(img):
    return img.source not in {"VIEWER", "MOVIE"}


def _texture_metadata(img):
    return {
        "name": img.name,
        "width": img.size[0],
        "height": img.size[1],
        "channels": img.channels,
        "color_space": img.colorspace_settings.name,
        "is_float": img.is_float,
        "alpha_mode": img.alpha_mode,
        "source": img.source,
        "file_format": img.file_format,
        "is_dirty": img.is_dirty,
        "packed": img.packed_file is not None,
    }


# ---------- handlers ----------

def handle_scene(body=None, query=None, headers=None):
    ctx = bpy.context
    active = getattr(ctx, "active_object", None)
    return _json({
        "blend_filepath": bpy.data.filepath,
        "unit": ctx.scene.unit_settings.system if ctx.scene else None,
        "active_object_name": active.name if active else None,
    })


def handle_list_textures(body=None, query=None, headers=None):
    items = [_texture_metadata(img) for img in bpy.data.images if _is_user_image(img)]
    items.sort(key=lambda x: x["name"])
    return _json(items)


def handle_get_texture(name, body=None, query=None, headers=None):
    img = bpy.data.images.get(name)
    if img is None or not _is_user_image(img):
        return _error(404, "texture_not_found", f"No image named '{name}'")
    return _json(_texture_metadata(img))


def handle_get_texture_data(name, body=None, query=None, headers=None):
    img = bpy.data.images.get(name)
    if img is None or not _is_user_image(img):
        return _error(404, "texture_not_found", f"No image named '{name}'")
    if img.packed_file is None:
        try:
            img.pack()
        except Exception as e:
            return _error(500, "pack_failed", f"Could not pack image: {e}")
    data = bytes(img.packed_file.data)
    ct = _CONTENT_TYPES.get(img.file_format, "application/octet-stream")
    return (200, {"Content-Type": ct}, data)


def handle_put_texture_data(name, body=None, query=None, headers=None):
    img = bpy.data.images.get(name)
    if img is None or not _is_user_image(img):
        return _error(404, "texture_not_found", f"No image named '{name}'")
    if not body:
        return _error(400, "empty_body", "PUT body is required")
    ct = (headers or {}).get("content-type", "image/png").lower()
    if not ct.startswith("image/png"):
        return _error(415, "unsupported_media_type",
                      "v1 only accepts image/png on PUT",
                      details={"received": ct})
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(body)
    tmp.close()
    try:
        result = _call_with_ui_context(
            bpy.ops.btp.update_texture, name=name, png_path=tmp.name)
        if 'FINISHED' not in result:
            return _error(500, "operator_failed", f"update_texture returned {result}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    _push_undo(f"BTP: update {name}")
    return _json(_texture_metadata(img))


def handle_create_texture(body=None, query=None, headers=None):
    name = (headers or {}).get("x-btp-name")
    if not name:
        return _error(400, "missing_name",
                      "X-BTP-Name header is required to name the new image")
    if name in bpy.data.images:
        return _error(409, "name_exists", f"Image '{name}' already exists")
    if not body:
        return _error(400, "empty_body", "POST body is required")
    ct = (headers or {}).get("content-type", "image/png").lower()
    if not ct.startswith("image/png"):
        return _error(415, "unsupported_media_type",
                      "v1 only accepts image/png on POST",
                      details={"received": ct})
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(body)
    tmp.close()
    try:
        result = _call_with_ui_context(
            bpy.ops.btp.create_texture, name=name, png_path=tmp.name)
        if 'FINISHED' not in result:
            return _error(500, "operator_failed", f"create_texture returned {result}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    img = bpy.data.images.get(name)
    if img is None:
        return _error(500, "create_failed", "Operator finished but image not found")
    _push_undo(f"BTP: create {name}")
    return _json(_texture_metadata(img), status=201)


def handle_rename_texture(name, body=None, query=None, headers=None):
    img = bpy.data.images.get(name)
    if img is None or not _is_user_image(img):
        return _error(404, "texture_not_found", f"No image named '{name}'")
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except json.JSONDecodeError:
        return _error(400, "bad_json", "Body must be JSON")
    new_name = payload.get("new_name")
    if not new_name:
        return _error(400, "missing_new_name", "Body must contain new_name")
    if new_name == name:
        return _json(_texture_metadata(img))
    if new_name in bpy.data.images:
        return _error(409, "name_exists", f"Image '{new_name}' already exists")
    result = _call_with_ui_context(
        bpy.ops.btp.rename_texture, name=name, new_name=new_name)
    if 'FINISHED' not in result:
        return _error(500, "operator_failed", f"rename_texture returned {result}")
    _push_undo(f"BTP: rename {name} -> {new_name}")
    return _json(_texture_metadata(img))


def handle_selection(body=None, query=None, headers=None):
    return _json({
        "texture": _current_selected_texture_name(),
        "object": None,
        "mesh": None,
    })


def handle_exec(body=None, query=None, headers=None):
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except json.JSONDecodeError:
        return _error(400, "bad_json", "Body must be JSON")
    command = payload.get("command")
    if not command:
        return _error(400, "missing_command", "Body must contain command")
    handler = _EXEC_REGISTRY.get(command)
    if handler is None:
        return _error(404, "unknown_command",
                      f"No exec command registered: '{command}'",
                      details={"registered": sorted(_EXEC_REGISTRY.keys())})
    params = payload.get("params") or {}
    try:
        result = handler(params)
    except Exception as e:
        return _error(500, "exec_failed", f"{command} raised: {e}")
    if isinstance(result, tuple) and len(result) == 3:
        return result
    return _json(result)


_EXEC_REGISTRY = {}


def register_exec(command, handler):
    _EXEC_REGISTRY[command] = handler


# ---------- references (ADR-0001) ----------
# A reference = metadata-only Image Empty that links a texture by name. Pixels
# live in /v1/textures (sent first). Identity = custom prop btp_ref. Upsert by
# name. See operators.BTP_OT_upsert_reference.

def _reference_metadata(obj):
    img = obj.data
    color = list(obj.color) if hasattr(obj, "color") else [1, 1, 1, 1]
    return {
        "name": obj.get("btp_ref"),
        "image": img.name if img else None,
        "object": obj.name,
        "location": list(obj.location),
        "rotation": list(obj.rotation_euler),
        "opacity": color[3] if len(color) >= 4 else 1.0,
    }


def _iter_reference_empties():
    return [o for o in bpy.data.objects if o.type == "EMPTY" and o.get("btp_ref")]


def handle_list_references(body=None, query=None, headers=None):
    items = [_reference_metadata(o) for o in _iter_reference_empties()]
    items.sort(key=lambda x: x["name"] or "")
    return _json(items)


def handle_get_reference(name, body=None, query=None, headers=None):
    for o in _iter_reference_empties():
        if o.get("btp_ref") == name:
            return _json(_reference_metadata(o))
    return _error(404, "reference_not_found", f"No reference named '{name}'")


def handle_put_reference(name, body=None, query=None, headers=None):
    """Upsert by name: create the reference if absent, else relink + re-place."""
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except json.JSONDecodeError:
        return _error(400, "bad_json", "Body must be JSON")
    image = payload.get("image")
    if not image:
        return _error(400, "missing_image", "Body must contain image (a texture name)")
    if image not in bpy.data.images:
        return _error(404, "texture_not_found",
                      f"No image named '{image}' — send the texture first")
    placement = payload.get("placement") or {}
    opacity = payload.get("opacity", 1.0)
    result = _call_with_ui_context(
        bpy.ops.btp.upsert_reference,
        name=name, image=image,
        placement_json=json.dumps(placement), opacity=float(opacity))
    if 'FINISHED' not in result:
        return _error(500, "operator_failed", f"upsert_reference returned {result}")
    _push_undo(f"BTP: reference {name}")
    for o in _iter_reference_empties():
        if o.get("btp_ref") == name:
            return _json(_reference_metadata(o))
    return _error(500, "upsert_failed", "Operator finished but reference not found")


def handle_delete_reference(name, body=None, query=None, headers=None):
    if not any(o.get("btp_ref") == name for o in _iter_reference_empties()):
        return _error(404, "reference_not_found", f"No reference named '{name}'")
    result = _call_with_ui_context(bpy.ops.btp.delete_reference, name=name)
    if 'FINISHED' not in result:
        return _error(500, "operator_failed", f"delete_reference returned {result}")
    _push_undo(f"BTP: delete reference {name}")
    return _json({"deleted": name})


# ---------- helpers ----------

def _current_selected_texture_name():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "IMAGE_EDITOR":
                space = area.spaces.active
                if space and space.image and _is_user_image(space.image):
                    return space.image.name
    obj = getattr(bpy.context, "active_object", None)
    if obj and obj.active_material and obj.active_material.use_nodes:
        nt = obj.active_material.node_tree
        node = nt.nodes.active
        if node and node.type == "TEX_IMAGE" and node.image and _is_user_image(node.image):
            return node.image.name
    return None


_ROUTES = [
    ("GET",  r"^/v1/scene$",                          handle_scene),
    ("GET",  r"^/v1/textures$",                       handle_list_textures),
    ("GET",  r"^/v1/textures/([^/]+)$",               handle_get_texture),
    ("GET",  r"^/v1/textures/([^/]+)/data$",          handle_get_texture_data),
    ("PUT",  r"^/v1/textures/([^/]+)/data$",          handle_put_texture_data),
    ("POST", r"^/v1/textures$",                       handle_create_texture),
    ("POST", r"^/v1/textures/([^/]+)/rename$",        handle_rename_texture),
    ("GET",  r"^/v1/selection$",                      handle_selection),
    ("POST", r"^/v1/exec$",                           handle_exec),
    ("GET",    r"^/v1/references$",                   handle_list_references),
    ("GET",    r"^/v1/references/([^/]+)$",           handle_get_reference),
    ("PUT",    r"^/v1/references/([^/]+)$",           handle_put_reference),
    ("DELETE", r"^/v1/references/([^/]+)$",           handle_delete_reference),
]
