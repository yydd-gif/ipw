# A+ 装配式集成方案（dsh 接入）

> 定稿：马仔B ｜ 日期：2026-09-12 ｜ 状态：**工头已认可 A+，本文为落地设计**
> 上位文档：`规范/技术选型-DeepSeek Harness评估.md`（路线对比与选型依据）
> 官方依据：`05_参考文档/dsh-docs/`（8 份架构文档 + 8 份插件开发文档 + 实测证据，均为官方原文）

---

## 0. 一句话

**dsh 以「官方 profile + 外部组合包」的形式接入，不改它一行源码。** 我们自建桌面壳与编辑内核，dsh 只当无界面的能力后端；**七块确定性引擎**打包成一个 dsh 组合包，注册成**七个工具**。

---

## 1. 为什么这条路的机制是成立的（不是猜的）

全部来自官方 `docs/user/develop/` 下给**外部插件作者**写的教程，不是仓库内部开发文档。

### 1.1 插件的最小形态

一个插件就是一个导出 `apply` 的 TypeScript 模块：

```ts
import type { Context } from '@deepseek-ai/cordis'

export const name = 'my-plugin'
export function apply(ctx: Context) {
  // 在这里通过 ctx 注册能力
}
```

就这么多。还支持对象形式与类形式（类形式用于向别的插件提供服务）。

### 1.2 依赖声明与自动清理

```ts
export const name = 'my-tool-plugin'
export const inject = ['tools']        // 框架会等 tools 就绪后才加载本插件

export function apply(ctx: Context) {
  ctx.tools.register(/* ... */)
}
```

> 官方原话：**「通过 `ctx` 注册的任何东西——事件监听、工具、定时器——在插件卸载时都会被自动清理。你不需要手动 removeListener 或 clearInterval。」**
> 需要手动释放的资源（如常驻连接）用 `ctx.effect(() => { ...; return () => cleanup() })`。

这条对我们很关键：**插件层不需要写资源管理代码，卸载即回收**，热替换不会残留旧注册。

### 1.3 工具注册（`defineTool`）

```ts
import { defineTool } from '@deepseek-ai/dsh-tools'

ctx.tools.register(defineTool({
  name: 'greet',
  description: 'Greet someone by name.',
  parameters: {
    name: { type: 'string', required: true, description: 'The name to greet' },
  },
  output: {
    schema: { type: 'string' },
    render: (_args, value) => [{ type: 'text', text: value }],
  },
  async execute(args) {
    return `Hello, ${args.name}!`
  },
}))
```

`defineTool` 根据 `parameters` 推导并校验 `args`；`execute` 返回 `output.schema` 声明的规范值，`output.render` 把它转成面向模型的内容。

### 1.4 插件配置（Schemastery）

```ts
export interface Config {
  greeting: string
  maxRetries: number
}
export const Config: Schema<Config> = Schema.object({
  greeting: Schema.string().default('Hello'),
  maxRetries: Schema.number().default(3),
})
export function apply(ctx: Context, config: Config) { /* ... */ }
```

官方两条设计约定（我们照办）：
- **无硬编码可调参数** —— 检验标准：「能否在 `cordis.yml` 中改变这个值，而不需要修改代码？」
- **配置错误要响亮** —— 把约束写进 schema，让非法配置在插件加载时直接失败

### 1.5 打包与安装（这是 A+ 的命门）

**两个概念，两种 manifest：**

| | 是什么 | manifest | 回答的问题 |
|---|---|---|---|
| **组合包** bundle | 附带一个配置层的 npm 包 | `dsh.bundle` | 这个包贡献什么？ |
| **profile** | `$DSH_HOME/profiles/<name>` 下的可启动组合 | `dsh.profile` | 这套配置由哪些组合包按什么顺序组成？ |

组合包是我们写并分发的；profile 是用户用 `dsh --profile <name>` 启动的。**没有东西同时是两者。**

我们的组合包结构：

