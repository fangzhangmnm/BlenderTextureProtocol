# Blender Texture Protocol (BTP) — v1 规范

**Bundle 版本**: `1.1.0`（与同目录 [`btp.js`](./btp.js) 的 `BUNDLE_VERSION` 严格对齐）
**Wire 版本**: `v1`（所有 endpoint 以 `/v1` 前缀）

## BTP 是什么

BTP 是一个 **Blender 插件 + 配套协议**，让外部图像编辑器（iPad 上的画板 app、PC 上的参考板 app、或任何脚本）通过一个 **HTTP 形状的 API** 直接读写 Blender 当前 `.blend` 里的贴图（`bpy.data.images`），**不经过导出 PNG → 文件管理器 → 重新导入**这条 friction 链。改完一调 API，贴图立刻在 Blender 里更新并 pack 进 `.blend`。

一句话数据流：`外部编辑器 → BTP 客户端 → (HTTP 或 WebRTC) → Blender 插件 → bpy.data.images`。

**两种 transport，同一套 API**：
- **localhost HTTP**——编辑器和 Blender 在**同一台机器**上时用。`http://127.0.0.1:18765`，零配置。
- **WebRTC DataChannel**——编辑器在**另一台设备**上时用（如 iPad ↔ PC）。经 Blender 面板配对一次。

> 本文是这套协议的**唯一权威契约**：消费方（接 BTP 的 app / agent）读本文即可集成，无需读源码。术语 "客户端" = 同目录的 JS 客户端库（`btp.js` 等）；"server" = Blender 插件端（[`../../blender_addon/btp/`](../../blender_addon/btp/)）。

---

## 文档维护规则（写给改本文的人 / agent）

- 本文是**持久契约**，描述"协议现在是什么、怎么用"——**不是 changelog、不是开发日志**。"这次改了什么 / 版本间差异" 一律进 [`CHANGELOG.md`](./CHANGELOG.md)，不进本文。
- 不写只有特定语境才懂的话（某次对话、某个内部代号、某条临时进度）。每一句都应让一个**没有任何项目背景**的读者看懂。要提到某个消费方时，用通用描述（"一个 iPad 画板 app"）而非假设读者认得的专名。
- 功能状态用**中性陈述**：`已实现` / `计划中（未实现）`。不写"测过没测过 / 哪天验的 / 下一步谁做"这类会过期的叙述。
- 协议语义或客户端文档化 API 变化 → bump `BUNDLE_VERSION` 并在此同步；纯内部重构 / bug fix 不 bump、不在此留痕。
- 与代码冲突时**以代码现状为准**，并修正本文。

---

## 概念模型（先读这段，就懂 API 为什么长这样）

- **身份 = image 的 `name`**（Blender 内保证唯一）。URL 里的 `{name}` 必须 percent-encode（名字可能含中文、空格、`.001` 后缀）。无 UUID、无额外 ID。
- **上传/下载语义 = 覆盖**。`PUT` 一张贴图就是用新像素整体替换。**协议不做冲突检测、不做版本合并**——多个客户端同时写同一张，最后写的赢，由使用方自行协调。这是有意的：纹理工作流里冲突解决只会添堵。
- **pack-all**：写入的贴图自动 pack 进 `.blend`（像素随 `.blend` 走，不依赖外部文件）。读取未 pack 的贴图时 server 会顺手 pack（无损）。
- **Undo 友好**：所有写操作（PUT / 创建 / rename）在 Blender 内作为一个带 undo 的 operator 执行，用户 Ctrl-Z 能回滚到操作前。（已知限制：图像**像素**的 redo（Ctrl-Shift-Z）在 Blender 侧不可靠——这是 Blender 自身 image undo 栈的限制，非本协议可控。）
- **transport 对 API 透明**：localhost HTTP 和 WebRTC 给到的是**完全相同**的 9 个 endpoint、相同的响应、相同的错误码。换 transport 不改任何调用代码。

---

## 快速接入

1. 把整个 `protocol/v1/` 目录**拷贝进你的 app**（源码直接 vendor，无需 npm / CDN）。
2. **只**从 [`index.js`](./index.js) import；其它文件是实现细节，别 deep import。

