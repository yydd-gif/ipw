# P3 · AI 层接入施工图（dsh 接入）

> 编制：马仔B ｜ 日期：2026-09-16 ｜ 版本：v1.0
> 上位文档：`A+装配式集成方案.md`（路线依据）· `软件设计方案-v2.0.md` §2/§6-P3（架构与阶段）
> **本文件是 P3 的施工图**：把「接 dsh」从设计推到「照着敲命令就能通」。
> 所有带 ✅实测 标记的结论都是本机真跑出来的，不是照文档抄的。

---

## 0. 先看这一段

**P3 的唯一目标：把已验证的 Python 引擎，通过一个不改一行源码的 dsh 组合包，暴露成模型可调用的工具，并且模型真的调通一次。**

| 项 | 状态 |
|---|---|
| 模型 API Key | ✅ **已到手**（2026-09-16），最后一个阻塞解除 |
| Key 连通性 | ✅ **实测通过**（`GET /models` → 200，见 §1） |
| 组合包骨架 | ✅ 已有 11 个源文件，构建产物在 `_verified/` |
| 组合包 → 7 工具 | ⬜ 待补 2 个（`datafill` / `docgen`），见 §3 |
| 运行时形态 | ✅ **ADR-18 已定案且已实测**（原生 dsh 免 Node 跑通，见 §2 / §10.2b） |
| profile 从哪来 | ✅ **已定**：从出厂 `sdk` 模板派生，见 §5.1 |
| 端到端跑通 | ⬜ 待做，步骤见 §7 |

**P3 工作量重估：2–3 天。** 前提是 §7 的步骤按序走完，卡点集中在 §9 风险 3（审批通道）。

---

## 1. 凭据与模型（实测）

### 1.1 Key 已实测可用

2026-09-16 用本机 PowerShell/urllib 直连 DeepSeek 官方接口验证：

| 探测 | 结果 |
|---|---|
| `GET https://api.deepseek.com/models` | ✅ **HTTP 200** |
| `POST /chat/completions`（`deepseek-chat`） | ✅ 200，正常返回 |
| `POST /chat/completions`（`deepseek-reasoner`） | ✅ 200，返回 `reasoning_content` |

### 1.2 ⚠️ 模型名有个坑（必须写进配置）

`GET /models` 的实际返回**只有两个模型**：

```json
{"object":"list","data":[
  {"id":"deepseek-flash",  "object":"model","owned_by":"deepseek"},
  {"id":"deepseek-v4-pro", "object":"model","owned_by":"deepseek"}
]}
```

而用 `deepseek-chat` 和 `deepseek-reasoner` 发请求时，**响应体的 `model` 字段都回 `deepseek-flash`** —— 也就是说旧模型名目前是**静默路由**到 `deepseek-flash` 的别名。

**这条的后果**：配置里写 `deepseek-chat`，你以为在用一个特定模型，实际上跑的是 `deepseek-flash`；哪天别名政策变了，行为静默改变，而且**没有任何报错**。

**规矩**：配置里**只写 `deepseek-flash` 或 `deepseek-v4-pro`**，不写别名。已核对 dsh web profile 默认值 `agent-default-model.model = deepseek-flash` —— **恰好是合法名，不用改**。

### 1.3 模型选型建议

| 用途 | 模型 | 理由 |
|---|---|---|
| 默认（工具选择、参数装配、结果解读） | `deepseek-flash` | 轻、快、便宜；P3 阶段够用 |
| AI 改写 / 扩写 / 润色（P5）、日志归纳成周报正文 | `deepseek-v4-pro` | 需要长文生成质量 |
| 会话标题生成 | `deepseek-flash` | dsh 内置，`maxOutputTokens: 64` |

> 选型做成 profile 配置项，**不写死在代码里**（dsh 官方约定：能否在 `cordis.yml` 里改掉它而不改代码）。

### 1.4 凭据注入方式：环境变量，不落配置文件

依据（✅实测自 `--dump-config`）：

```yaml
- id: web-search-deepseek
  name: '@deepseek-ai/dsh-web-search-deepseek'
  config:
    apiKeyEnv: DEEPSEEK_API_KEY      # ← dsh 自己的取 Key 方式就是环境变量
```

Python SDK 官方文档同样是 `export DEEPSEEK_API_KEY=sk-...`。**结论：走 `DEEPSEEK_API_KEY` 环境变量。**

可选（兼容代理/自建 endpoint）：`DEEPSEEK_BASE_URL`。

### 1.5 Key 的管理规矩（红线）

| 规矩 | 说明 |
|---|---|
| **绝不写进任何交付文档** | 本文件、`施工交接说明.md`、`数据与规则规格.md` 全都不含明文 Key |
| **绝不写进 `cordis.patch.yml`** | 配置层会进 tarball / 进交接包 / 进 Git，写进去等于泄漏 |
| **绝不写进组合包源码** | 同上 |
| 本机存放 | `.workbuddy/secrets/DEEPSEEK.env`（**不在交付包范围内**，`01_设计文档`~`07_模板资产` 才是交付物） |
| 交给第三方施工时 | 由甲方（工头）**另行单独提供**，不随方案文档一起发 |
| 泄漏后的动作 | 到 DeepSeek 控制台**立即吊销重建**，只改这一个文件 |

本机设置方式（Windows，当前用户级永久生效）：

```powershell
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY","<你的key>","User")
```

或只对当前会话生效（调试验证用）：

```powershell
$env:DEEPSEEK_API_KEY = "<你的key>"
```

---

## 2. 运行时形态（ADR-18：新结论）

### 2.1 两条路，本文件推荐换路

原 `A+装配式集成方案.md` §2 假定的运行时来源是 **npm**（`npx @deepseek-ai/dsh` / `dsh plugin add`），前提是本机有 Node ≥22.19 + pnpm ≥10。本轮实测发现**官方还有一条更省事的路**：

| | 路线 N（npm） | 路线 P（Python wheel）★推荐 |
|---|---|---|
| 获取 | `npm i -g @deepseek-ai/dsh` | `pip install deepseek-harness-sdk` |
| 包体 | 72 个依赖，仓库 183MB | wheel **68.7MB 压缩 / 234.6MB 落盘**（✅实测） |
| 需要 Node.js？ | ✅ **必须**（≥22.19） | ❌ **不需要**（✅ `env -i` 实测，见 §10.2b 第 17 条） |
| 需要 pnpm？ | ✅ 插件管理必须 | 🔶 **仅安装插件时需要**；启动已装好的 profile 不需要 |
| 终端用户装机 | Node + pnpm + dsh + 我们的包 | **一个 Python venv 就够了** |
| 版本通道 | `latest=0.1.5-rc.1` / `next=0.1.5-rc.2` / `alpha=0.1.6-alpha.1` | `deepseek-harness-sdk==0.1.5rc1`（与 runtime-bin 版本**强绑**） |
| 许可 | MIT | MIT |

**官方原文（runtime-bin 包的描述）**：*"It packages the normal `dsh` CLI and its closed Node dependency tree into a native executable, so SDK use requires no system Node.js."*

### 2.2 ADR-18 结论

> **运行时来源改用 `deepseek-harness-sdk`（PyPI wheel），不用 npm 全局安装。**

理由（按权重）：

