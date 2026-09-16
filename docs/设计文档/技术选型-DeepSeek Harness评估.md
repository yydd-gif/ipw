# 技术选型评估：DeepSeek Harness 当底座（v2 · 含路线对比）

> 评估：马仔B ｜ 日期：2026-09-12 ｜ v1 结论曾判「不可当整机底座」→ **v2 实地核验后更正**
> 触发：工头问「如果以 deepseek harness 为底座怎么样」→ 追问「如果是二次开发 deepseek harness 对比路线A呢」
>
> **✅ 2026-09-12 工头拍板「A+ 不错」—— 采纳路线 A+（装配式二次开发）。落地设计见 `规范/A+装配式集成方案.md`。**

---

## 0. 一句话结论

**dsh 不是"命令行套壳"，是一个自带 Electron 桌面端 + 插件化 UI 框架 + Host/Client RPC + 多语言 SDK 的完整平台。** v1 里我写"只有对话式 Web UI / CLI，Ribbon、目录树、编辑区一样都给不了" —— **这句是错的，向工头认。**

更正后的准确说法是两句话：

1. **它白送的是「工作台外壳」** —— 桌面窗口、侧栏、布局、主题、i18n、设置面板、插件管理器、打包/签名/自动更新流水线、Agent 循环、权限沙箱、会话留痕、模型适配。
2. **它给不了的是「编辑内核」** —— Word 级所见即所得编辑、行列标、打印预览、已打印/未打印标记、PDF/图片导出。**而这一块恰好是这个软件的命根子。**

→ 所以结论不变但理由全变：**不走真 fork（路线 C），走「装配式二次开发」（路线 A+）** —— 用官方 profile + 外部插件包扩展，**不改 upstream 一行源码**，照样吃到 dsh 的外围基建。

---

## 1. 先认错：v1 的两处硬伤

| v1 的说法 | 实情 | 性质 |
|---|---|---|
| 「只有对话式 Web UI / CLI」 | `apps/` 下有 **四个真应用**：`cli` / `web` / `desktop`（**Electron**）/ `desktop-host` | ❌ 事实错误 |
| 「Ribbon、目录树、编辑区… dsh 一样都给不了」 | UI 是**插件化的**：`packages/client/` 下 **50+ 个 `ui-*` 包**，含 `ui-sidebar` / `ui-sidebar-files` / `ui-dockkit` / `ui-layout` / `ui-theme` / `ui-brand-official`；插槽机制 `ui-slots`（single / list / keyed / chain 四种组合）+ `ui-renderer`（React） | ⚠️ 部分错误：**框架白送，编辑内核仍缺** |

v1 错在**只看了 npm 发布包**（那确实只是个 17KB 引导壳），没进 GitHub 仓库看 `apps/` 和 `packages/client/`。这轮补齐了。

---

## 2. 实地核验：dsh 的真实架构（新证据）

### 2.1 四个应用

| 应用 | 形态 | 备注 |
|---|---|---|
| `apps/cli` | 命令行 | npm 分发的入口 |
| `apps/web` | Vite 浏览器应用 | `dsh web` → `127.0.0.1:3080` |
| **`apps/desktop`** | **Electron 桌面端** | `electron-builder.config.mjs`；**不开放任何端口**，走 `dsh-app://` 协议 + 分帧字节管道；自带 electron-updater |
| `apps/desktop-host` | 桌面私有 Host 进程 | 跑在内置上游 Node.js 里 |

### 2.2 插件化 UI（`packages/client/`，50+ 包）

`ui-slots` 是扩展点核心：客户端插件把组件注册进父级已声明的 slot，四种 kind —— `single` / `list` / `keyed` / `chain`。**声明即认领**，加载期做类型检查与冲突检查，卸载时递归回收。

可直接复用的现成面板：`ui-sidebar`（侧栏骨架）、`ui-sidebar-files`（文件树）、`ui-sidebar-documentpreview`（文档预览）、`ui-layout`、`ui-dockkit`（停靠面板）、`ui-theme`、`ui-settings*`（含 `ui-settings-plugin-inventory` 插件管理）、`ui-brand-official`（品牌位）。