```javascript
import {
  BTPClient, BTPError, BUNDLE_VERSION,
  connectRemote, ManualSignaling,
} from "./vendor/btp/v1/index.js";

// ① 同机：localhost HTTP，零配置
const client = new BTPClient();                        // 默认 http://127.0.0.1:18765
const scene  = await client.getScene();                // 探活；失败 = 插件没开或不在同机

// ② 跨设备：WebRTC，配对一次（详见下文「WebRTC transport」）
const conn = await connectRemote({
  signaling: ManualSignaling({
    offer:    pastedConnectionCode,                    // 用户从 Blender 面板复制来的码
    onAnswer: (code) => showCodeForUserToPasteBack(code),
  }),
});
const remote = new BTPClient({ baseUrl: "", fetch: conn.fetch });
// remote 之后与 client 用法完全一致；conn.close() 断开
```

集成建议：
- 启动先试同机 `new BTPClient()` + `getScene()`；失败再走 `connectRemote`（跨设备）或提示用户开插件。
- 别把 `color_space` 当 enum 比对（见 metadata 说明），按 opaque 字符串透传。
- 别依赖 `/v1/exec` 下的具体命令跑核心流程（那些不在版本保证内）。
- 缺接口 → 提给协议维护方加 endpoint，别在 app 端绕协议。协议是公开契约，破坏性改动会 bump major 并起 `protocol/v2/`。

---

## Transport

### localhost HTTP（同机）

- server 监听 `127.0.0.1:18765`（端口可在插件 Preferences 改）。仅绑 loopback，**不暴露到局域网**——局域网扫描看不到这个 socket。
- 浏览器跨域：server 发 CORS `*`，所以 HTTPS 部署的 app 也能 `fetch http://127.0.0.1:18765`（浏览器把 localhost 当 secure context 放行）。
- 开关：插件 Preferences 里的"启用 localhost HTTP 服务"勾选框。
- 安全：因为只绑 loopback，唯一残留面是**同机其它程序/网页**也能打这个端口。按当前设计，靠"用户主动开启"限制暴露窗口，不加 token。

### WebRTC transport（跨设备）

**为什么跨设备不能直接用 HTTP（即便在同一局域网）**：浏览器禁止 HTTPS 页面 `fetch http://<局域网IP>`（mixed-content / secure-context 限制）——同一个 WiFi 也被拦。只有 `127.0.0.1` 在白名单内（所以同机 HTTP 行）。能让一个 HTTPS 页面打到一个**无 TLS 证书**的对端、又不用让用户装证书的，只有 **WebRTC DataChannel**（其 DTLS 自带加密传输身份）。所以拦路的是浏览器策略、不是 NAT——局限在局域网能省掉 STUN/TURN 和公网信令，但**省不掉 WebRTC 本身**。

**配对角色**：**Blender 是 offerer，app 是 answerer**。Blender 生成 offer，app 应答。

**握手流程**：
1. 用户在 Blender 的 BTP 面板点 "Open for Another Device" → 生成一个**连接码**（offer，`BTP1:` 信封格式），显示并复制到剪贴板。
2. app 拿到该码（用户粘贴）→ 应答，产出一个**响应码**（answer，`BTP1:` 信封）。
3. 用户把响应码粘回 Blender 的 "Paste Response from Device"。
4. DataChannel 打开。之后 app 发请求、Blender 回响应，走与 HTTP 完全相同的处理管线。

**LAN 默认不配 ICE server**：客户端默认 `iceServers: []`，同子网靠 host candidate 直连，无外部依赖。

**信令（如何把 offer/answer 送到对端）是可插拔的**：
- `ManualSignaling`（**已实现**）—— 复制粘贴，零基础设施。最少两次跨设备粘贴（offer 去、answer 回）。
- `ServerSignaling`（**计划中，未实现**）—— 一个公网可达的 relay，两端输同一个短 PIN，把 offer/answer 各转一程，配对收敛成"输一次 PIN"。接缝已在 [`signaling.js`](./signaling.js) 留好。

**免重复配对（计划中，未实现）**：目标是配一次后、连接断了能免粘贴自动重连，只在"网络身份变了"（IP / 端口 / 持久化的 DTLS 证书 变化）时才需重新配对。需要两端持久化证书 + 钉固定 UDP 端口让 offer/answer 可复现。`connectRemote` 已暴露 `remoteFingerprint`（从对端 SDP 解析的 DTLS 指纹）供信任展示和将来的证书钉用。

**安全**：DataChannel 经 DTLS 加密。手动粘贴模式下，"把码输进你自己的设备"这一步本身就是认证；首次配对可比对双方 `remoteFingerprint` 防中间人。

**消息分片（实现细节，消费方通常无需关心）**：一条 DataChannel 消息有体积上限（SCTP + 各浏览器限制，常见 ~64KB–256KB）。一次 GET 大贴图或 PUT 几 MB 的 PNG 装不进单条消息，所以每条逻辑信封（请求或响应）按 16KB 切片、对端重组。线格式：