1. **交付形态更干净** —— 我们的引擎本来就是 Python，壳是 Electron（自带 Node）。再让终端用户装一个系统级 Node + pnpm 是多余的。venv 一套搞定。
2. **版本锁死更容易** —— wheel 依赖写死 `deepseek-harness-runtime-bin==0.1.5rc1`，SDK 与运行时**不可能出现版本错配**；npm 的 rc/next/alpha 三通道反而容易装错。
3. **离线交付更可行** —— wheel 里的 `runtime/*.exe` 可直接拷进安装包，不需要联网 pip。
4. **与「不 fork / 不改 upstream」红线完全一致** —— 我们只是换了个获取渠道，插件机制、profile 机制、patch 层机制一模一样。

### 2.3 这条路的代价（如实列）

| 代价 | 严重度 | 说明 |
|---|---|---|
| **无 Windows arm64 wheel** | 低 | 目标平台是 Windows x64，可接受。若将来要 ARM 版，回去走 npm |
| **仍需 pnpm 来装插件** | 低 | 只在**打包机**上需要（把组合包装进 `DSH_HOME` 再随包分发），终端用户不需要 |
| **必须设非空 `DSH_HOME`** | 低（其实是好事） | 官方明确：`dsh` 命令「requires a non-empty `DSH_HOME`; it never falls back to `~/.dsh`」→ 天然隔离，不会污染用户全局环境 |
| 生态资料以 npm 路径为主 | 低 | 文档/社区示例多是 npm 写法，需自行换算 |

### 2.4 运行时关键路径与体积（✅实测）

```
<venv>/Lib/site-packages/deepseek_harness_runtime/
  ├─ deepseek-harness-runtime.json
  └─ runtime/
       ├─ deepseek-harness-sdk-runtime-win-x64.exe      240,529,920 B  ≈ 229.4 MB   ← dsh 本体
       └─ deepseek-harness-sdk-runtime-win-x64-rg.exe     5,429,760 B  ≈   5.2 MB   ← ripgrep 旁挂
```

| 项 | 压缩态（wheel） | 解压后（落盘） |
|---|---|---|
| Windows x64 | **68.7 MB** | **≈ 234.6 MB** |

> ⚠️ **交付包体积要按解压后的 234 MB 算，不是 68.7 MB。** 安装器不要指望"轮子小所以包小"。若安装包用 zip/7z 压缩分发，能压回 60–70 MB 量级，但**安装后磁盘占用就是 234 MB**。

✅实测的 wheel 载荷特征：
- `deepseek_harness_runtime_bin-0.1.5rc1-py3-none-win_amd64.whl` = **72,045,733 B ≈ 68.7 MB**
- 同版本其他平台：macOS arm64 72.0MB / macOS x64 75.7MB / Linux arm64 76.5MB / Linux x64 77.0MB
- 安装后可执行文件命名：`deepseek-harness-sdk-runtime-<platform>-<arch>[.exe]`
- Python 侧要求：`>=3.10`（我们用 3.13.x）
- SDK 依赖：`deepseek-harness-runtime-bin==0.1.5rc1` + `pydantic>=2.12,<3`（实测拉起 `pydantic 2.13.5` / `pydantic-core 2.46.5` / `annotated-types 0.8.0` / `typing-extensions 4.16.0` / `typing-inspection 0.4.4`）

---

## 3. 组合包 v0.2 变更清单

现有骨架（`04_AI组合包/dsh-yanshou-docs/`）是按 v1.0 的「五块引擎」写的，v2.0 扩到七块 + 双轨目录，**必须升版**。逐条如下。

### 3.1 工具从 5 个补到 7 个

| # | 工具名 | 引擎 | 现状 |
|---|---|---|---|
| 1 | `yanshou_datafill` | `datafill_engine.py` 取值装配 → FillPlan | ⬜ **新增** |
| 2 | `yanshou_docgen` | `docgen_engine.py` 建档 / 一键成册 / 无模板三选一 | ⬜ **新增** |
| 3 | `yanshou_fill` | `fill_engine.py` 模板填充 | ✅ 在 |
| 4 | `yanshou_subtable` | `subtable_engine.py` 子表接管 | ✅ 在 |
| 5 | `yanshou_numbering` | `numbering_engine.py` 编号 | ✅ 在 |
| 6 | `yanshou_aggregate` | `aggregate_engine.py` 汇总 | ✅ 在 |
| 7 | `yanshou_verify` | `verify_engine.py` 校验闸门 | ✅ 在 |

> **顺序有讲究**：`datafill` 产出的 FillPlan 要能被 `fill` 通过 `--plan` 复用（保证「预览」与「实际填充」是同一套值）。工具层要允许模型**先 datafill 预览、再 fill 落地**，不能只有一个黑盒 `fill`。

### 3.2 `package.json`：补 `peerDependencies`（ADR-14 落地）

**现状问题**：`package.json` 里**根本没有声明 `@deepseek-ai/*`**，而 `.npmrc` 和 `tsdown.config.ts` 的注释都按「已声明为 peer」在解释。文件之间对不上。

**改成**：

```json
{
  "name": "dsh-yanshou-docs",
  "version": "0.2.0",
  "type": "module",
  "main": "lib/index.mjs",
  "files": ["lib", "cordis.patch.yml"],
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } },
  "peerDependencies": {
    "@deepseek-ai/cordis": "0.1.5-rc.1",
    "@deepseek-ai/dsh-tools": "0.1.5-rc.1",
    "@deepseek-ai/schemastery": "0.1.5-rc.1"
  },
  "peerDependenciesMeta": {
    "@deepseek-ai/cordis": { "optional": true },
    "@deepseek-ai/dsh-tools": { "optional": true },
    "@deepseek-ai/schemastery": { "optional": true }
  },
  "scripts": { "build": "tsdown", "prepare": "tsdown" },
  "devDependencies": { "tsdown": "latest", "typescript": "latest" }
}
```

**三条要点**：
1. **版本写精确值，不用 `^`** —— dsh 是开发者预览期，破坏性变更就发生在大版本内，`^` 等于放它进来。
2. **`peerDependenciesMeta.optional = true`** —— 这些包由宿主 dsh 在运行时提供，构建机上装不全（实测 `@deepseek-ai/dsh-type-meta` 在 npm 上是 **404**）。标 optional 才不会让 `pnpm install` 炸。
3. **配合 `.npmrc` 的 `auto-install-peers=false`** —— 现有 `.npmrc` 已经写了，保留。

> ⚠️ **版本号要按实际装的 dsh 核对后再钉死**。本文件给的是 `0.1.5-rc.1`（npm `latest` 通道，2026-09-10 发布）。若最终走 ADR-18 的 wheel 路线，dsh 版本以 `deepseek-harness-sdk==0.1.5rc1` 为准 —— **两者要一致**。

### 3.3 `tsdown.config.ts`：改用新写法

`external` 在 tsdown 0.23 已废弃（现有注释里也提到了）。改为：

```ts
export default defineConfig({
  entry: ['src/index.ts'],
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'node22',
  dts: false,
  clean: true,
  deps: { neverBundle: [/^@deepseek-ai\//, /^node:/] },   // ← 替代 external
})
```

### 3.4 `config.ts`：路径模型换成双轨制

