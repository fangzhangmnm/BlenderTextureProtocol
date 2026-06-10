# BlenderTextureProtocol / BTP（家族总规则见上级 CLAUDE.md）

Blender 5 插件：localhost HTTP + WebRTC DataChannel 暴露场景/贴图/选中，让 iPad 上的 WebPaint/AtlasMaker 直推直拉贴图。**UI 纯英文**。

- 交付物：协议 spec + vendored `btp.js` 客户端包（兄弟 app 各自 vendor）；**协议版本严格**。
- **设计立场（别推翻）**：name-as-id 可重绑；upload/download 语义就是覆盖，**无冲突解决 by design**（"做了反而是给用户添堵"）；abandonware-proof > 可升级性；不污染 namespace；开任何端口前必须 per-session 用户 consent。redo 不灵很敏感——丢用户数据是红线。
- 已知死路：Blender 的 image pixel undo 从 Python 根本做不了（issue #127872 / PR #127895）——别再试，等上游。
- Roadmap（聊天里有、doc 里没有）：数字 PIN 配对；牵手服务器/微信粘贴 fallback；visual-agent 端点（set camera / take camera photo，给 coding agent 建模用）；三视图导出、UV wireframe。