```
dsh-yanshou-docs/
├── package.json       # 声明 dsh.bundle
├── cordis.patch.yml   # 本包贡献的配置层
└── lib/index.mjs      # patch 行引用的插件模块（tsdown 构建产物）
```

```json
{ "name": "dsh-yanshou-docs", "type": "module", "main": "lib/index.mjs",
  "files": ["lib", "cordis.patch.yml"],
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } } }
```

```yaml
- insert:
    - id: yanshou-docs
      name: dsh-yanshou-docs
```

**注意**：组合包里的 patch 行按**包名**引用（不是相对源码路径），这样 Node 的模块解析才找得到已安装的代码。

### 1.6 四层加载顺序（必须记牢）

生效配置在空根之上逐层组合：

1. profile 的 `dsh.profile.bundles` 所列各组合包 patch，**按列表顺序**（先是 `@deepseek-ai/dsh-base`）
2. profile 自己的 `cordis.patch.yml`
3. home 级的 `$DSH_HOME/cordis.patch.yml`
4. 每个 `--patch <path>` overlay，按 argv 顺序

**后层按行胜出，且 patch 替换目标行的整个 `config`，不深合并。** 推论：
- 我们的 patch 可以按 `id` 覆盖前面各层的行，但**必须重述该行需要的每一个键**，不能只写改动的那个
- 用户可以在自己 profile 的 `cordis.patch.yml` 里覆盖我们的行，**无需改动我们的包** → 所以配置默认值要给「用户大概率会保留的」那一套

### 1.7 安装、验证、移除

```sh
dsh plugin --profile yanshou add ./dsh-yanshou-docs-0.1.0.tgz   # 转发给 pnpm
dsh --profile yanshou --dump-config                             # 应看到 "# == dsh-yanshou-docs" 层
dsh --profile yanshou
dsh plugin --profile yanshou remove dsh-yanshou-docs            # 依赖与层一并移除
```

### 1.8 profile 模板

随发行版交付 `web` / `headless` / `sdk` / `sdk-minimal` / `acp`：

| profile | 用途 | 我们怎么用 |
|---|---|---|
| `web` | 浏览器 UI（`dsh web` 是它的别名） | 不用 —— 我们自己有壳 |
| `headless` | 不带服务器的一次性运行器 | 备选 |
| **`sdk`** | **SDK JSON-RPC 服务器** | **✅ 我们自己桌面壳接这个** |
| `sdk-minimal` | 显式最小 SDK 配置树（不套 `dsh-base`） | 参考 |
| `acp` | Agent Client Protocol 服务器（纯自动化） | 将来做批量自动化用 |

---

## 2. 分发方式：选 tarball，不选 git

官方给了三条路，只有一条适合我们：

| 方式 | 代价 | 判定 |
|---|---|---|
| `dsh plugin add github:you/repo` | 拉的是**源码不是产物**，作者必须提供 `prepare` 脚本；pnpm ≥10 默认拒绝跑 git 依赖的 prepare，用户要在 `pnpm-workspace.yaml` 里写 `allowBuilds` 授权 —— **等于允许该包在安装时于用户机器上执行代码，且不在沙箱内** | ❌ 弃 |
| 发布 npm | 需要注册表账号与发布流程；对内部工具过重 | ⏸ 备选 |
| **`pnpm pack` → `.tgz`** | **装的是预构建代码，用户无需任何构建授权**；可离线交付（U 盘 / 内网） | ✅ **选它** |

官方原文明确：「如果不想让用户做这项授权，就改为分发构建产物 —— 发布到 npm，或交付 tarball。」

### 2.1 补充：dsh 本体从哪来（ADR-18，2026-09-16 定案）

上面说的是**我们的组合包**怎么分发。**dsh 本体**的获取方式本轮也改了：

