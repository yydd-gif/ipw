# dsh-yanshou-docs

验收资料编辑软件的**七块**确定性引擎 —— 以 DeepSeek Harness「组合包」形式接入（v0.2）。

**路径**：本包在仓库里的位置是 [`packages/dsh-yanshou-docs`](../../packages/dsh-yanshou-docs)（交付包里的 `04_AI组合包/dsh-yanshou-docs/` 只保留指针）。

## 这是什么

一个 dsh **组合包**（bundle）：把 Python 引擎注册成面向模型的工具。**不改 dsh 一行源码**，通过官方 profile + patch 层接入。

只用 **`dsh.bundle.patch`**，**不用 `dsh.client`** —— 编辑区由自建壳拥有，dsh 只当 sdk / JSON-RPC 后端。

## 定位：接线层，不是逻辑层

```
你的桌面壳（Ribbon / 三页签树 / 编辑区 / 打印 / 导出）   ← 自建（P4）
        │ stdio JSON-RPC（--profile yanshou，从 sdk 模板派生）
        ▼
dsh --profile yanshou  （headless 后端，upstream 一行未改）
  ├─ @deepseek-ai/dsh-base
  ├─ @deepseek-ai/dsh-sdk-app          ← JSON-RPC server
  └─ dsh-yanshou-docs（本包）           ← 只做接线
       └─ spawn → assets/engine/*.py   ← 真正干活
```

每个工具只做三件事：`assertWritable()` → spawn 一次 Python 子进程（`--json`）→ 解析 stdout **最后一行**契约 JSON。

## 提供的工具（7）

注册顺序：`datafill → docgen → fill → numbering → verify → aggregate → subtable`

| 工具名 | 引擎 | 说明 |
|---|---|---|
| `yanshou_datafill` | `datafill_engine.py` | 取值装配 → FillPlan（只算不写文档） |
| `yanshou_docgen` | `docgen_engine.py` | 一键成册 / 单份 / 无模板三选一 |
| `yanshou_fill` | `fill_engine.py` | 按 FillPlan 填充；可复用 `planPath` |
| `yanshou_numbering` | `numbering_engine.py` | 编号；删 02 不重排 03 |
| `yanshou_verify` | `verify_engine.py` | 导出前校验闸门 |
| `yanshou_aggregate` | `aggregate_engine.py` | 日志→周报/月报（P6 骨架；模型先归纳） |
| `yanshou_subtable` | `subtable_engine.py` | 子表接管（P5 骨架；先注册避免「脚本不存在」） |

## 配置：双轨制

| 字段 | 含义 |
|---|---|
| `installRoot` | 安装资产根（只读）：`templates/` `spec/` `engine/` `runtime/` |
| `workspaceRoot` | 工程数据根（可读写，可整包拷走） |
| `activeProject` | 当前工程目录或 `project.json` |
| `pythonBin` | Python 解释器（交付为内嵌运行时） |
| `engineRoot` | 留空 = `<installRoot>/engine` |
| `protectedPaths` | 相对 `installRoot`。默认 `templates`、`templates-backup`、`templates_原始备份` |
| `allowWriteToTemplates` | 逃生开关，默认 `false` |
| `engineTimeoutMs` | 单次引擎超时，默认 600000 |

模板保护的路径基准是 **`installRoot`**，比较前 `realpathSync` 解 symlink / junction。

## 凭据（红线）

- **只走环境变量 `DEEPSEEK_API_KEY`**（可选 `DEEPSEEK_BASE_URL`）。
- **`cordis.patch.yml`、源码、tarball、Git 里都不得出现 Key。**
- 模型名只写 `deepseek-flash` / `deepseek-v4-pro`，不写 `deepseek-chat` 别名。

## 安装与运行（照施工图 §7）

运行时推荐 ADR-18：`pip install deepseek-harness-sdk==0.1.5rc1`（原生 `dsh`，不依赖系统 Node）。**装插件仍需 pnpm**（打包机一次性）。`dsh` **要求非空 `DSH_HOME`**，绝不回退 `~/.dsh`。

```sh
export DSH_HOME=/path/to/dsh-home          # 必须先建目录
mkdir -p "$DSH_HOME"
export DEEPSEEK_API_KEY=...                # 不写进任何文件

# 1. 从出厂 sdk 模板派生 —— 不要裸 --profile yanshou 初始化（会得到空根、没有 JSON-RPC）
dsh --profile yanshou --from-default-profile sdk

# 此时 profiles/yanshou/package.json 的 bundles 应为：
#   ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-sdk-app"]

# 2. 构建并打 tarball（必须用 tarball，不要 link:）
cd packages/dsh-yanshou-docs
pnpm install
pnpm build
pnpm pack                                  # dsh-yanshou-docs-0.2.0.tgz

# 3. 装进 profile
dsh plugin --profile yanshou add ./dsh-yanshou-docs-0.2.0.tgz

# 4. 验证层生效
dsh --profile yanshou --dump-config
```

### `--dump-config` 期望（真跑才算数）

输出里应出现：

