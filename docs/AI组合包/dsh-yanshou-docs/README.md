# dsh-yanshou-docs

验收资料编辑软件的五块确定性引擎 —— 以 DeepSeek Harness「组合包」形式接入。

## 这是什么

一个 dsh 组合包（bundle）：把「验收资料编辑软件」的五块引擎注册成面向模型的工具，
让 dsh 的 agent 轮次可以直接调用。它**不改 dsh 源码**，通过官方 profile + patch 层接入。

## 定位：接线层，不是逻辑层

```
你的桌面壳（Ribbon / 三页签树 / 编辑区 / 打印 / 导出）   ← 自建
        │ 本地 IPC
        ▼
dsh --profile yanshou  （headless 后端，不改源码）
  ├─ dsh-base：模型适配 · 工具注册表 · 沙箱审批 · 会话日志   ← 官方提供
  └─ dsh-yanshou-docs（本包）                              ← 只做接线
       └─ spawn → Python 引擎（.workbuddy/engine/*.py）      ← 真正干活
```

本包的每个工具只做三件事：校验参数 → spawn 一次 Python 子进程 → 把 stdout 回成工具结果。
文档处理逻辑全部留在已验证的 Python 引擎里，**零重写**。

## 提供的工具

| 工具名 | 引擎 | 状态 |
|---|---|---|
| `yanshou_fill` | `fill_engine.py` 一键成册填充 | ✅ 引擎已跑通（37 份 / 171 处命中 / 零残留） |
| `yanshou_verify` | `verify_engine.py` 导出前残留查错 | ⏳ 待从 `tools/verify_placeholders.py` 收编 |
| `yanshou_subtable` | `subtable_engine.py` 清单表按表头接管数据行 | ⏳ 待建 |
| `yanshou_numbering` | `numbering_engine.py` 编号分配 | ⏳ 待建 |
| `yanshou_aggregate` | `aggregate_engine.py` 日志→周报→月报 | ⏳ 待建 |

## 模板保护（硬机制）

本项目铁律：**AI 绝不写 `模版/` 下的 docx**。这条规矩曾经被破过一次，所以落成代码：

- `src/policy.ts` 的 `assertWritable()` 是所有写盘工具的前置闸门，命中受保护目录直接抛 `TemplateProtectionError`
- 受保护目录由 `protectedPaths` 配置，默认 `模版`、`模版_原始备份`
- `allowWriteToTemplates` 是逃生开关，默认 `false`

## 文件

```
package.json        # 声明 dsh.bundle.patch
cordis.patch.yml    # 配置层：insert 本插件 + 默认配置
tsdown.config.ts    # 自包含构建（prepare 用，不依赖 monorepo）
src/
  index.ts          # 插件入口：name / inject / apply
  config.ts         # Config 接口 + Schemastery schema
  bridge.ts         # Python 引擎桥（spawn + 超时 + 退出码）
  policy.ts         # 模板保护策略
  tools.ts          # 五块引擎的 defineTool 注册
```

## 安装与运行

```sh
# 1. 构建并打包（产出 dsh-yanshou-docs-0.1.0.tgz）
pnpm install && pnpm build && pnpm pack

# 2. 装进一个专用 profile（首次会自动以 dsh-base 为基础初始化）
dsh plugin --profile yanshou add ./dsh-yanshou-docs-0.1.0.tgz

# 3. 先验证层生效，再启动
dsh --profile yanshou --dump-config     # 应看到 "# == dsh-yanshou-docs" 层
dsh --profile yanshou
```

配置覆盖：用户在自己 profile 的 `cordis.patch.yml` 里按 `id: yanshou-docs` 覆盖，
**无需改动本包**。注意 patch 替换的是整行 `config`，不是深合并 —— 覆盖时要重述要保留的键。

### 两条实测踩过的坑（2026-09-12 真机验证）

1. **必须用 tarball，不要用本地目录 `link:`** —— 在 Windows 上 pnpm 的 `link:` 会产生**空目录**，
   `node_modules/<包名>/package.json` 不存在，dsh 解析不到包后会退化并打出误导性警告
   「declares no dsh.bundle」。真因是链接为空，不是你 manifest 写错。
2. **首次跑 `dsh plugin` 前先确保 `pnpm` 可用** —— dsh 把安装转发给 pnpm，
   没装 pnpm 会直接报 `dsh: pnpm failed in profile directory`。

（该链路已实测走通：`dsh.profile.bundles` 自动追加包名，`--dump-config` 出现自定义层头。）

## Model Experience

### Request context and condition

#### What the model sees

五个工具的 name / description / parameters 进入提示词组装（由工具注册表统一处理）。

#### Token effect

固定：五个工具 schema 常驻；description 长度决定常量开销。

#### KV Cache effect

仅追加 —— 本包只注册工具、不修改系统提示词，不使已有前缀失效。

## Known Limitations and Deferred Work

- **钩子层未启用** —— `src/policy.ts` 末尾的 `tools/pre-execute` 全局拦截处于注释状态。
  dsh 架构文档记载它是 waterfall 事件（须调用 `next()`），但确切回调签名需真机确认后再启用，
  不凭猜测写跑不通的代码。当前保护依赖工具内的 `assertWritable()` 调用，覆盖本包自身工具。
- **四个引擎脚本待建** —— 表中 ⏳ 项的 Python 脚本尚未落地，对应工具会返回「引擎脚本不存在」。
- **版本号待锁定** —— `package.json` 里 `@deepseek-ai/*` 的依赖范围写的是 `^0.1.5-rc.1`，
  需按实际安装的 dsh 版本核对后钉死。dsh 官方声明处于开发者预览、会有破坏性变更，
  锁定版本比放宽范围重要。
- **TS 构建链路未实测** —— 插件机制本身已在真机验证通过（装 tarball → bundles 追加 → `--dump-config` 出层），
  但**本包的 tsdown 构建与加载尚未跑过**，需先 `pnpm install` 依赖再 `pnpm build` 验证。
- **模型调用未验证** —— 需要模型 API Key。按实测，Key 走环境变量注入
  （dsh 内置 `web-search-deepseek` 用的就是 `apiKeyEnv: DEEPSEEK_API_KEY` 这种方式），不写进配置文件。