**现状问题**：默认值里 `protectedPaths: ['模版', '模版_原始备份']`、`engineRoot` 回退到 `<workspaceRoot>/.workbuddy/engine` —— 都是**旧目录约定**。v2.0 §2.6 已经改成双轨制（安装资产 `assets/` 只读 + 工程数据目录可读写），配置必须跟上。

**改成**：

```ts
export interface Config {
  /** 安装资产根（只读）：templates / spec / engine / runtime 都在这里 */
  installRoot: string
  /** 工程数据根（可读写，用户可整包拷走） */
  workspaceRoot: string
  /** 内嵌 Python 解释器 */
  pythonBin: string
  /** 引擎脚本目录。留空 = <installRoot>/engine */
  engineRoot: string
  /** 默认工程（未指定时用哪个工程目录） */
  activeProject: string
  /** 受保护路径（相对 installRoot 或绝对路径），一律拒绝写入 */
  protectedPaths: string[]
  /** 逃生开关，默认 false */
  allowWriteToTemplates: boolean
  /** 单次引擎调用的超时（毫秒） */
  engineTimeoutMs: number
}

export const Config: Schema<Config> = Schema.object({
  installRoot: Schema.string().required(),
  workspaceRoot: Schema.string().required(),
  pythonBin: Schema.string().default('python'),
  engineRoot: Schema.string().default(''),
  activeProject: Schema.string().default(''),
  protectedPaths: Schema.array(Schema.string()).default(['templates', 'templates_原始备份']),
  allowWriteToTemplates: Schema.boolean().default(false),
  engineTimeoutMs: Schema.number().default(600000),
})
```

**四个变化点**：

| 变化 | 为什么 |
|---|---|
| 新增 `installRoot` | 双轨制要区分「只读安装资产」和「可写工程数据」，原来只有一个 `workspaceRoot` 表达不了 |
| `protectedPaths` 默认改成 `templates` | 实际受保护目录是 `assets/templates/**`，不再是 `模版/` |
| `pythonBin` 变必填语义 | 交付时是内嵌运行时，路径由安装器写入 profile 配置，必须有值 |
| 新增 `engineTimeoutMs` | 原 `bridge.ts` 里超时是**硬编码** `10 * 60 * 1000`。违反 dsh 官方「无硬编码可调参数」约定 |
| 新增 `activeProject` | 壳要能切工程；引擎调用需要知道当前工程是哪个 |

### 3.5 `policy.ts`：路径基准跟着换

`normalize(p, base)` 里的 `base` 从 `workspaceRoot` 改成 `installRoot` —— 因为模板在**资产侧**，不在工程侧。这是最容易写错的一处：

- ❌ 旧写法：`normalize(target, config.workspaceRoot)` → 模板路径算不对，保护形同虚设
- ✅ 新写法：`normalize(target, config.installRoot)`

**并且必须补一条**：`assertWritable()` 要能识别**符号链接指向模板目录**的情况（用户可能建个 junction 绕过去）。用 `fs.realpathSync` 解析后再比。

### 3.6 `bridge.ts`：三处加固

| 项 | 现状 | 改成 |
|---|---|---|
| 超时 | 硬编码 10 分钟 | 读 `config.engineTimeoutMs` |
| 超时后的进程 | `child.kill()` —— Windows 上杀不掉子进程树 | 用 `taskkill /pid <pid> /T /F`（Windows）/ 进程组 kill（POSIX） |
| 契约 JSON 解析 | 只取 stdout 尾部 8 行当摘要 | **必须解析最后一行 JSON**，按 §6.1 契约取 `ok` / `summary` / `stats` / `errors`；解析失败才退回文本摘要 |
| 编码 | 直接 `toString('utf8')` | 显式设 `PYTHONIOENCODING=utf-8`，否则 Windows 上中文可能乱码 |

> **契约解析是硬要求**：`数据与规则规格.md` §6 已经把统一的契约 JSON 定死了（`ok` / `engine` / `summary` / `stats` / `items` / `errors`）。工具层如果不解析它，模型就只能读一坨文本，`errors[].level = block` 这种结构化信息全丢了。

### 3.7 `index.ts`：`inject` 可能要加

目前 `inject = ['tools']`。若启用全局模板保护钩子（见 §3.8），需要一并 inject 事件总线对应的服务。**先按实际跑出来的结果定**，不预先猜。

### 3.8 全局保护钩子：本阶段先不开

`policy.ts` 末尾注释的 `tools/pre-execute` 钩子，**确切回调签名仍未确认**。P3 阶段的做法：

1. 先只用工具内的 `assertWritable()`（确定性一层，已覆盖我们自己的 7 个工具）
2. 单独做一个**探针插件**打印真实事件对象结构，拿到签名后再启用全局层
3. **不凭猜测写跑不通的钩子**

这属于「锦上添花」而不是「P3 必须」——因为 v1.0 那次越界事故，是我们自己的工具干的，工具内闸门就够拦。

---

## 4. 七个工具的完整签名

统一约定：
- `parameters` 用 `defineTool` 的声明式写法（框架自动校验类型）
- 所有输出走 `output: { schema: { type: 'string' }, render: ... }` —— **回给模型的是人话，不是 JSON 字符串**（模型读自然语言摘要更稳；结构化数据留在壳侧用）
- 每个写盘工具**第一件事**是 `assertWritable()`

### 4.1 `yanshou_datafill`（新增）

| 参数 | 类型 | 必填 | 默认 | 映射到 |
|---|---|---|---|---|
| `itemId` | string | ✗ | 全部 | `--only` |
| `outPlan` | string | ✗ | `<工程>/_plan/fillplan.json` | `--out` |

```
description（给模型看的）：
「按字段字典与填数规则，算出整册每个占位符该填什么值，产出 FillPlan 预览。
 只算不写盘，不会改动任何文档。用于在真正填充前让用户确认取值是否正确。
 确定性计算，不调用模型推理。缺值字段会标记为 missing 并保留 {{key}}。」
```
- 对应 CLI：`--project --out --dict --rules --only --json`

### 4.2 `yanshou_docgen`（新增）

| 参数 | 类型 | 必填 | 默认 | 映射到 |
|---|---|---|---|---|
| `itemId` | string | ✅ | — | `--item`（`all` 或具体项） |
| `count` | number | ✗ | 1 | `--count` |
| `mode` | enum | ✗ | `template` | `--mode`（`template`/`blank`/`upload`/`skip`） |
| `overwrite` | boolean | ✗ | false | `--overwrite` |

```
description：
「按目录清单生成文档：有模板的套模板，无模板的按 mode 三选一
 （template 选一个备用模板 / blank 建空白 / upload 占位等用户传 / skip 跳过）。
 默认跳过已存在的文档，保护用户的编辑成果。确定性批处理，不调用模型推理。」
```
- 对应 CLI：`--project --item --count --mode --templates --out --overwrite --json`

### 4.3 `yanshou_fill`

| 参数 | 类型 | 必填 | 默认 | 映射到 |
|---|---|---|---|---|
| `outDir` | string | ✗ | 工程目录 | `--out` |
| `planPath` | string | ✗ | 运行时重算 | `--plan` |
| `anchor` | boolean | ✗ | true | `--anchor on/off` |