| | 路线 N（原方案，npm） | 路线 P（新方案，Python wheel）★ |
|---|---|---|
| 获取 | `npx @deepseek-ai/dsh` / 全局安装 | `pip install deepseek-harness-sdk` |
| 需要 Node.js | ✅ 必须（≥22.19） | ❌ **不需要**（已实测） |
| 体积 | 仓库 183MB / 72 依赖 | wheel 68.7MB，落盘 234.6MB |

**结论：改用 `deepseek-harness-sdk`。** 完整依据、实测数据与代价见 `P3-AI层接入施工图.md` §2 / §10.2b。

> 注意：**装插件仍需 pnpm**，但这是**打包机**上的一次性动作；终端用户跑已装好的 profile 不需要 pnpm。

---

## 3. 本项目的落地形态

### 3.1 分层

```
┌────────────────────────────────────────────────────────────────┐
│  自建桌面壳（Electron / Tauri）                                 │
│  Ribbon · 左侧三页签树 · 编辑区 · 打印预览 · 导出 · 回收站       │  ← 自建
│  编辑内核：docx 所见即所得 + 行列标 + 打印 + 已打印标记          │  ← 自建（命根子）
└───────────────────────┬────────────────────────────────────────┘
                        │ 本地 IPC（127.0.0.1 JSON-RPC 或 stdio）
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  dsh --profile yanshou  （headless 后端，upstream 一行未改）     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ @deepseek-ai/dsh-base                                    │  │
│  │  模型适配 · 工具注册表 · 沙箱与审批 · 会话日志 · 设置 · 凭据│  │  ← 官方提供
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ dsh-yanshou-docs（我们的组合包，树外）                     │  │  ← 只做接线
│  │   tools: yanshou_fill / _verify / _subtable /            │  │
│  │          _numbering / _aggregate                         │  │
│  │   policy: 模板保护（拒绝写 模版/**）                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────┬────────────────────────────────────────┘
                        │ spawn（argv 传参，不用 shell）
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  Python 引擎层  assets/engine/*.py                             │  ← 真正干活，已部分跑通
└───────────────────────┬────────────────────────────────────────┘
                        ▼
        工程文件夹（project.json + 8 分册 docx + 附件）  ← 不依赖 dsh，可整包拷走
```

### 3.2 为什么插件层要「薄如纸」

引擎是 Python 写的、已经验证过（填充引擎实测 1 秒 37 份、171/171 命中、零残留）。
插件层只做三件事：**校验参数 → spawn 一次子进程 → 把 stdout 回成工具结果**。

三个好处：
1. 已验证的代码为了换运行时重写，是纯粹的浪费
2. 确定性批处理必须 100% 可复现，Python 侧已经做到
3. **将来弃用 dsh，这一层整片扔掉即可**，Python 引擎与工程文件夹数据模型一行不改 → 抽身成本≈0

### 3.3 编辑区为什么不走 dsh 的 UI 通道

dsh 有完整的 Host/Client RPC 层（`api-gateway` + 各 Remote controller）和 50+ 个 `ui-*` 插件。
我们**刻意不用**，理由：

- 我们要的编辑能力（Word 级所见即所得、行列标、打印预览、已打印标记）dsh 一样没有，自建壳里做
- 一旦把编辑面板挂进 dsh 的 slot 体系，就和它的 UI 骨架绑死，**它的破坏性变更会直接砸到我们脸上**
- 只走 `--profile sdk` 的 JSON-RPC 通道，**契约面最小** —— 升级风险被压缩到「agent 协议变了没有」

这条是整个 A+ 的风险控制核心。

### 3.4 七块引擎 → 七个工具

> **2026-09-16 修订**：v2.0 把引擎从 5 块扩到 7 块（新增 `datafill` 取值装配与 `docgen` 文档生成）。完整工具签名见 `P3-AI层接入施工图.md` §4。