### 2.3 Host/Client RPC 层（`packages/api/`）

`api-gateway` + 一组 **「Host … Remote controller」** 服务：`api-session-controller`、`api-workspace-controller`、`api-workspace-files`、`api-settings-controller`、`ctx.directoryPickerController`、`ctx.credentialsController`。客户端包消费 Remote 服务、不直连宿主 —— **这正是"换前端不换后端"的架构前提。**

### 2.4 Profile 与组合包（官方设计的扩展方式）

官方原话：**「不存在需要打补丁的特权内核：扩展 dsh 的方式是把插件挂载到其他插件旁边。」**

- 随发行版交付的 profile：`web` / `headless` / `sdk` / `sdk-minimal` / `acp`
- 自定义 profile = 有序叠加的组合包 + `cordis.patch.yml` 逐层 patch，「一条 patch 按 id 定位某个条目并替换其整个 config」
- `dsh-base` 是共享第一层：模型适配、工具、持久化、**沙箱与审批策略**、设置、凭据、遥测
- 改任何东西前可先 `dsh --profile web --dump-config` 看本机配置树，「打印出的任何条目，都可以由你自己的 patch 替换」

### 2.5 能力 seam 与扩展点

架构文档给了**扩展归属映射表**（21 条），与本项目相关的几条：

| 目标 | 官方机制 |
|---|---|
| 添加面向模型的能力 | 在 `ctx.tools` 上注册，schema 自动进提示词组装 |
| 添加 shell 执行 | 注册 `ctx.shell` 后端 |
| 添加后台工作 | 注册 `ctx.jobs` |
| 限制所启动的进程 | 使用 `ctx.sandbox` 后端 |
| 拦截请求/工具/轮次 | 监听 `agent/*` 或 `tools/*` 事件 |
| **添加 UI 或编辑器集成** | **驱动 `ctx.agents` 并从 `session/event` 渲染** |
| 添加 Web Client Chat 节点 | 注册 `ConversationNodeDefinition` + keyed renderer |

### 2.6 其他地方核出来的硬事实

- **会话日志**：追加式、带版本（`session.vN.jsonl[.zstd]`）、有迁移链、**「模型可见即已记录」是运行时不变量**。审计留痕是天生自带的。
- **SDK 三件套**：TypeScript SDK（解析同版本 `dsh` 依赖，选 `sdk` profile）／**Python SDK**（运行时 wheel 把 `dsh --profile sdk` 打包进去）／`acp` profile（Agent Client Protocol，纯自动化用）。
- **桌面端版本锁定**：官方明写「Electron 与 `@deepseek-ai/dsh` 始终使用同一精确版本。**即使桌面壳代码不变，升级 dsh 也必须发布新 Desktop 版本**」。→ fork 之后，你的产品版本号被 upstream 绑架。
- **许可 MIT**：fork 与商业闭源衍生都合法。
- **开发者预览**：官方明写「未来将出现破坏兼容性的变更」。
- **工程体量**：仓库约 **183 MB**；pnpm monorepo；`packages/` **55 个包** + 4 个应用；含原生模块（`node-pty`，Windows 上要 Python + VC++ 构建工具）；多套 vitest 配置；文档有**双语配对校验**（`verify-translation-pairing`）与**文档图生成**（`gen-doc-graphs`）；发行签名要 **Windows EV 证书 + SafeNet Token**、macOS 公证流水线。
- **Issue 通道关闭**（`has_issues: false`），只有 Discussions。

---

## 3. 四条路线

| 代号 | 名称 | 一句话 |
|---|---|---|
| **A** | 纯自建 | 完全不用 dsh，AI 自己调 LLM API；一切自建 |
| **A+** | **装配式二次开发（推荐）** | 自建 UI 外壳与编辑内核；dsh 以**官方 profile + 外部插件包**引入，**不改源码** |
| **C** | 真 fork | 克隆 monorepo 改源码 + 自写 profile/bundle/`ui-*` 插件，产品 = 魔改版 dsh |
| **B** | 原样用（基线） | `npx dsh web` 当产品用，只装插件 |