```
帧 (JSON 文本):   { id, i, n, p }      # i=分片序号(0基), n=总片数, p=信封JSON的一段
请求信封:         { id, method, path, headers?, body_b64? }
响应信封:         { id, status, headers, body_b64 | null }
```

`body_b64` 是请求/响应体的 base64。未分片的 raw 信封在输入侧也接受（向后兼容）。JS 端实现 [`frame.js`](./frame.js)，Blender 端 [`../../blender_addon/btp/frame.py`](../../blender_addon/btp/frame.py)，两者线格式严格一致。

---

## 通用约定

### 编码
- 所有 JSON 请求/响应：UTF-8，`Content-Type: application/json; charset=utf-8`。
- 二进制贴图：v1 只支持 `image/png`。后续版本可经 `Accept` / `Content-Type` 协商加 `image/x-exr` 等。
- URL path 里的 `{name}` 必须 percent-encode。

### 错误响应
status code 表达错误大类，`error.code` 表达具体原因（machine-readable，跨版本稳定）：

```json
{ "error": { "code": "texture_not_found", "message": "No image named 'T_Body'", "details": {} } }
```

| status | 语义 |
|---|---|
| 200 | 成功（含读、改） |
| 201 | 创建成功 |
| 400 | 请求格式错（缺字段、JSON 解析失败） |
| 404 | 资源不存在 / 路由不存在 / exec 命令未注册 |
| 409 | 冲突（重名） |
| 415 | Content-Type 不支持（v1 PUT/POST 只接 PNG） |
| 500 | server 内部错（Blender API 异常） |

**冲突检测**：不做。`PUT` 即覆盖，多客户端竞争由使用方协调。

---

## Endpoints

完整 9 个。所有写操作可被用户 Ctrl-Z 回滚。

### `GET /v1/scene`
当前 `.blend` 的元信息。
```json
{ "blend_filepath": "D:/path/foo.blend", "unit": "METRIC", "active_object_name": "Cube" }
```
- `blend_filepath` 为空串 = `.blend` 没保存过；`active_object_name` 为 `null` = 无 active object。