| 工具名 | 引擎脚本 | 状态 |
|---|---|---|
| `yanshou_datafill` | `datafill_engine.py` 取值装配 → FillPlan | ⬜ **新增**（P3 补） |
| `yanshou_docgen` | `docgen_engine.py` 建档 / 一键成册 / 无模板三选一 | ⬜ **新增**（P3 补） |
| `yanshou_fill` | `fill_engine.py` 模板填充 | ✅ 引擎已跑通（37 份 / 171 处 / 零残留） |
| `yanshou_verify` | `verify_engine.py` 导出前查错 | ⏳ 待从 `tools/verify_placeholders.py` 收编 |
| `yanshou_subtable` | `subtable_engine.py` 清单表按表头接管数据行 | ⏳ 待建（**不进 MVP**，建议 P3 先不注册） |
| `yanshou_numbering` | `numbering_engine.py` 编号分配 | ⏳ 待建 |
| `yanshou_aggregate` | `aggregate_engine.py` 日志→周报→月报 | ⏳ 待建 |

**为什么 `datafill` 与 `fill` 要拆成两个工具**：`datafill` 只算不写盘，产出 FillPlan 供用户**预览取值是否正确**；`fill` 拿同一个 FillPlan 落地。拆开才能做到「先看后填」，合成一个就是黑盒了。

### 3.5 模板保护（从口头规矩变硬机制）

铁律：**AI 绝不写 `模版/` 下的 docx**。这条曾经被破过一次，所以分两层落实：

1. **确定性一层（现在就有效）** —— `src/policy.ts` 的 `assertWritable()`，所有写盘工具动手前先过闸；命中受保护目录抛 `TemplateProtectionError`
2. **全局一层（待启用）** —— `tools/pre-execute` waterfall 事件拦截，可覆盖到别的插件注册的工具。官方架构文档记载了该事件存在与语义，但**确切回调签名需真机确认后再启用** —— 不凭猜测写跑不通的代码

同时 `ctx.sandbox` 是官方记录的「限制所启动的进程」seam，将来可把 Python 子进程也纳入沙箱后端统一管控。

### 3.6 留痕

dsh 的会话日志是**追加式、带版本（`session.vN.jsonl[.zstd]`）、有迁移链**，并且「**模型可见即已记录**」是一条运行时不变量。这意味着「谁、何时、改了哪份哪字段」天然可回放 —— 验收资料要的正是这个，将来能拿给甲方看。

---

## 4. 边界：明确不做什么

| 不做 | 原因 |
|---|---|
| 不 fork dsh 源码 | 见评估文档：fork 换不来核心价值，且要永久接管一个 183MB / 55 包的框架 |
| 不改 `tsconfig.*.json` / 不往 `packages/` 塞包 | 那属于仓库内开发（路线 C），会让升级变成 rebase |
| 不用 dsh 的 `ui-*` 插件体系搭编辑器 | 会把我们绑死在它的 UI 骨架上，破坏性变更全部直击 |
| 不把一键成册交给模型推理 | 输入固定、输出唯一的批处理，交给 LLM 是几十次推理 + 不确定性；项目名称填错要返工 |
| 不从 git 安装插件 | 安装期执行代码 + 需用户授权，供应链风险 |

---

## 5. 落地阶段

> **2026-09-16 修订**：本文的阶段划分已与 v2.0 的 `P0–P7` 对齐。下表保留 A+ 视角的阶段编号，括号内是对应的 P 编号。

| 阶段 | 内容 | 前置 | 状态 |
|---|---|---|---|
| **0**（P1） | 引擎 1 填充引擎（Python） | ✅ 已完成 | ✅ |
| **1 · 分水岭**（**P3**） | **把引擎接进 dsh**：从 `sdk` 模板派生 profile → 构建组合包 v0.2 → `pnpm pack` → `dsh plugin add` → `--dump-config` 验证层 → 跑通工具调用 | 装运行时、**模型 API Key** | 🔶 **Key 已给、运行时可装、步骤已细化 → 可动工** |
| 2（P2） | 收编引擎 2 残留校验（`verify_placeholders.py` → `verify_engine.py`） | 不依赖阶段 1 | ⬜ |
| 3（P5） | 建引擎 3 子表识别（8 张清单表按表头列名接管数据行） | 阶段 2 | ⬜ |
| 4（P2） | 建引擎 4 编号引擎（`{合同编号}-{缩写}-{流水号}`，目录项内续排 + 编号池） | 阶段 2 | ⬜ |
| 5（P5） | 建引擎 5 自动汇总，试点「施工日志 → 周报 → 月报」 | 阶段 4 | ⬜ |
| 6（P4） | 自建桌面壳接 `dsh --profile yanshou` 的 JSON-RPC | 阶段 1 | ⬜ |