```yaml
# == dsh-yanshou-docs
- id: yanshou-docs
  name: dsh-yanshou-docs
```

以及被本层覆盖的：

- `id: agent-default-model` → `model: deepseek-flash`（无 `deepseek-chat`）
- `id: system-prompt` → 不再是 “You are a coding agent…”
- `id: sdk-jsonrpc-server`（来自 sdk 模板，不是我们手插的）

`profiles/yanshou/package.json` 的 `dsh.profile.bundles` 应为：

```json
["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-sdk-app", "dsh-yanshou-docs"]
```

**不要把某次失败或本机未跑的输出抄进文档冒充实测。** 仓库里的 `test/dump-config.expectation.md` 只列出期望片段，不是一次真实 dump。

### 两条实测踩过的坑

1. **必须用 tarball，不要用本地目录 `link:`** —— Windows 上 pnpm 的 `link:` 会产生**空目录**，dsh 解析不到包后打出误导性警告「declares no dsh.bundle」。真因是链接为空。
2. **先 `--from-default-profile sdk`，再 `plugin add`**。`dsh plugin --profile <n>` 在 profile 不存在时会以**空根**自动初始化（没有 sdk-app），然后再因缺 pnpm 失败。
3. 打包分发前在 profile 的 `.npmrc` 设 `node-linker=hoisted`，否则 pnpm 的 store 符号链接拷到别的机器会断。

## Headless 审批（施工图 §9.1）

dsh-base 默认：

```yaml
- id: approval
  name: '@deepseek-ai/dsh-user-approval'
  config:
    policy: !!js >-
      (process.env.DSH_PERMISSION_MODE ?? 'workspace-write') === 'danger-full-access'
        ? 'never' : 'ask'
```

`ask` 在没有审批回调的 headless 壳里会**一直挂住**。

| 场景 | 做法 |
|---|---|
| 生产壳（P4） | **方案 A**：实现审批回调，弹窗问用户。不要关安全阀。 |
| CI / 本机无 UI | **方案 B（后门）**：`export DSH_PERMISSION_MODE=danger-full-access`（见 `scripts/headless.env`），可选再加 `--patch overlays/ci-headless.patch.yml` |
| 不要做 | 在组合包 `cordis.patch.yml` 里猜 `id: approval` 的键（方案 C） |

`danger-full-access` **禁止**写进已提交的 bundle patch。

启动 dsh 时 **cwd 必须是工程目录**（`sandbox-policy.workspaceRoot` 在 dsh-base 里是 `process.cwd()`；我们的层给了安装器默认值，开发机请 overlay）。

## 模板保护

写盘工具第一件事是 `assertWritable()`。命中 `installRoot` 下的 `templates` / `templates-backup` 抛 `TemplateProtectionError`。Python 引擎侧 `assets/engine/_common.py` 还有一层。

## 文件

```
package.json            # dsh.bundle.patch + peerDependencies（精确版本，无 ^）
cordis.patch.yml        # 配置层：insert 本插件 + 覆盖模型 / 提示词 / 沙箱
tsdown.config.mjs       # deps.neverBundle @deepseek-ai/* 与 node:
overlays/ci-headless.patch.yml
scripts/headless.env
src/
  index.ts              # name / inject=['tools'] / apply
  config.ts             # 双轨制 Config
  bridge.ts             # spawn + 契约 JSON + 进程树超时
  policy.ts             # 模板保护（installRoot + realpath）
  tools.ts              # 七个 defineTool
```

`peerDependencies` 钉死 `0.1.5-rc.1`（与 `deepseek-harness-sdk==0.1.5rc1` 一致），并标 `optional: true`，配合 `.npmrc` 的 `auto-install-peers=false`。

## 无 Key 可跑的检查

```sh
python tools/run_p3_smoke.py
```

不调用模型。能跑：静态契约、policy 单测、（若有 pnpm）build / pack、（若有 `dsh`）真实 `--dump-config`。没有 `dsh` 时不会伪造 dump 输出。

## Model Experience

### Request context and condition

#### What the model sees

七个工具的 name / description / parameters 进入提示词组装（由工具注册表统一处理）。`system-prompt` 的 persona 被本层换成验收资料助手，不再是 coding agent。

#### Token effect

固定：七个工具 schema 常驻；persona 前缀/后缀替换 sdk-app 原值。

#### KV Cache effect

替换 `system-prompt` 会使该前缀失效；工具列表仅追加。

## Known Limitations and Deferred Work

- **全局 `tools/pre-execute` 钩子未启用** —— 签名未确认，本阶段只靠工具内 `assertWritable()`。
- **审批回调的 RPC 形状未确认** —— P4 壳实现方案 A；P3 CI 走 `DSH_PERMISSION_MODE` 后门。
- **`yanshou_subtable` / `yanshou_aggregate` 引擎仍是骨架** —— 工具已注册，返回 not-implemented 契约，而不是「脚本不存在」。
- **模型真调一轮需要 `DEEPSEEK_API_KEY`** —— 不写进仓库。无 Key 时不要假装跑过步骤 4。