```
description：
「按 FillPlan 把值填进模板生成文档，逐份输出到工程目录。确定性批处理，不调用模型推理。
 缺值的占位符原样保留 {{key}} 并记入报告，绝不填空字符串。
 若已用 yanshou_datafill 生成过计划，传 planPath 复用，保证与预览一致。」
```

### 4.4 `yanshou_subtable`

| 参数 | 类型 | 必填 | 默认 | 映射到 |
|---|---|---|---|---|
| `docPath` | string | ✅ | — | `--doc` |
| `tableKey` | string | ✗ | 自动识别 | `--table`（8 选 1） |
| `dataFile` | string | ✗ | 从 `project.json._assets` 取 | `--data` |

8 个 `tableKey` 枚举：`deviceList` / `softwareList` / `testItemList` / `trialRunList` / `expertScoreList` / `documentList` / `documentChecklist` / `volumeList`

```
description：
「识别文档中的清单型表格，按表头列名匹配后接管数据行：数据不足则克隆行，多余则删除行。
 模板侧不含任何子表标记，识别完全靠表头列名序列 —— 所以不要改模板表头文字。」
```
> ⚠️ 子表**不进 MVP**（v2.0 §8.1 第 7 条），这个工具在 P3 阶段**可以先注册但不可用**，或干脆 P5 再加。建议：**先不注册**，避免模型选到它然后吃到「引擎脚本不存在」。

### 4.5 `yanshou_numbering`

| 参数 | 类型 | 必填 | 默认 | 映射到 |
|---|---|---|---|---|
| `item` | string | ✅ | — | `--item`（目录项名或 itemId，优先 itemId） |
| `action` | enum | ✗ | `allocate` | `--action`（`allocate`/`release`/`restore`） |
| `count` | number | ✗ | 1 | `--count` |
| `docNo` | string | ✗ | — | `--no` |
| `docId` | string | ✗ | — | `--doc-id` |

```
description：
「为文档分配/释放/恢复文档编号，格式 {合同编号}-{表名拼音缩写大写}-{流水号}，如 YYCZ-2026-0816-KGBSB-01。
 流水号在单个目录项内独立续排，删除只释放回本目录项的编号池，恢复取回原号。
 关键约束：编号在目录项内不重排 —— 删掉 02，03 仍然是 03。这是已打印纸质件的命根子。」
```

### 4.6 `yanshou_aggregate`

| 参数 | 类型 | 必填 | 默认 | 映射到 |
|---|---|---|---|---|
| `period` | enum | ✅ | — | `--period`（`week`/`month`） |
| `from` | string | ✗ | 上一自然周/月 | `--from` |
| `to` | string | ✗ | 上一自然周/月末 | `--to` |
| `outDoc` | string | ✗ | — | `--out` |

```
description：
「把施工日志按周/月聚合生成项目周报与月报。窗口内没有源日志时直接失败，不生成空文档。
 这是唯一需要模型参与生成的引擎：引擎负责取数与写入，模型的归纳在调用之前完成。」
```
> **这是唯一一个「模型前置生成正文、再交给引擎写入」的工具**。工具本身仍是确定性的。给模型的 description 要把这个分工说清楚，否则模型会以为调一次工具就自动生成正文了。

### 4.7 `yanshou_verify`

| 参数 | 类型 | 必填 | 默认 | 映射到 |
|---|---|---|---|---|
| `dir` | string | ✗ | 工程目录 | `--dir` |
| `level` | enum | ✗ | `block` | `--level`（`block`/`all`） |

```
description：
「导出前最后一道查错：扫描残留占位符、字典里没有的 key、日期字段是否被误填。
 返回阻断项与警告项清单。有 block 级问题时不要继续导出，先让用户补齐。」
```

### 4.8 工具注册顺序建议

注册顺序决定它们出现在模型提示词里的顺序（同类工具相邻更容易被正确选择）：

```
datafill → docgen → fill → numbering → verify → aggregate
（子表 subtable 留到 P5）
```

---

## 5. profile `yanshou` 完整配置

### 5.1 用哪套出厂 profile 打底（✅已实测确定）

**不要从空白建，也不要手动 insert。** 从出厂的 `sdk` 模板派生即可。

✅实测的出厂 profile 模板全清单（`--dump-default-config` 探测，2026-09-16）：

| 模板名 | 配置树行数 | 含 JSON-RPC server | 我们怎么用 |
|---|---|---|---|
| `web` | 539 | ❌ | 不用（自带浏览器 UI，我们自己有壳） |
| `headless` | 348 | ❌ | 备选（一次性运行器，无 server → 壳接不上） |
| **`sdk`** | **352** | **✅** | ✅ **就用它打底** |
| `sdk-minimal` | 140 | ✅ | 参考（不套 dsh-base，太素，缺工具与设置体系） |
| `acp` | 348 | ❌ | 将来做纯批量自动化再用 |
| ~~`tui` / `minimal`~~ | — | — | ❌ **不存在**（文档里提到过 `tui` 示例，本版运行时没有） |

✅实测 `sdk` profile 的层结构（`# ==` 层头）：

```
# == @deepseek-ai/dsh-base
# == @deepseek-ai/dsh-base, patched by @deepseek-ai/dsh-sdk-app     ← 多处
# == @deepseek-ai/dsh-base
# == @deepseek-ai/dsh-sdk-app                                       ← 末尾
- id: sdk-app-startup
  name: '@deepseek-ai/dsh-sdk-app'
  config:
    profile: sdk
- id: sdk-jsonrpc-server
  name: '@deepseek-ai/dsh-sdk-jsonrpc-server'
  inject: [sdkAppStartup, loader]
  config:
    maxTokensAsSuccess: !!js >-
      process.env.DSH_MAX_TOKENS_AS_SUCCESS === undefined ? true :
      JSON.parse(process.env.DSH_MAX_TOKENS_AS_SUCCESS)
```

**结论：`@deepseek-ai/dsh-sdk-app` 是一个"打补丁的组合包"，它只干两件事 —— 插 `sdk-app-startup` 和 `sdk-jsonrpc-server`。** 它同时也把 `system-prompt` 的行改成：

```yaml
- id: system-prompt
  name: '@deepseek-ai/dsh-system-prompt'
  config:
    personaSuffix: Your working directory is {{cwd}}.
    personaPrefix: You are a coding agent powered by the {{model}} model.
```

以及把 `session-title-llm` 置 `disabled: true`。

> **对我们的意义**：`system-prompt` 的这两个 persona 字段**我们大概率要改**（"你是一个验收资料助手"，不是"coding agent"）。这是一处**必须覆盖的行**，且按 patch 语义**要重述整行 config**。

### 5.2 profile manifest

`$DSH_HOME/profiles/yanshou/package.json`（`dsh plugin add` 会自动追加我们的 bundle）：

```json
{
  "dsh": {
    "profile": {
      "bundles": [
        "@deepseek-ai/dsh-base",
        "@deepseek-ai/dsh-sdk-app",
        "dsh-yanshou-docs"
      ],
      "patchReload": "live"
    }
  }
}
```

**顺序不能乱**：`dsh-base` → `dsh-sdk-app`（提供 JSON-RPC server）→ `dsh-yanshou-docs`（我们的）。后层按行胜出，我们的层在最后，所以能覆盖前面任何一行。

> ✅ **原来担心的「profile 有没有 JSON-RPC server」已排除** —— `sdk` 模板自带，不需要手动 insert。

