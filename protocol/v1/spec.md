# Blender Texture Protocol — v1 规范

**Bundle 版本**: `1.1.0`（与同目录 [btp.js](./btp.js) 严格对齐）
**Wire 版本**: `v1`（URL 前缀 `/v1`）

> ## 本文怎么维护（元规则 / meta-rule）
>
> 这份 spec.md 是 BTP 协议的**持久 SSoT**，是 tutorial + API overview 合一的
> 一份文档（同 JRP `src/store/STORE.md` 的写法）。给后来的 agent 和人：
>
> - **它是 persistent 的契约，不是 changelog，不是聊天记录。** 禁止往里 dump
>   "本次改了啥 / 最近的人类 minor feedback / 这轮讨论"。那些进 commit message、
>   journal、或 ADR，不进这里。这里只留**当前为真的协议 + 怎么用**。
> - **写法**：先心智模型 → 默认部署 → 通用约定 → endpoints → 客户端 API →
>   集成建议。读者读完能直接接，不用读源码。
> - **as-of 戳**：任何易腐烂、版本相关、或"已定未全验"的条目，行内标
>   `（as-of vN / YYYY-MM-DD）`。已定但未实现的标 **⚠TODO**。
> - **信任顺序**（doc 与现实冲突时）：代码现状 > journal/聊天里的人类原话 >
>   ADR（why 类，耐老化）> AI 写的 how 类 doc（最易腐烂，本文属此类）。
>   反直觉条目先回人类语料验证出处再信。
> - **版本对齐**：协议语义或 btp.js 文档化 API 变 → bump `BUNDLE_VERSION`
>   并在此同步；内部 refactor / bug fix 不 bump、不在此留痕。

## 版本管理策略

- `BUNDLE_VERSION`（spec.md + btp.js）当**协议语义**或 **btp.js 文档化 API** 变化时 bump。
- 实现 bug 修复 / 内部 refactor / 非语义性 wording 调整**不 bump**。
- Major 升级（1.x → 2.x）意味着 wire 路径升到 `/v2/*`，本仓库出现并列 `protocol/v2/` 目录。
- v1 的所有 `/v1/*` endpoint 在 1.x 内**向前兼容**：可以新增字段，不可删字段、不可改语义、不可改 status code。

## 默认部署