> **A+ 与 C 的本质区别**：A+ 是**装配**（装官方件 + 挂自己的件），C 是**改造**（改官方件的源码）。官方架构文档明确说了「不存在需要打补丁的特权内核」—— 意味着**绝大多数"二次开发"诉求，用插件就能满足，根本不必 fork**。

---

## 4. 逐维度对比

### 4.1 复用边界矩阵

| 层 | A · 纯自建 | A+ · 装配式 | C · 真 fork | B · 原样用 |
|---|---|---|---|---|
| 桌面外壳 / 打包 / 自动更新 | 自建 | 自建（可抄 dsh 的 electron-builder 配置） | **dsh 改编** | dsh 原生 |
| 目录树 / 布局 / 主题 / i18n | 自建 | 自建 | **dsh 改编** | dsh 原生 |
| **编辑内核**（docx 所见即所得 / 打印 / 导出 / 已打印标记） | **自建** | **自建** | **自建** | ❌ 没有 |
| 5 块确定性引擎 | 自建 | 自建（同时注册成 dsh 工具） | 自建（注册成 dsh 工具） | 自建（插件） |
| Agent 循环 / 权限沙箱 / 会话留痕 / 模型适配 | 自建或调 API | **dsh 原生** | **dsh 原生** | dsh 原生 |
| 插件管理器 / 设置面板 | 自建 | 自建或复用思路 | **dsh 原生** | dsh 原生 |

**一眼看出：C 相对 A+ 多拿到的是「外壳 + 工作台 + 插件管理器」，少拿到的是「不用跟 upstream」。编辑内核三行全是"自建"，谁都给不了。**

### 4.2 决策维度对比

| 维度 | A · 纯自建 | **A+ · 装配式（推荐）** | C · 真 fork | B · 原样用 |
|---|---|---|---|---|
| 前期工作量 | 最大 | **中** | 中（外壳白拿） | 最小 |
| 长期维护负担 | 低 | **低**（升级=只换 dsh 版本） | **极高**（rebase 183MB / 55 包 / 含原生模块的 monorepo） | 低但被动 |
| upstream 破坏性变更影响 | 无 | **可控**（插件 API 变了才要动） | **每一处都砸你脸上** | 全砸 |
| 版本号归属 | 你的 | **你的** | **被 dsh 绑架**（Electron 与 dsh 同版本锁定） | 不是你 |
| 交付形态 | 双击即用 ✅ | **双击即用 ✅** | 双击即用 ✅ | 浏览器/CLI ⚠️ |
| 是否要去 issue 通道 | 不用 | 少用 | **没得用（已关）** | 没得用 |
| AI 能力（循环/沙箱/留痕/多模型） | 自己搭 | **全部拿到** | 全部拿到 | 全部拿到 |
| 对外卖同行 / 做平台 | 可以 | **可以** | 可以但升级拖累 | 难（是别人的产品） |
| 团队技能门槛 | 中（桌面+文档处理） | **中** | **高**（TS monorepo + 插件生态 + 原生构建 + 发布签名） | 极低 |
| 抽身成本（想换底座） | — | **低**（dsh 是外挂进程，拔掉就行） | **极高**（代码已深度纠缠） | 高 |
| 失败模式 | 进度慢 | **AI 层挂了不影响出整册** | **升级一次崩一次** | 哪天升级就坏 |

### 4.3 关键判断

**为什么 fork 换不来核心价值？**

这软件的三根支柱 —— **① Word 级编辑内核 ② 打印与"已打印/未打印"状态 ③ 一键成册的确定性批处理** —— dsh 一样都没有，fork 之后**还是得自己写**。fork 能省的是外围工作台。而外围工作台，恰恰是 A+ 能**用官方插件机制低风险白拿**的部分（`ui-slots` 挂面板、`ctx.sandbox` 挡模板写入、`session/event` 出留痕、SDK 起后端）。

**所以：C 用"永久接管一个框架"去换"前期省下外壳工作量"，这笔账不划算。**