### 5.3 我们的 patch 层（`cordis.patch.yml`，v0.2）

```yaml
# dsh-yanshou-docs 「组合包」配置层 · v0.2
#
# 层顺序（后层按行胜出，且 patch 替换目标行整个 config，不深合并）：
#   1. dsh.profile.bundles 所列各组合包 patch，按列表顺序（先是 dsh-base）
#   2. profile 自己的 cordis.patch.yml
#   3. $DSH_HOME/cordis.patch.yml（机器本地偏好）
#   4. 每个 --patch <path> overlay，按 argv 顺序

- insert:
    - id: yanshou-docs
      name: dsh-yanshou-docs
      config:
        # ── 双轨制目录 ──────────────────────────────
        # 安装资产根（只读）：templates / spec / engine / runtime
        installRoot: 'C:/Program Files/YanshouDocs/assets'
        # 工程数据根（可读写，用户可整包拷走）
        workspaceRoot: 'D:/验收资料/岳阳市财政局信息中心机房改造工程'
        # 当前工程（壳切换工程时由壳传入 --patch 覆盖）
        activeProject: 'D:/验收资料/岳阳市财政局信息中心机房改造工程'

        # ── 运行时（内嵌，不依赖系统 Python）──────────
        pythonBin: 'C:/Program Files/YanshouDocs/runtime/python/python.exe'
        engineRoot: ''      # 留空 = <installRoot>/engine

        # ── 模板保护 ────────────────────────────────
        protectedPaths:
          - 'templates'
          - 'templates_原始备份'
        allowWriteToTemplates: false

        # ── 其他 ────────────────────────────────────
        engineTimeoutMs: 600000

    # ── 模型默认值（按 id 覆盖 dsh-base 的行，必须重述整行 config）──
    - id: agent-default-model
      name: '@deepseek-ai/dsh-agent-default-model'
      config:
        provider: deepseek-official
        model: deepseek-flash          # ← 只写合法名，不写 deepseek-chat 别名

    # ── 系统提示词（覆盖 dsh-sdk-app 改过的那一行，必须重述整行）─────
    # dsh-sdk-app 默认写的是「You are a coding agent powered by ...」，
    # 那是给写代码的场景用的。我们是文档助手，必须换成自己的。
    - id: system-prompt
      name: '@deepseek-ai/dsh-system-prompt'
      config:
        personaPrefix: 「你是验收资料助手，负责按目录清单组织与生成工程验收文档。」
        personaSuffix: '当前工程目录是 {{cwd}}。不要修改 assets/templates 下的任何模板文件。'

    # ── 沙箱与审批（headless 场景，见 §9 风险 3）─────
    - id: sandbox-policy
      name: '@deepseek-ai/dsh-sandbox-policy'
      config:
        mode: 'workspace-write'
        workspaceRoot: 'D:/验收资料/岳阳市财政局信息中心机房改造工程'
```

**三条必须记住的 patch 语义**：

1. **patch 替换整行 `config`，不深合并**。所以覆盖 `agent-default-model` 时，`provider` 和 `model` **两个键都要写**，只写 `model` 会把 `provider` 抹掉。
2. **我们的层可以被用户覆盖**：用户在自己 profile 的 `cordis.patch.yml` 里按 `id: yanshou-docs` 重写 config 即可，不用改我们的包 → 所以默认值要给「用户大概率会保留的那套」。
3. **`!!js` 表达式可用**（dsh-base 自己就在用），例如 `!!js process.env.DSH_PERMISSION_MODE ?? 'workspace-write'` —— 但**我们的层尽量别用**，会让配置不可静态检查。

### 5.4 必须显式设置的两个环境变量

| 变量 | 值 | 为什么 |
|---|---|---|
| `DSH_HOME` | 安装目录下的 `dsh-home/` | 官方明确 `dsh` **要求非空且不回退 `~/.dsh`**；也保证不污染用户全局 |
| `DEEPSEEK_API_KEY` | 工头提供的 Key | 唯一凭据来源 |

可选：`DEEPSEEK_BASE_URL`（走代理时）、`DSH_PERMISSION_MODE`（见 §9 风险 3）。

> **`cwd` 也要对**：`sandbox-policy.workspaceRoot` 在 dsh-base 里是 `!!js process.cwd()`。**启动 dsh 时必须把 `cwd` 设为工程目录**，否则沙箱根目录会落在壳的安装目录上。这是最容易踩的一脚。

---

## 6. 壳 ↔ dsh 的契约

### 6.1 通道选择

只走 **`--profile sdk`（或含 sdk-app 的 yanshou profile）的 JSON-RPC**，**不用 dsh 的 UI 插件体系**。

理由（`A+装配式集成方案.md` §3.3 已论证）：一旦把编辑面板挂进 dsh 的 slot 体系，就和它的 UI 骨架绑死，它的破坏性变更会直接砸到脸上。只走最小契约面，升级风险被压缩到「agent 协议变了没有」。

### 6.2 进程模型

```
Electron 主进程
  └─ spawn(dsh 可执行文件)
       args:   --profile yanshou
       env:    DSH_HOME / DEEPSEEK_API_KEY / PYTHONIOENCODING=utf-8
       cwd:    <工程数据目录>          ← 关键，见 §5.3
       stdio:  ['pipe','pipe','pipe']
```

| 项 | 约定 |
|---|---|
| 传输 | stdio JSON-RPC（不上 TCP，避免端口占用与防火墙弹窗） |
| 一工程一进程 | 切工程时重启 dsh 进程（`cwd` 与 `workspaceRoot` 都要跟着换） |
| 日志 | stderr 原样落 `<DSH_HOME>/logs/壳-YYYYMMDD.log`，出问题第一时间看它 |
| 退出 | 壳退出时先发关闭请求，给 3 秒；超时 `taskkill /T /F` |

### 6.3 壳侧必须实现的三件事

| # | 事项 | 为什么 |
|---|---|---|
| 1 | **审批回调（approval channel）** | 见 §9 风险 3。不做，遇到需要审批的工具调用会**直接挂住** |
| 2 | **流式事件渲染** | 作业面板要显示「正在处理 25/37 份」——靠 `#PROGRESS` 行或 RPC 的流式事件 |
| 3 | **会话留痕落库** | dsh 的会话日志是追加式 JSONL（`<DSH_HOME>/sessions`），壳要能读出来做「谁、何时、改了哪份哪字段」的回放 |

---

## 7. P3 施工步骤（照序执行）

### 步骤 0 · 装运行时（✅本步已实测通过，实际耗时 1 分 46 秒）

```powershell
# 建一个专用 venv（隔离，不污染系统 Python）
python -m venv C:\YanshouBuild\runtime
C:\YanshouBuild\runtime\Scripts\python.exe -m pip install "deepseek-harness-sdk==0.1.5rc1"

# 设置隔离的 DSH_HOME（必须先建目录，dsh 要求非空）
$env:DSH_HOME = "C:\YanshouBuild\dsh-home"
New-Item -ItemType Directory -Force $env:DSH_HOME | Out-Null

# 导入凭据
$env:DEEPSEEK_API_KEY = "<工头给的key>"
```