**阶段 1 是分水岭**：跑通了，A+ 就从设计变成事实。

> **注意排序上的修正**：阶段 2/4（确定性引擎）**不依赖阶段 1**，可并行先做。这是 v2.0「先把确定性内核做扎实，再上界面」原则在 A+ 视角下的体现。

---

## 6. 风险控制


| 风险 | 对策 |
|---|---|
| dsh 是开发者预览，会有破坏性变更 | **钉死版本**（`package.json` 里 `@deepseek-ai/*` 依赖按实际安装版本锁定，不用 `^` 范围）；只走 `--profile sdk` 最小契约面 |
| 上游哪天变商业 / 停更 | 插件层薄 + 数据层不依赖 dsh → **拔掉即可**，换一层薄 LLM 调度 |
| 插件安装引入供应链风险 | 只用 tarball 分发，不用 git 安装，**不引入任何需要 `allowBuilds` 授权的包** |
| 原生模块构建（`node-pty` 等）在 Windows 上卡住 | 我们只用 headless / sdk profile，不需要桌面端与终端功能，避开原生编译 |
| Issue 通道关闭，踩坑无处反馈 | 官方 Discussions + 本地归档官方文档（`05_参考文档/dsh-docs/`）自查 |

---

## 7. 实测验证记录（2026-09-12，真机）

不是照文档抄，是真跑了一遍。环境：Node v22.22.2 / npm 10.9.7 / pnpm 12.4.1（本地装），隔离 `DSH_HOME`。

### 7.1 通过项

| # | 验证内容 | 结果 |
|---|---|---|
| 1 | `npx @deepseek-ai/dsh --help` | ✅ **exit=0**，CLI 真能跑 |
| 2 | 帮助文本是否印证四层加载顺序 | ✅ 官方原话：「boot a DeepSeek Harness profile — **an ordered stack of plugin-bundle patch layers under your own overrides**」 |
| 3 | `--patch <path>` / `--dump-config` / `dsh plugin` | ✅ 三个都在，`--patch` 标注可重复 |
| 4 | `dsh plugin --profile <n> add <spec>` | ✅ 自动初始化 profile 并转发 pnpm |
| 5 | **tarball 安装 → 层自动生效** | ✅ **`dsh.profile.bundles` 自动追加 `dsh-probe-plugin`** |
| 6 | `--dump-config` 是否显示自定义层 | ✅ 出现 `# == dsh-probe-plugin` 层头 + `- id: hello / name: dsh-probe-plugin` 行 |
| 7 | 安装后 `node_modules/<pkg>/` 实体是否到位 | ✅ `package.json` / `index.js` / `cordis.patch.yml` 三个文件齐全 |

**实测输出（`--dump-config` 尾部）：**

```yaml
- id: llm-deepseek
  name: '@deepseek-ai/dsh-llm-deepseek'
# == dsh-probe-plugin          ← 我们自己的层
- id: hello
  name: dsh-probe-plugin       ← patch 行生效
```

**profile manifest（`dsh.profile.bundles` 被自动追加）：**

```json
{ "dsh": { "profile": { "bundles": ["@deepseek-ai/dsh-base", "dsh-probe-plugin"], "patchReload": "live" } } }
```

### 7.2 踩到的坑（重要）

**`link:` 本地路径安装在 Windows 上不可用。**

用 `dsh plugin --profile probe add ./hello-plugin`（本地目录，pnpm 记成 `link:`）时：

