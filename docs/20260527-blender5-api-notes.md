# Blender 4.x → 5.x API 变化笔记 (针对 BTP 项目)

写于 2026-05-26，对应 slice 0 代码 audit。AI 笔记，给未来的我自己。

## 高置信度变化（必修）

### 1. Extension 格式取代 legacy add-on

Blender 4.2 (2024 Jul) 引入 Extensions Platform：
- 新格式: addon 目录里**必须**有 `blender_manifest.toml`，metadata 写在 toml 里
- 旧格式 `bl_info` 仍可识别但属于 "legacy add-on"，UI 上归到不同 tab
- Blender 5.x 进一步推 extension 格式

**Blender 4.2 manifest 必需字段** (5.x 应该向后兼容):
```
schema_version, id, version, name, tagline,
maintainer, type, blender_version_min, license
```

**修复**: 加 `blender_manifest.toml`，保留 `bl_info` 双保险 (装在老 Blender 上也能用)。

## 中置信度变化（可能影响）

### 2. Color space 名字向 OCIO 标准对齐

Blender 4.x 内部已经在改：
- `Linear` 可能在 5.x 是 `Linear Rec.709` / `Linear sRGB` 之一
- `Filmic Log` 可能动
- `Non-Color` / `sRGB` 通常不变

**对协议影响**: PWA 端应把 `color_space` 当 opaque string，不要硬编码 enum 比对。我们 metadata 是 pass-through，**代码无需改**。docs 写明这条契约。

### 3. `view_layer.objects.active` vs `active_object`

- `bpy.context.active_object` 更推荐 (4.x 起)
- `bpy.context.view_layer.objects.active` 仍工作但啰嗦
- 5.x 应该都还能用

**修复**: 改成 `context.active_object`，简洁，无功能差异。

## 低置信度 / 不确定

### 4. Blender 5.0 具体改动

我的知识截止 2026-01。5.0 应已发布但具体改动我无法逐项核实。已知方向:
- Vulkan 默认后端 → 对我们 Python 插件无影响 (我们不碰 GL)
- Geometry Nodes 提速 → 无关
- 不确定 `bl_info` 是否在某次 5.x 彻底废弃 → 加 manifest 是 belt-and-suspenders

### 5. `bpy.app.timers` 行为
4.x 稳定。5.x 应不变。若 `persistent=True` 跨文件加载行为变了我不知道。**Bridge 模块的核心机制依赖这个**，需要实际测。

### 6. Image API
`image.pack()` / `unpack()` / `reload()` / `packed_file.data` 应该都稳定。但 5.x Vulkan 后端是否对内部 image storage 改了（比如要重新 upload 到 GPU）我不确定。**PUT 测试时若 viewport 不刷新，可能要 `image.update()` 或 `image.gl_touch()`**。

## 修复 checklist
- [x] 加 `blender_manifest.toml`
- [x] `context.view_layer.objects.active` → `context.active_object`
- [ ] 实际在 Blender 5 里装+测 (user 跑)

## User 验证关键点
1. 装插件: Edit > Preferences > 是 "Add-ons" tab 还是 "Get Extensions" tab？
2. 启用后控制台是否打印 `[BTP] localhost HTTP listening on 127.0.0.1:8765`
3. 9 个 curl endpoint 是否都通
4. **PUT 后 Blender viewport / Image Editor 是否真的刷新**（5.x Vulkan 重渲染机制变了的话这里最容易翻车）

## 已知不会自动测出来的坑
- `bl_info` deprecation warning 不影响功能但会刷 console，可忽略
- 如果 Preferences 里 toggle HTTP 后没启动，看 console 有没有报错；可能是 thread / queue 注册时机问题