**验收**：
- `C:\YanshouBuild\runtime\Scripts\dsh.exe --help` 能打出帮助文本，**退出码 0**
- `dsh.exe --version` 输出 **`0.1.5-rc.1`**
- 磁盘上 `runtime/` 目录约 **234 MB**（这是正常的，见 §2.4）

> ✅实测（2026-09-16）：这一步跑通无坑。72 MB wheel 下载 14.5 MB/s，5 秒下完；装完直接可用。
> **不需要装 Node.js** —— 用 `env -i PATH="<仅系统目录>" dsh --version` 可以自证（§10.2b 第 17 条）。
>
> ⚠️ **步骤 3 之前必须先让 pnpm 可用** —— 插件管理命令转发给 pnpm，没装会报 `dsh: pnpm failed in profile directory`。**只有装插件需要 pnpm，跑 profile 不需要。**

### 步骤 1 · 从出厂的 `sdk` 模板派生 profile（关键）

```powershell
# 以 sdk 为模板建 yanshou —— 这一步就同时解决了「JSON-RPC server 从哪来」
dsh --profile yanshou --from-default-profile sdk

# 确认 bundles 里已经有 dsh-base 与 dsh-sdk-app
Get-Content $env:DSH_HOME\profiles\yanshou\package.json
```

**验收**：
- `profiles/yanshou/` 目录生成，含 `package.json` / `cordis.patch.yml` / `pnpm-workspace.yaml`
- `package.json` 的 `dsh.profile.bundles` = `["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-sdk-app"]`

> ✅ **不要手动 insert `sdk-app`。** ✅实测：`dsh-sdk-app` 本身就是一个打补丁的组合包（它只插 `sdk-app-startup` + `sdk-jsonrpc-server` 两行），从 `sdk` 模板派生就自动拿到了。
> ❌ 也别用 `--profile yanshou` 直接裸启动 —— 那个 profile 不存在时会以空根初始化，**没有 JSON-RPC server，壳接不上**。
> 更别拿 `headless` 或 `acp` 当模板（✅实测：这两个都不含 JSON-RPC server）。

### 步骤 2 · 构建组合包 v0.2

```powershell
cd <包目录>\dsh-yanshou-docs
# 先按 §3.1–§3.6 改完代码
pnpm install
pnpm build          # 产出 lib/index.mjs
pnpm pack           # 产出 dsh-yanshou-docs-0.2.0.tgz
```

**验收**：`lib/index.mjs` 存在且体积合理（v0.1 是 12.19 kB，七个工具应该更大）。

### 步骤 3 · 装进 profile 并验证层生效

```powershell
dsh plugin --profile yanshou add .\dsh-yanshou-docs-0.2.0.tgz
dsh --profile yanshou --dump-config | Select-String -Pattern "dsh-yanshou-docs","yanshou-docs"
```

**验收**：`--dump-config` 输出里出现 `# == dsh-yanshou-docs` 层头 + `- id: yanshou-docs` 行。

> **必须用 tarball，不要用本地目录 `link:`** —— 2026-09-12 实测：Windows 上 `link:` 会产出**空目录**，dsh 解析不到包后退化成普通依赖，并打出**误导性警告**「declares no dsh.bundle」。看到这条警告，先去 `node_modules/<包名>/` 看文件在不在，别去改 manifest。
>
> ✅实测补充（2026-09-16）：`dsh plugin --profile <n> ...` 在 profile 不存在时会**先自动初始化**（打印 `dsh: initialized profile <n> at ...`），**然后**才因为找不到 pnpm 而失败并报 `dsh: pnpm failed in profile directory ...`。**但自动初始化的 profile 是以空根建的，不含 sdk-app** —— 所以顺序必须是「步骤 1 派生 → 步骤 3 装包」，不能指望 `plugin add` 顺手把 profile 建对。

### 步骤 4 · 首次启动 + 模型调用验证

```powershell
dsh --profile yanshou
# 在会话里输入：帮我看看这个工程的目录清单，一共有多少项
```

**验收（P3 的核心验收）**：
- 模型**选对工具**（应该调 `yanshou_verify` 或 `yanshou_datafill`，而不是瞎调）
- 工具**真的执行**，返回的不是「引擎脚本不存在」
- 模型能**正确解读**返回的契约摘要

### 步骤 5 · 模板保护验证（红线）

在会话里明确要求 AI：**「把 `assets/templates` 下的模板删掉一个 / 改一个」**

**验收**：被拒，且报错信息里含 `TemplateProtectionError` 与受保护路径列表。

### 步骤 6 · 抽身验证（A+ 的保险）

```powershell
dsh plugin --profile yanshou remove dsh-yanshou-docs
# 然后在纯命令行直接跑引擎
python <engineRoot>\fill_engine.py --project <工程>\project.json --out <输出目录>
```

**验收**：引擎与工程数据**一行没改照样能用**。这是「哪天弃用 dsh 也无所谓」的实证。

---

## 8. P3 验收清单（DoD）

| # | 验收项 | 判定方式 | level |
|---|---|---|---|
| 1 | 运行时能跑 | `dsh --help` 退出码 0 | block |
| 1b | **不依赖系统 Node** | `env -i PATH="<仅系统目录>" dsh --version` 仍返回版本号 | block |
| 2 | 层生效 | `--dump-config` 出现 `# == dsh-yanshou-docs` | block |
| 3 | **profile 从 `sdk` 模板派生** | `profiles/yanshou/package.json` 的 bundles = `[dsh-base, dsh-sdk-app, dsh-yanshou-docs]` | block |
| 3b | profile 含 JSON-RPC server | `--dump-config` 里有 `sdk-jsonrpc-server` 行 | block |
| 4 | 七个工具全注册 | 会话里问「你有哪些验收资料相关的工具」，模型能列全 | block |
| 5 | **模型选对工具、给对参数** | 用「不认识这项目的人」的视角提问，看它选得对不对 | block |
| 6 | **模板保护生效** | 让 AI 写 `assets/templates/**` → 被拒 + 明确报错 | block |
| 7 | **抽身验证通过** | 拔掉组合包，引擎与数据层一行不改仍可用 | block |
| 8 | 契约 JSON 被正确解析 | 工具返回里能看到 `stats` / `errors` 的结构化信息 | warn |
| 9 | 超时可配且能杀掉 | 故意把 `engineTimeoutMs` 设成 1000，看是否干净退出（无残留进程） | warn |
| 10 | 中文不乱码 | Windows 下引擎输出中文，壳里显示正常 | warn |
| 11 | 版本已钉死 | `package.json` 里 `@deepseek-ai/*` 无 `^` | warn |
| 12 | **系统提示词已换** | `--dump-config` 里 `system-prompt` 不再是「coding agent」那套 | warn |
| 13 | 模型名合法 | 配置里只有 `deepseek-flash` / `deepseek-v4-pro`，无别名 | warn |

---

## 9. 风险与降级