### `GET /v1/textures`
所有 user image 的 metadata 列表（过滤掉 `VIEWER` / `MOVIE` source），按 `name` 字典序。每项见 [Texture metadata](#texture-metadata)。

### `GET /v1/textures/{name}`
单条 metadata。**404** `texture_not_found`。

### `GET /v1/textures/{name}/data`
取像素字节。`Content-Type` 反映源格式（`image/png` 等），body 是原始字节。**副作用**：未 pack 的会先被 `image.pack()`（无损）。

### `PUT /v1/textures/{name}/data`
替换已有 image 的像素。
- 请求：`Content-Type: image/png`（强制），body = PNG 字节。
- **200**：替换后的 metadata（`packed` 变 `true`，分辨率以请求 PNG 为准）。
- **415**：Content-Type 不是 PNG。**404**：image 不存在（PUT 不创建，创建用 POST）。

### `POST /v1/textures`
新建 image。
- 请求：header `X-BTP-Name: {name}`（必填）+ `Content-Type: image/png` + PNG body。
- **201**：新 metadata。**409** `name_exists`。**400** `missing_name`。

### `POST /v1/textures/{name}/rename`
重命名。请求 `{ "new_name": "..." }`。**200** 新 metadata。**409** `name_exists`。**404** 原名不存在。（Blender 内名字唯一，冲突直接拒，不自动加 `.001`。）

### `GET /v1/selection`
当前用户选中的资源。
```json
{ "texture": "T_Body", "object": null, "mesh": null }
```
`object` / `mesh` 为后续版本占位，v1 恒为 `null`。`texture` 启发式：优先 Image Editor 当前显示的 image，否则 active material 的 active image-texture node，都没有则 `null`。

### `POST /v1/exec`
ad-hoc 命令入口（server 端可注册自定义命令）。请求 `{ "command": "...", "params": {...} }`，响应由命令决定。**404** `unknown_command`（`details.registered` 列已注册命令）。
> ⚠ `/v1/exec` 下的命令**不在版本保证范围内**。消费方不应依赖它跑核心流程，仅作 ad-hoc 扩展。

---

## Texture metadata

```typescript
interface TextureMetadata {
  name: string;            // 唯一 ID（Blender 内保证）
  width: number;
  height: number;
  channels: number;        // 1 | 3 | 4
  color_space: string;     // "sRGB" | "Non-Color" | … —— 当 opaque string，别硬编码比对
  is_float: boolean;       // true = 32-bit float (HDR)
  alpha_mode: string;      // "STRAIGHT" | "PREMUL" | "CHANNEL_PACKED" | "NONE"
  source: string;          // "FILE" | "GENERATED" | "MOVIE" | "VIEWER" | …
  file_format: string;     // "PNG" | "JPEG" | "OPEN_EXR" | …
  is_dirty: boolean;       // .blend 内有未保存修改
  packed: boolean;         // 像素是否已 pack 进 .blend
}
```
- 协议**不暴露 DPI**（Blender image datablock 不记 DPI，纹理用例下无意义）。
- `color_space` 的取值在不同 Blender 版本可能不同（OCIO 标准化进程中），故按字符串透传、勿硬编码 enum。

---

## 版本管理

- **Wire 版本 `/v1`**：所有 `/v1/*` endpoint 在 v1 内**向前兼容**——可新增字段，不可删字段、不可改语义、不可改 status code。
- **Bundle 版本**（`BUNDLE_VERSION`，spec.md + 客户端库配对）：协议语义或客户端文档化 API 变化时 bump；内部重构 / bug fix 不 bump。
- **Major 升级（1.x → 2.x）**：wire 升到 `/v2/*`，仓库出现并列的 `protocol/v2/` 目录，`/v1/*` 保留向后兼容。
- 版本间的具体变更记录见 [`CHANGELOG.md`](./CHANGELOG.md)。

### 保留命名空间（v1 内保留，未实现，请勿占用）
```
/v1/meshes/{name}        /v1/objects/{name}        /v1/materials/{name}        /v1/jobs/{id}
POST /v1/meshes/{name}/uv-wireframe          POST /v1/objects/{name}/three-view-mesh
GET  /v1/textures/{name}/data  (Accept: image/x-exr  → HDR 取)
```

---

## 客户端 API 参考（`index.js` 导出）

| 导出 | 用途 |
|---|---|
| `BTPClient` | 9 个 endpoint 的封装；两种 transport 共用 |
| `BTPError` | 失败时抛出，带 `.status` / `.code` / `.details` |
| `connectRemote(opts)` | 跨设备配对，返回 `{ fetch, close(), peerConnection, remoteFingerprint, connectionState }` |
| `channelFetch(channel, opts?)` | 把一个已开的 DataChannel 包成 fetch（自带 channel 时的 escape hatch） |
| `ManualSignaling({offer, onAnswer})` | 复制粘贴信令策略 |
| `ServerSignaling` | 计划中（调用即抛"未实现"） |
| `BUNDLE_VERSION` / `PROTOCOL` | `"1.1.0"` / `"v1"` |

### BTPClient 方法

```javascript
await client.getScene();                              // GET /v1/scene
await client.listTextures();                          // GET /v1/textures
await client.getTextureMetadata("T_Body");            // GET /v1/textures/T_Body
const blob = await client.getTextureData("T_Body");   // GET …/data        → Blob
await client.putTextureData("T_Body", pngBlob);       // PUT …/data
await client.createTexture("T_New", pngBlob);         // POST /v1/textures
await client.renameTexture("T_Old", "T_New");         // POST …/rename
await client.getSelection();                          // GET /v1/selection
await client.exec("cmd", { a: 1 });                   // POST /v1/exec
await client.fetch("GET", "/v1/whatever");            // 未封装 endpoint 的 escape hatch

try {
  await client.getTextureMetadata("nonexistent");
} catch (e) {
  if (e instanceof BTPError && e.code === "texture_not_found") { /* … */ }
}
```

### 构造选项 `new BTPClient(opts)`
- `baseUrl` —— 默认 `"http://127.0.0.1:18765"`（localhost HTTP）；WebRTC 传 `""`（path 即 fetch 的 url）。
- `fetch` —— 注入 transport。不传 = 浏览器原生 fetch；传 `conn.fetch` = WebRTC DataChannel。
- `timeoutMs` —— 单请求超时（默认无超时）。

### connectRemote 选项
- `signaling`（必填）—— 一个有 `receiveOffer()` / `sendAnswer(code)` 的策略（用 `ManualSignaling` 构造）。
- `rtcConfig` —— 默认 `{ iceServers: [] }`（纯 LAN）。
- `handshakeTimeoutMs` —— 默认 30000。
- `requestTimeoutMs` —— 每请求超时（默认无）。
- `onStateChange(state)` —— 连接状态回调。

> PUT 返回 200 即表示贴图已在 Blender 内更新，**无需再等任何 "sync"**。