- pnpm 报告成功：`+ dsh-probe-plugin link:../../../hello-plugin` / `Done in 5.8s`
- 但 `node_modules/dsh-probe-plugin/` 是个**空目录**，`package.json` 不存在
- dsh 于是解析不到包，退化成「普通依赖」，并打出一句**误导性警告**：
  ```
  warning: dsh-probe-plugin declares no dsh.bundle — installed as a plain dependency, not a profile layer
  ```

**根因**（读 dsh 源码定位，`@deepseek-ai/dsh-app-boot`）：

```js
function resolveBundleDir(binName, packageName, installAnchor, profileDir) {
  for (const anchor of [installAnchor, join(profileDir, "package.json")]) {
    const dir = packageDirFromAnchor(anchor, packageName);
    if (dir !== void 0) return dir;
  }
  throw new Error(`${binName}: cannot resolve profile bundle ...`);
}
function exportsPatch(packageName, profileDir) {
  let dir;
  try { dir = resolveBundleDir(NAME, packageName, INSTALL_ANCHOR, profileDir); }
  catch { return false; }          // ← 解析失败被吞掉
  return readProfileManifest(NAME, dir).dsh?.bundle?.patch !== void 0;
}
```

解析失败被 `catch` 吞掉后返回 `false`，于是上层把它当成「这个包没声明 `dsh.bundle`」——
**警告文本与真实原因不符**。真因是链接为空，不是 manifest 写错。以后碰到这条警告，先去 `node_modules/<pkg>/` 看文件在不在。

**结论：改用 tarball 安装后，一切正常。** 这反向验证了本文 §2 的决策 —— tarball 不只是「避开 git 的构建授权风险」，也是 Windows 上**唯一稳妥**的安装方式。

> **对 A+ 的实践指导**：
> - ✅ 分发用 `pnpm pack` → `.tgz` → `dsh plugin add ./x.tgz`
> - ❌ 不用 `link:` 本地目录（Windows 空目录）
> - ❌ 不用 `github:` 直装（构建授权 + 供应链风险）
> - 首次跑 `dsh plugin` 前必须**先确保 pnpm 可用**，否则 dsh 会直接报 `pnpm failed in profile directory`

### 7.3 顺带拿到的关键事实

`--dump-config` 吐出完整真实配置树（**335 行**，已留档），确认了几个要点：

| 项 | 实测值 |
|---|---|
| 工具注册表 | `id: tools` → `@deepseek-ai/dsh-tools`（与 `defineTool` 的导入路径一致） |
| 沙箱 | `id: fs-sandbox` → `@deepseek-ai/dsh-fs-sandbox` |
| 模型适配 | `id: llm-deepseek` → `@deepseek-ai/dsh-llm-deepseek` |
| **模型 Key 注入方式** | `web-search-deepseek` 的 config 是 **`apiKeyEnv: DEEPSEEK_API_KEY`** → **走环境变量，不写进配置** |
| 内置工具 | `tool-workflow` / `tool-todo` / `tool-goal` / `tool-ralph` / `tool-web` / `tool-terminal`（见完整树） |
| profile 目录落盘 | `package.json` + `cordis.patch.yml`（用户层）+ `cordis.yml` + `pnpm-workspace.yaml` + `node_modules/` |

**留档位置**：`05_参考文档/dsh-docs/30-真实配置树-web-profile.yml`、`31-真实配置树-含自定义插件层.yml`、`32-自定义插件层片段.yml`、`33-profile-manifest-实例.json`

### 7.4 仍未验证的（如实标注）