| # | 风险 | 严重度 | 对策 |
|---|---|---|---|
| 1 | dsh 是开发者预览，破坏性变更 | 高 | **钉死版本**（含 runtime-bin 的 `==` 绑定）；只走 sdk 最小契约面；升级前先在隔离 `DSH_HOME` 试 |
| 2 | **模型名静默路由**（§1.2） | 中 | 配置只写 `deepseek-flash` / `deepseek-v4-pro`；**上线前再次核对 `GET /models`** |
| 3 | **headless 下审批策略为 `ask` 会挂住** | **高** | 见下 §9.1 —— 这是 P3 最可能的卡点 |
| 4 | `sandbox-policy.workspaceRoot = process.cwd()` | 中 | 启动 dsh 时**必须**把 `cwd` 设成工程目录，否则沙箱根错位 |
| 5 | `dsh plugin` 依赖 pnpm | 低 | 只在打包机装 pnpm；终端用户不需要 |
| 6 | 组合包 TS 构建未实测 | 中 | 步骤 2 第一件事就是 `pnpm install && pnpm build`，早失败早修 |
| 7 | 全局保护钩子签名未确认 | 低 | 本阶段不开；工具内闸门已覆盖我们的 7 个工具 |
| 8 | 原生运行时 wheel 无 Windows arm64 | 低 | 目标平台 x64；真要 ARM 版回退 npm 路线 |
| 9 | 上游停更 / 转商业 | 中 | 抽身验证（步骤 6）就是保险：插件层薄 + 数据层不依赖 dsh → **拔掉即可** |
| 10 | **`dsh plugin add` 在 runtime-bin 的 `dsh` 上未实测** | 中 | 理论上与 npm 版同一上游实现，但**没跑过就不算**。步骤 3 一跑就知道；若不通，回退 npm 版 `dsh` 只用来**装插件**，运行时仍用 wheel（两者可混用，因为插件产物是纯 JS） |
| 11 | **交付包 ≈ 420 MB+** | 低 | ADR-18 的固有代价（234.6 MB 是 dsh 原生运行时）。**提前告知工头**，别到打包那天才发现 |
| 12 | 磁盘 pnpm 硬链接/软链在分发时失效 | 中 | pnpm 默认用全局 store + 符号链接。**打包前必须在 profile 的 `.npmrc` 里设 `node-linker=hoisted`**，否则拷到别的机器 `node_modules` 全断 |

### 9.1 风险 3 展开：审批通道

✅实测自 `--dump-config`：

```yaml
- id: approval
  name: '@deepseek-ai/dsh-user-approval'
  config:
    policy: !!js >-
      (process.env.DSH_PERMISSION_MODE ?? 'workspace-write') === 'danger-full-access'
        ? 'never' : 'ask'
```

**含义**：默认权限模式是 `workspace-write`，此时审批策略是 **`ask`** —— 也就是**要有人回答「准不准」**。

我们的壳是 headless 的（没有 dsh 的 UI）。**如果壳不实现审批回调，遇到需要审批的动作就会一直挂着。**

三条出路，**建议按 A 试、不行退 B**：

| 方案 | 做法 | 评价 |
|---|---|---|
| **A（推荐）** | 壳实现审批回调，弹窗问用户 | **最安全**，也符合「AI 动手前要人点头」的产品意图。审批结果顺带进留痕 |
| B | `DSH_PERMISSION_MODE=danger-full-access`（审批变 `never`） | 快，但**等于关掉安全阀**。且我们的工具本来就自己管路径，风险可控 —— 但**不推荐作为默认** |
| C | 用 profile patch 单独覆盖 `id: approval` 的行为 | 需要先知道它的 config 有哪些键，**P3 阶段先别猜** |

> **P3 步骤 4 之前先确认这一条**。否则会看到「模型选对了工具，但一直没动静」这种最难查的现象。

### 9.2 降级路径

若 P3 因任何原因卡住（dsh 侧问题、审批通道做不出来、构建链跑不通）：

**降级方案：壳直接调 Python 引擎，不接 dsh。**

- 引擎 CLI 与契约 JSON（`数据与规则规格.md` §3/§6）**本来就是按「不依赖 dsh」设计的**
- 壳把「调工具」换成「spawn 一次 `python xxx_engine.py`」，参数完全一样
- 代价：**丢掉 AI 能力**（AI 改写、日志归纳成周报），但**主流程一步不少**
- 而且这条降级**不需要改任何引擎代码** —— 这正是「插件层薄如纸」的回报

**建议：P3 与 P1/P2 并行做。** 万一 P3 拖了，P1/P2 的确定性内核照样往前推，不互相拖累。

---

## 10. 实测记录（2026-09-16，本机）

### 10.1 凭据与模型

| # | 验证内容 | 结果 |
|---|---|---|
| 1 | `GET /models` | ✅ 200，返回 **2 个模型**：`deepseek-flash` / `deepseek-v4-pro` |
| 2 | `POST /chat/completions` model=`deepseek-chat` | ✅ 200，但响应 `model` 字段 = **`deepseek-flash`**（静默路由） |
| 3 | `POST /chat/completions` model=`deepseek-reasoner` | ✅ 200，返回 `reasoning_content`，响应 `model` 仍是 `deepseek-flash` |

### 10.2 运行时分发形态

| # | 验证内容 | 结果 |
|---|---|---|
| 4 | PyPI `deepseek-harness-sdk` | ✅ 存在，`0.1.5rc1`，2026-09-10 发布，`requires_python >=3.10` |
| 5 | 其依赖 | ✅ `deepseek-harness-runtime-bin==0.1.5rc1` + `pydantic>=2.12,<3` |
| 6 | SDK wheel 体积 | ✅ **13,694 B**（纯 Python 外壳，本体在 runtime-bin） |
| 7 | runtime-bin Windows wheel 体积 | ✅ **72,045,733 B ≈ 68.7 MB**（压缩态） |
| 8 | runtime-bin 载荷性质 | ✅ 官方描述：把 dsh CLI 与**封闭的 Node 依赖树**打成**原生可执行文件**，**不需要系统 Node.js** |
| 9 | Windows 旁挂 | ✅ 含 `-rg.exe`（ripgrep，5.2 MB） |
| 10 | 平台覆盖 | ✅ Linux x64/arm64、macOS arm64/x64、Windows x64；**无 Windows arm64** |
| 11 | `DSH_HOME` 要求 | ✅ 非空，**绝不回退 `~/.dsh`** |

### 10.2b 端到端实装验证（✅ 2026-09-16 真跑，这是 ADR-18 的实证）

装了隔离 venv 实测，不是读文档。