**什么情况下 C 才划算？** 满足全部三条才考虑：
1. 目标明确是**平台型产品**（要接第三方插件生态、要卖同行）；
2. 有 **3~5 人能长期全职跟 upstream**（这是个公司级工程，不是二次开发）；
3. 愿意接受产品版本号由 dsh 发行节奏决定。

这三条目前一条都不成立。

---

## 5. 建议路线：A+ 装配式二次开发

### 5.1 形态

```
┌──────────────────────────────────────────────────────────┐
│  你的桌面壳（Electron / Tauri）                            │
│  Ribbon · 左侧三页签树 · 编辑区 · 打印预览 · 导出           │  ← 自建（命根子）
│  ← 抄 dsh 的 electron-builder / 更新 / 签名配置思路即可      │
└───────────────┬──────────────────────────────────────────┘
                │ 本地 IPC / JSON-RPC（127.0.0.1 或 stdio）
                ▼
┌──────────────────────────────────────────────────────────┐
│  dsh 子进程（官方 profile，不改源码）                       │
│  dsh --profile sdk   ← headless，无 UI，纯能力后端          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ dsh-base：模型适配 · 工具注册表 · 沙箱·审批 · 会话日志 │  │  ← 白拿
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 你的外部插件包（树外插件，dsh plugin 安装）           │  │  ← 自建，但是插件形式
│  │  · tools: fill / subtable / numbering / verify /    │  │
│  │           aggregate                                 │  │
│  │  · sandbox policy: 拒绝写 模版/**                    │  │
│  │  · 会话留痕 / 轨迹                                   │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                │
                ▼
        工程文件夹（project.json + docx + 附件）  ← 不依赖 dsh，可整包拷走
```

### 5.2 为什么这样最优

| 收益 | 说明 |
|---|---|
| **拿到 dsh 全部外围基建** | 权限沙箱、审批、会话留痕、模型适配、工具注册表、MCP/LSP/Skills —— 都是官方件，一条 patch 就能改配置 |
| **零分叉** | 升级 = 换个 dsh 版本号。插件 API 变了才需要动你的代码 |
| **抽身自由** | dsh 是外挂进程。哪天它崩了、变商业了、你想要更快 —— 拔掉，换一层薄 LLM 调度，产品照样跑 |
| **模板保护变硬机制** | 用 `ctx.sandbox` 写一条策略：**拒绝一切写 `模版/**` 的动作**。我上个月真越界改过一次文档，这条对我是刚需 |
| **确定性引擎留在自己手里** | 一键成册仍是 Python 直改 docx（实测 **1 秒 37 份、171/171 命中、100% 可复现**），**绝不交给 LLM** |
| **留痕可交付甲方** | 追加式会话日志可回放：谁、何时、改了哪份哪字段 |

### 5.3 什么时候才升级到 C

只有当出现下面这个信号：**你要开放插件生态给第三方开发者，且自建外壳成了瓶颈**。在那之前，A+ 的收益/成本比完胜。

---

## 6. 待工头拍板

1. **A+ 认不认？** 认了我就把 dsh 的引入方式写进 `规范/软件使用方式设计.md` 的实施路线。
2. **先做最小验证？** 用 `dsh --profile sdk` + 一个外部插件包，跑通「**施工日志 → 周报 → 月报**」。这个试点不碰模板、不碰编辑内核，搞砸零损失。需要你给个模型 API Key。

---

## 附：核验手段与参考

- **手段**：GitHub REST API 逐目录遍历（`apps/` / `packages/` / `packages/client/` / `packages/host/` / `packages/acp/` / `docs/`）+ 官方文档正文抓取 + `npm view` / `npm pack` 解包逐文件统计。可复现。
- **本地归档**：`.workbuddy/ref/dsh-docs/`（架构 / Cordis / 能力 seams / 桌面端 / UI 插槽 / 客户端 / 沙箱 共 8 份原文）
- **官方文档**：https://deepseek-harness.github.io/deepseek-harness/
- **仓库**：https://github.com/deepseek-ai/deepseek-harness （默认分支 `master`）