| 项 | 状态 | 2026-09-16 更新 |
|---|---|---|
| 组合包骨架 `dsh-yanshou-docs` 的 TS 构建（tsdown）与加载 | 未跑 | ⬜ 仍待跑 —— 见 `P3-AI层接入施工图.md` §7 步骤 2 |
| `tools/pre-execute` 全局钩子的确切回调签名 | 未确认 | ⬜ 仍待确认 → `policy.ts` 保持注释状态 |
| 在 `sdk` profile 下启动 JSON-RPC 后端并接入自建壳 | 未验证 | 🔶 **部分解决**：`sdk` profile 的 `sdk-jsonrpc-server` 配置项已确认存在；接壳留 P4 |
| 模型实际调用工具（需 API Key） | 未验证 | 🔶 Key 已到位，⬜ 待跑一次完整轮次 |

**2026-09-16 新增验证（详见 `P3-AI层接入施工图.md` §10）**：

| 项 | 结果 |
|---|---|
| 模型 API Key 连通性 | ✅ `GET /models` 200；实际可用模型只有 **`deepseek-flash` / `deepseek-v4-pro`** |
| ⚠️ 模型别名静默路由 | ✅ `deepseek-chat` / `deepseek-reasoner` 请求会被静默路由到 `deepseek-flash`（响应体 `model` 字段为证）→ **配置里只写合法名** |
| **dsh 运行时改用 Python wheel（ADR-18）** | ✅ 装 `deepseek-harness-sdk==0.1.5rc1` 成功；**`env -i` 清空环境、PATH 无 node，`dsh --version` 照样返回 `0.1.5-rc.1`** → **免 Node.js 实测成立** |
| 运行时体积 | ✅ wheel 68.7 MB（压缩）/ **234.6 MB（落盘）** |
| 出厂 profile 模板 | ✅ 实测存在 `web` / `headless` / **`sdk`（含 JSON-RPC server）** / `sdk-minimal` / `acp`；**无 `tui` / `minimal`** |
| `sdk` 如何拿到 RPC server | ✅ 层头 `patched by @deepseek-ai/dsh-sdk-app`；该包只插 `sdk-app-startup` + `sdk-jsonrpc-server` 两行 → **从 `sdk` 模板派生即可** |

---

## 8. 待工头拍板

1. ~~**要不要现在做阶段 1？** 需要你给一个模型 API Key~~ → ✅ **2026-09-16 已给，已实测连通，P3 可动工**
2. 阶段 1 跑通后，**引擎建序是否按 2→3→4→5** 走？（我建议按此序，引擎 2 最轻且马上有用）—— **仍待拍板**

> 📐 **阶段 1（= P3）已细化到可施工**：`01_设计文档/P3-AI层接入施工图.md`（7 步命令 + 13 项 DoD + 9 条风险 + 实测记录）。

---

## 附：产物清单

> ⚠️ **路径已按打包后的实际目录更新**（2026-09-16）。旧文档里写的 `.workbuddy/engine/`、`.workbuddy/ref/` 已被重命名，别按旧路径找。

| 路径 | 说明 |
|---|---|
| `04_AI组合包/dsh-yanshou-docs/` | 组合包骨架（11 个源文件，按官方 API 撰写；**已构建通过**） |
| `04_AI组合包/dsh-yanshou-docs/_verified/` | 构建留档：`index.mjs`（12.19 kB）+ `dsh-yanshou-docs-0.1.0.tgz`（8777 B） |
| `05_参考文档/dsh-docs/` | 官方文档 + 实测证据归档 **25 份**（架构 8 + 插件开发 13 + 实测证据 4） |
| `05_参考文档/dsh-docs/30~33-*` | 真实配置树与 profile manifest 留档 |
| `01_设计文档/技术选型-DeepSeek Harness评估.md` | 路线对比与选型依据 |
| **`01_设计文档/P3-AI层接入施工图.md`** | **本次新增**：AI 层施工图（凭据 / 运行时 / 组合包变更 / 工具签名 / profile / 契约 / 步骤 / DoD / 风险） |
| `.workbuddy/tmp/dsh_sdk_profile.yml` | **本次新增**：`sdk` profile 的全量配置树（352 行，实测导出） |
| `.workbuddy/secrets/DEEPSEEK.env` | 模型凭据（**不在交付包范围内**，勿随方案外发） |