| # | 验证内容 | 命令 | 结果 |
|---|---|---|---|
| 12 | **装得上** | `python -m venv ... && pip install deepseek-harness-sdk==0.1.5rc1` | ✅ 成功，72 MB wheel **14.5 MB/s 下完 5 秒**，总耗时 1 分 46 秒 |
| 13 | 实际拉起的依赖 | — | ✅ `deepseek-harness-runtime-bin 0.1.5rc1` / `pydantic 2.13.5` / `pydantic-core 2.46.5` / `annotated-types 0.8.0` / `typing-extensions 4.16.0` / `typing-inspection 0.4.4` |
| 14 | **落盘体积** | `ls -la .../runtime/` | ✅ 主程序 **240,529,920 B ≈ 229.4 MB** + rg.exe 5.2 MB = **≈ 234.6 MB** |
| 15 | **能跑** | `dsh --help` | ✅ exit=0，打出完整用法（"boot a DeepSeek Harness profile — an ordered stack of plugin-bundle patch layers under your own overrides"） |
| 16 | 版本 | `dsh --version` | ✅ **`0.1.5-rc.1`**（与 npm `latest` 通道一致） |
| 17 | **不依赖 Node.js（铁证）** | `env -i PATH="/c/Windows/System32:/c/Windows" dsh --version` | ✅ **返回 `0.1.5-rc.1`，exit=0** —— 环境清空、PATH 里一个 node 都没有，照样跑 |
| 18 | 出厂 profile 清单 | 逐个 `--profile <n> --dump-default-config` | ✅ `web`(539 行) / `headless`(348) / **`sdk`(352，含 JSON-RPC server)** / `sdk-minimal`(140，含) / `acp`(348)。**`tui` 与 `minimal` 不存在** |
| 19 | **`sdk` 是怎么拿到 RPC server 的** | `--dump-config` 看层头 | ✅ 层头 `# == @deepseek-ai/dsh-base, patched by @deepseek-ai/dsh-sdk-app`；`dsh-sdk-app` 层只插两行：`sdk-app-startup` + `sdk-jsonrpc-server` |
| 20 | `dsh-sdk-app` 还改了什么 | 同上 | ✅ 覆盖 `system-prompt`（personaPrefix="You are a coding agent…"）并把 `session-title-llm` 置 `disabled: true` |
| 21 | 无 pnpm 时的行为 | `dsh plugin --profile probe list` | ✅ 先打印 `dsh: initialized profile probe at ...`（**以空根初始化**），再报 `dsh: pnpm failed in profile directory ...` |
| 22 | sdk profile 全量配置树留档 | — | ✅ 352 行，存 `.workbuddy/tmp/dsh_sdk_profile.yml` |

**第 17 条是 ADR-18 的胜负手**：它证明「免 Node 运行时」不是宣传话术，是能实测复现的事实。

### 10.3 npm 侧（对比用）

| # | 验证内容 | 结果 |
|---|---|---|
| 12 | `@deepseek-ai/dsh` 版本通道 | ✅ `latest=0.1.5-rc.1`（2026-09-10）/ `next=0.1.5-rc.2` / `alpha=0.1.6-alpha.1` |
| 13 | 许可 | ✅ MIT |
| 14 | 直接依赖数 | ✅ **72** |

### 10.4 全量配置树事实（引自 2026-09-12 `--dump-config`）

| 项 | 实测值 |
|---|---|
| 默认模型 | `agent-default-model`: `provider: deepseek-official`, `model: deepseek-flash` ← **合法名，不用改** |
| 凭据插件 | `credentials` → `@deepseek-ai/dsh-credentials-local` |
| Key 注入范式 | `web-search-deepseek`: `apiKeyEnv: DEEPSEEK_API_KEY` |
| 沙箱 | `sandbox-policy`: `mode = DSH_PERMISSION_MODE ?? 'workspace-write'`, `workspaceRoot = process.cwd()` |
| 审批 | `approval`: `danger-full-access` → `never`，否则 `ask` |
| 工具注册表 | `tools` → `@deepseek-ai/dsh-tools` |
| 文件系统沙箱 | `fs-sandbox` → `@deepseek-ai/dsh-fs-sandbox` |
| Shell 工具 | `tool-bash`（win32 禁用）/ `tool-pwsh`（非 win32 禁用） |
| 会话日志 | `session-persistence-jsonl` → `root: dshHomePath('sessions')` |
| 内置工具 | `tool-workflow` / `tool-todo` / `tool-goal` / `tool-ralph` / `tool-web` / `tool-terminal` |

### 10.5 仍未实测的（如实标注）

| 项 | 状态 |
|---|---|
| 组合包 v0.2 的 TS 构建（tsdown）与加载 | ⬜ **未跑** —— 步骤 2 的第一件事 |
| `tools/pre-execute` 全局钩子的确切回调签名 | ⬜ **未确认** —— 保持注释状态，不凭猜测启用 |
| **审批回调的确切 RPC 形状** | ⬜ **未确认** —— 风险 3，P3 最可能的卡点 |
| 七个工具在真实会话里被模型调用 | ⬜ 未验证 —— 步骤 4 |
| `sdk` profile 下启动 JSON-RPC 后端并接入自建壳 | ⬜ 未验证 —— P4。**但 server 配置项已确认存在（§10.2b 第 18/19 条）** |
| 用真实 Key 跑一次完整 agent 轮次（工具调用 + 结果解读） | ⬜ 未验证 —— 步骤 4 |
| `dsh plugin add` 在 runtime-bin 的 `dsh` 上是否与 npm 版行为一致 | ⬜ **未验证** —— 步骤 3 会暴露。理论上一样（同一个上游实现），但要跑过才算 |
| ⛔ ~~runtime-bin 路线端到端（装 wheel → dsh 能跑）~~ | ✅ **已实测通过** —— 见 §10.2b |

---

## 11. 与既有文档的接口

| 你要什么 | 去哪找 |
|---|---|
| 为什么走 A+ 这条路 | `A+装配式集成方案.md` §1 |
| AI 层在整体架构里的位置 | `软件设计方案-v2.0.md` §2.1 |
| 引擎 CLI 参数与契约 JSON | `数据与规则规格.md` §3 / §6 |
| P3 在总计划里的位置 | `软件设计方案-v2.0.md` §6 / 本文 §7 |
| 施工怎么开始 | `施工交接说明.md` |
| 界面长什么样 | `界面线框图.html`（作业面板画板就是本文件 §6.3 的可视化） |

### 本文件带来的决策增量

| ADR | 内容 | 状态 |
|---|---|---|
| **ADR-18** | **运行时来源改用 `deepseek-harness-sdk`（Python wheel），不用 npm 全局安装** | ✅ 本文件定案，**且已端到端实测**（§10.2b：免 Node 跑通） |
| **ADR-19** | **模型只写合法名（`deepseek-flash` / `deepseek-v4-pro`），禁用别名；凭据走 `DEEPSEEK_API_KEY` 环境变量** | ✅ 本文件定案（依据 §1） |
| **ADR-20** | **壳必须实现审批回调（方案 A）**；`danger-full-access` 仅作调试后门 | ⏸ 待 P3 步骤 4 前确认（§9.1） |
| **ADR-21** | **`yanshou` profile 从出厂 `sdk` 模板派生**（`--from-default-profile sdk`），不手工 insert `sdk-app` | ✅ 本文件定案（依据 §5.1、§10.2b 第 18/19 条） |
| **ADR-22** | **覆盖 `system-prompt` 的 persona** —— dsh 默认给的是「coding agent」，我们是文档助手 | ✅ 本文件定案（依据 §5.1、§5.3），待步骤 4 实测效果 |

### 交付包体积的影响（因 ADR-18 而生）

| 项 | 体积 |
|---|---|
| Python 运行时（内嵌 venv） | ~35 MB（视精简程度） |
| **dsh 运行时（含 rg 旁挂）** | **≈ 234.6 MB** |
| 模板资产（37 份 docx） | 待测 |
| Electron 壳 | ~150 MB（典型） |
| **大头合计** | **≈ 420 MB+ （安装后）** |

> 这条要提前告诉工头：**这个软件装完是 400MB 量级的**。不是设计失误，是「把 Node 依赖树打进单文件原生程序」换来的「免装 Node」的代价。若嫌大，唯一的替代是用 npm 路线（更小但要求用户装 Node）—— 不划算。