- **transport**: localhost HTTP，监听 `127.0.0.1:18765`（端口可配置）。**默认开启**——让 sibling 应用（如 AtlasMaker）启动时自动 detect 并直连，无需用户配置。仅绑定 127.0.0.1，不暴露到局域网。
- **关闭方式**: Blender Preferences > Add-ons > Blender Texture Protocol，取消勾选"启用 localhost HTTP 服务"。
- **跨设备 (iPad / 手机 / 第二台 PC)**: 同一套 endpoint，transport 换成 **WebRTC DataChannel**，配对走 Blender N-panel 的"Open for Another Device"。详见下文 [§远程 transport](#远程-transport跨设备--webrtc)。Sibling 应用应当先尝试 localhost 直连，失败再走牵手。

Server 实现见 [Blender addon](../../blender_addon/btp/)。

## 远程 transport（跨设备 / WebRTC）

> as-of bundle 1.1.0 / 2026-06-25。手动粘贴配对已实现并 mock 测过；**真机 iPad↔Blender ICE 握手未验**。零粘贴重连、信令服务器为 ⚠TODO。

**为什么跨设备必须用 WebRTC（即便只在局域网）**：WebPaint 是 HTTPS PWA。浏览器**禁止** HTTPS 页面 `fetch http://<lan-ip>:port`（mixed-content / secure-context 墙）——同一个 WiFi 也被拦。`127.0.0.1` 被白名单成 secure context（所以同机 localhost HTTP 能直连），但局域网 IP 不在白名单。能从 HTTPS 页面打到一个无证书对端、又不用装证书的，只有 WebRTC DataChannel（DTLS 自带安全传输）。所以拦路的是浏览器策略、不是 NAT；限局域网能砍掉 STUN/TURN 和互联网信令，但**砍不掉 WebRTC 本身**。

**角色**: **Blender 是 offerer**，app 是 answerer（app 通过 `pc.ondatachannel` 收到通道）。只有这一种 offerer 模型。

**握手（手动粘贴；信令服务器可后续替换粘贴）**:
1. Blender N-panel "Open for Another Device" → 生成 offer（`BTP1:` 信封），显示并复制到剪贴板。
2. app 粘贴该码 → 产生 answer 码（`BTP1:` 信封）。
3. Blender "Paste Response from Device" 粘回 answer。
4. DataChannel 打开。之后 app 发请求信封、Blender 回响应信封，走与 HTTP 同一条 `api.handle` 主线程管线。

**LAN 默认无 ICE server**：客户端默认 `iceServers: []`，同子网靠 host candidate 直连，零外部依赖（符合 vendor-everything）。

**分片（两端对称）**: 单条 DataChannel 消息有体积上限（SCTP + 各浏览器，常 ~64KB–256KB）。一次 GET 2048² PNG 或 WebPaint 的 PUT 都是几 MB，单 `send()` 装不下。所以每条逻辑信封（请求**或**响应）按 16KB 切成 frame，对端重组。小消息 = 单 frame。实现：[`frame.js`](./frame.js) ⟷ [`blender_addon/btp/frame.py`](../../blender_addon/btp/frame.py)（字节级对齐，JS↔Python cross-test 验过）。

```
帧 (JSON 文本):   { id, i, n, p }          # i=分片序号, n=总数, p=信封 JSON 的一段
请求信封:         { id, method, path, headers?, body_b64? }
响应信封:         { id, status, headers, body_b64 | null }
```
未分片的 raw 信封在输入侧仍被接受（向后兼容）。

**信令是可插拔接缝**（anti-abandonware）:
- `ManualSignaling`（已实现）—— 复制粘贴，零 infra。最少两次跨设备粘贴（offer 去、answer 回）。
- `ServerSignaling`（**⚠TODO**）—— 一个 HTTPS/WSS relay，两端输同一个短 PIN，把 offer/answer 各送一程，配对收敛成"输一次 PIN"。接缝已留（[`signaling.js`](./signaling.js)），未实现。

**零粘贴重连（⚠TODO，下一 slice）**: 目标是配一次、之后免粘贴重连，"失效才重牵"——失效 = LAN IP / 钉的 UDP 端口 / 持久化证书 变了（家用 LAN + DHCP 保留可数天到数周不变）。需要两端持久化 DTLS 证书 + 钉固定 UDP 端口，使 offer/answer 可复现并缓存。**aiortc 能否钉端口/注入证书未验证**——故先交付手动配对，零粘贴单独验。`connectRemote` 已暴露 `remoteFingerprint`（从对端 SDP 解析）供信任展示与未来证书钉用。

**安全姿态**:
- **localhost HTTP**：绑 `127.0.0.1`，局域网根本扫不到这个 socket。残留风险只是**同机浏览器里的恶意网页**能 `fetch` localhost（CORS `*` 放行、secure-context 反而允许打 localhost——它不是这里的防线）。缓解 = 服务**默认关、用户主动开**，窗口仅限开着时。对 hobby 自用工具够用。（as-of 2026-06-25：定为默认关即可，不加 token/Origin 白名单。）
- **WebRTC**：DTLS 加密传输。LAN 手动粘贴下，"把码输进自己的设备"这一步本身就是 auth；首次配对可比对 `remoteFingerprint`（4-hex 安全码思路）防 MITM。

## 通用约定

### 编码
- 所有 JSON 请求/响应: UTF-8，`Content-Type: application/json; charset=utf-8`。
- 二进制贴图: `image/png`（v1 only）。后续版本可通过 `Accept` / `Content-Type` 协商加 `image/x-exr` 等。
- URL path 中的 `{name}` 必须 percent-encode（image 名可能含中文、空格、`.001` 之类）。

### 错误响应
status code 表达错误大类，`error.code` 表达具体原因（machine-readable，跨版本稳定）：

```json
{
  "error": {
    "code": "texture_not_found",
    "message": "No image named 'T_Body_Diffuse'",
    "details": { /* 可选 */ }
  }
}
```

| status | 语义 |
|---|---|
| 200 | 成功（含读、改） |
| 201 | 创建成功 |
| 400 | 请求格式错（缺字段、JSON 解析失败） |
| 404 | 资源不存在 / 路由不存在 / exec command 未注册 |
| 409 | 冲突（重名） |
| 415 | Content-Type 不支持（v1 PUT/POST 只接 PNG） |
| 500 | server 内部错（Blender API 异常） |

**冲突检测策略**: 不做。`PUT data` 语义即覆盖，多客户端竞争由用户管理。

### Undo 模型
所有 mutating endpoint（PUT / POST 创建 / rename）通过**内部 Blender Operator**（带 `bl_options = {'UNDO'}`）执行 mutation。Blender 在 operator 完成时自动 push memfile snapshot，比手动 `undo_push` 更可靠（尤其是新增 datablock 这种操作）。用户 Ctrl-Z 可回滚到 mutation 之前的状态。

GET data 在 image 未 packed 时会调用 `image.pack()` 作为副作用——这是无损的内部状态变化（像素本身不变），**不进 undo stack**。

## Endpoints

### `GET /v1/scene`
返回当前 .blend 的元信息。

**Response 200**:
```json
{
  "blend_filepath": "D:/path/foo.blend",
  "unit": "METRIC",
  "active_object_name": "Cube"
}
```
- `blend_filepath` 是空串表示 .blend 没保存
- `active_object_name` 是 `null` 表示无 active object

### `GET /v1/textures`
列出所有 user image (过滤掉 `VIEWER` / `MOVIE` source)。

**Response 200**:
```json
[
  {"name": "T_Body", "width": 2048, "height": 2048, "channels": 4, ...},
  ...
]
```

按 `name` 字典序排列。每项 metadata 字段见下"Texture metadata"。

### `GET /v1/textures/{name}`
单条 metadata。

**Response 200**: 单个 Texture metadata 对象  
**404** `texture_not_found`

### `GET /v1/textures/{name}/data`
取像素字节。

**Response 200**:
- `Content-Type` 反映源格式 (`image/png`、`image/jpeg`、`image/x-exr` etc.)
- Body 是原始字节

**副作用**: 如果 image 未 packed，server 会调用 `image.pack()`（与 pack-all 策略一致）。

### `PUT /v1/textures/{name}/data`
替换已有 image 的像素。

**Request**:
- `Content-Type: image/png`（强制）
- Body: PNG 字节

**Response 200**: 替换后的 Texture metadata。注意:
- `source` 可能从 `GENERATED` 变成 `FILE`（实现细节，不影响后续行为）
- `packed` 会变成 `true`
- 分辨率以请求体的 PNG 为准（client 决定分辨率）

**415**: Content-Type 不是 `image/png`  
**404**: image 不存在（PUT 不会创建，要创建用 POST）

### `POST /v1/textures`
新建 image。

**Request**:
- Header `X-BTP-Name: {name}`（必填，新 image 的名字）
- `Content-Type: image/png`
- Body: PNG 字节

**Response 201**: 新建的 Texture metadata  
**409** `name_exists`: 该名字已被占用  
**400** `missing_name`: 没有 `X-BTP-Name` header

### `POST /v1/textures/{name}/rename`
重命名 image。

**Request**:
```json
{ "new_name": "T_Body_New" }
```

**Response 200**: 重命名后的 Texture metadata  
**409** `name_exists`: 新名已存在  
**404**: 原名不存在

注: Blender 内 image 名本身唯一。冲突会被 server 拒绝；不做自动 `.001` 后缀。

### `GET /v1/selection`
当前用户选中的资源。

**Response 200**:
```json
{
  "texture": "T_Body",
  "object": null,
  "mesh": null
}
```

`object` / `mesh` 字段为 v2 占位，v1 总是 `null`。

`texture` 启发式: 优先返回 Image Editor 当前显示的 image；否则 active material 的 active image-texture node 的 image；都没有返回 `null`。

### `POST /v1/exec`
ad-hoc 命令入口。Server 端可通过 `api.register_exec(name, handler)` 注册命令。

**Request**:
```json
{
  "command": "build_three_view_mesh",
  "params": { /* 任意 */ }
}
```

**Response**: 由命令决定（JSON 或 binary）。  
**404** `unknown_command`: 命令未注册（`details.registered` 列出已注册命令名）。

⚠️ **`/v1/exec` 下注册的 command 不在版本保证范围内**。AtlasMaker / WebPaint 不应依赖 `/v1/exec` 跑核心流程，仅用于 ad-hoc 扩展。

## Texture metadata

```typescript
interface TextureMetadata {
  name: string;            // 唯一 ID（Blender 内保证）
  width: number;
  height: number;
  channels: number;        // 1, 3, 4
  color_space: string;     // "sRGB" | "Non-Color" | "Linear..." 等。Client 应当作 opaque string。
  is_float: boolean;       // true = 32-bit float (HDR)
  alpha_mode: string;      // "STRAIGHT" | "PREMUL" | "CHANNEL_PACKED" | "NONE"
  source: string;          // "FILE" | "GENERATED" | "MOVIE" | "VIEWER" 等
  file_format: string;     // "PNG" | "JPEG" | "OPEN_EXR" | ...
  is_dirty: boolean;       // .blend 内未保存的修改
  packed: boolean;         // 像素是否打包进 .blend
}
```

### Color space 注意事项
- v1 协议**不暴露 DPI**（Blender image datablock 不记 DPI；纹理用例下 DPI 无意义）。
- `color_space` 值在不同 Blender 版本可能略不同（4.x → 5.x OCIO 标准化中）。**Client 不应硬编码 enum 比对**，按字符串透传。

## 未来命名空间（v1 保留，不实现）

```
/v1/meshes/{name}                 — mesh datablock
/v1/objects/{name}                — scene object (mesh + transform)
/v1/materials/{name}              — material
/v1/jobs/{id}                     — async 长任务
POST /v1/meshes/{name}/uv-wireframe       — 生成 UV 线框 PNG
POST /v1/objects/{name}/three-view-mesh   — 三视图建模
GET /v1/textures/{name}/data with Accept: image/x-exr  — HDR 取
```

这些名字现在请勿占用。

## Client API 对应（窄接口 / index.js）

**唯一入口**：vendor 整个 `protocol/v1/` 目录，只从 [`index.js`](./index.js) import。其余文件（`webrtc-fetch.js` / `signaling.js` / `frame.js` / `sdp-envelope.js`）是实现细节，sibling 不直接碰。两种 transport 之后给的是**同一个 `BTPClient`、同一套 endpoint、同样的错误**。

```javascript
import {
  BTPClient, BTPError, BUNDLE_VERSION,
  connectRemote, ManualSignaling,
} from "./vendor/btp/v1/index.js";

// 同机（AtlasMaker on PC）—— localhost HTTP，零配置：
const client = new BTPClient();                        // 默认 http://127.0.0.1:18765

// 跨设备（WebPaint on iPad）—— WebRTC，经 Blender 面板配对一次：
const conn = await connectRemote({
  signaling: ManualSignaling({
    offer: pastedConnectionCode,                       // 用户从 Blender 复制来的码
    onAnswer: (code) => showCodeForUserToCopy(code),   // 给用户粘回 Blender
  }),
});
const remoteClient = new BTPClient({ baseUrl: "", fetch: conn.fetch });
// 从此与 localhost 那个 client 用法完全一致。conn.close() 断开。
```

`connectRemote` 返回 `{ fetch, close(), peerConnection, remoteFingerprint, connectionState }`。
`channelFetch(channel)` 也单独导出（自带 channel 的 escape hatch / 单测用）。

**BTPClient 方法**（两种 transport 共用）:

```javascript
await client.getScene();                              // GET /v1/scene
await client.listTextures();                          // GET /v1/textures
await client.getTextureMetadata("T_Body");            // GET /v1/textures/T_Body
const blob = await client.getTextureData("T_Body");   // GET /v1/textures/T_Body/data
await client.putTextureData("T_Body", pngBlob);       // PUT /v1/textures/T_Body/data
await client.createTexture("T_New", pngBlob);         // POST /v1/textures
await client.renameTexture("T_Old", "T_New");         // POST /v1/textures/T_Old/rename
await client.getSelection();                          // GET /v1/selection
await client.exec("my_command", { a: 1 });            // POST /v1/exec
await client.fetch("GET", "/v1/whatever");            // escape hatch

try {
  await client.getTextureMetadata("nonexistent");
} catch (e) {
  if (e instanceof BTPError && e.code === "texture_not_found") {
    // handle
  }
}
```

`BTPClient` 构造选项:
- `baseUrl` — 默认 `"http://127.0.0.1:18765"`；WebRTC transport 传 `""`（路径即 fetch 的 url）。
- `fetch` — 注入 transport。不传 = 浏览器原生 fetch（localhost HTTP）；传 `conn.fetch` = WebRTC DataChannel。
- `timeoutMs` — 单请求超时（默认无超时）。

## 给 sibling 项目集成的建议

1. 拷贝整个 `protocol/v1/` 目录到自己的 vendor 里（per umbrella 的 vendor-everything 约定）。
2. **只** `import { ... } from "./vendor/btp/v1/index.js"`，别 deep import 其它文件。
3. 启动时先试 localhost：`new BTPClient()` + 一次 `getScene()` 探活。失败 → 要么提示用户开 Blender 插件的 HTTP toggle（同机），要么走 `connectRemote`（跨设备）。
4. 跨设备 transport 用 `connectRemote(...)`，UI 把 offer 码/answer 码两个粘贴位接上 `ManualSignaling`。
5. 不要硬编码 `color_space` 值列表；当 opaque string 处理。
6. 不要依赖 `/v1/exec` 下的特定 command 跑核心流程。
7. PUT 之后**不需要**等待"sync"——response 200 时贴图已在 Blender 内更新。
8. 缺接口 / 库没实现你要的 → escalate（改协议走 pwa-cloud-store 同款纪律：协议是公开契约，破坏性改动 bump major、并起 `protocol/v2/`）。别在 app 端绕协议。
