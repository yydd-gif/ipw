# 验收到手（Acceptance Studio）M1

本地桌面应用，用于把工程 / 政务信息化 / 混合项目的验收资料按固定七卷目录组卷，并导出 Zip 资料包。

M1 垂直切片：**项目主数据 → 施工日志 → 生成 2.12 项目周报（可选 2.11 月报）→ 填充 2.10 施工日志 Word → 按目录导出验收资料包**。

2.1–2.5 为开工报审、授权书、施工组织方案、开工令等上传件。不内嵌 GenOffice：生成 `.docx` 后用操作系统默认程序打开，主进程预留后续接入点。

## 功能范围

1. 新建项目（类型 `engineering` | `gov_it` | `hybrid`，默认混合）。混合类型同时启用工程条目与政务信息化条目。
2. 数据驱动的验收目录（七卷），条目含编号、中文标题、产出方式（上传 / 模板 / 派生）、必填、适用类型。实例状态：未开始 / 草稿 / 已确认 / 免于提供。
3. 施工日志表单，本地 SQLite 存储。
4. 使用 `templates/` 下的 Word 模板填报（非 Excel），导出带目录文件夹结构的 Zip。
5. 必填条目未确认时禁止出包。

## 环境要求

- Node.js 20+（推荐 22）
- npm
- 桌面环境（用于 Electron 窗口；无界面机器可用 `npm run verify:m1` 校验核心链路）

## 运行

Windows 用户请看 [Windows 运行说明](docs/windows-run.md)（含系统 Node 损坏时的便携版应急）。

```bash
npm install
npm run dev
```

首次 `npm install` 会执行 `postinstall`，生成 `templates/` 中的示例 `.docx`。若模板缺失，可手动执行：

```bash
npm run generate:templates
```

其他脚本：

```bash
npm run verify:m1    # 无界面走通 M1 演示路径并检查 Zip 结构
npm run typecheck
npm run build
```

Linux 容器若无法打开窗口，可安装并使用虚拟显示：

```bash
xvfb-run -a npm run dev
```

数据目录默认在 Electron `userData/acceptance-studio/`，布局为 `projects/<id>/uploads|generated`。可用环境变量 `ACCEPTANCE_STUDIO_HOME` 覆盖。

## 推荐演示路径

1. 侧栏 **项目**：新建「混合」项目，填写建设单位 / 监理 / 施工 / 合同号。
2. **施工日志**：至少录入 3 条日志。
3. 点击 **生成周报**（2.12）；可选 **生成月报**（2.11）。
4. 点击 **导出 2.10 施工日志**，用系统 Word / WPS 打开检查。
5. **资料目录**：对上传类必填条目放入任意占位文件；对模板类条目点「生成 Word」。
6. **出包**：点「确认所有已有资料」，再「导出验收资料包」。

Zip 结构示例：

```text
验收资料包_<项目名>_<日期>/
  00_目录与校验报告.md
  01_依据分册/1.2_合同/...
  02_过程分册/2.10_施工日志/2.10_施工日志.docx
  02_过程分册/2.12_项目周报/2.12_项目周报.docx
```

## 模块说明

| 模块 | 路径 | 职责 |
| --- | --- | --- |
| 目录定义 | `src/shared/catalog.ts` | 七卷条目、必填、适用类型 |
| 完整性校验 | `src/shared/completeness.ts` | 出包阻断规则 |
| 日志与项目 | `src/core/studio.ts` | SQLite + 文件布局 |
| 模板引擎 | `src/core/template-engine.ts` | docxtemplater + PizZip 填 Word |
| 导出器 | `src/core/studio.ts` `exportZip` | 按分册/编号组 Zip |
| Electron 主进程 | `src/main/index.ts` | IPC、系统打开 Word、文件对话框 |
| 界面 | `src/renderer` | 项目 / 资料目录 / 施工日志 / 出包 |

Word 打开处留有扩展注释：`GENOFFICE_EXTENSION_POINT`。后续可改为调用 GenOffice，而不改组卷流程。

## 目录条目要点

- **1 依据分册**：以上传为主，**1.2 合同必填**。
- **2 过程分册**：2.6 / 2.7 / 2.8 / 2.9 / 2.13 必填；2.10 施工日志选填；**2.11 项目月报、2.12 项目周报**；工程/混合选填上传：2.1 开工报审表、2.2 项目经理授权书及法定代表人授权书、2.3 施工组织方案报审表、2.4 施工组织方案、2.5 工程开工令。
- **3 图纸分册**、**4 变更分册**：上传（变更有则归档）。
- **5 初步验收与试运行（政务信息化）**：5.1 / 5.4 / 5.6 / 5.7 / 5.8 / 5.9 必填。
- **6 竣工验收（普通/工程）**：6.2 必填；6.1 工程选填。
- **7 竣工验收（政务信息化）**：7.1 / 7.2 / 7.4–7.11 必填；7.4、7.5 为「后期自动生成」占位稿。

示例模板：`2.10`、`2.11`、`2.12`、`2.7`、`2.8`、`6.2`、`7.1`、`7.2`。其余模板类条目以主数据标量填充为主，表格字段可后续加深。

## 技术栈

Electron + Vite + React + TypeScript；`sql.js`（SQLite）；`docxtemplater` + `pizzip` 填充中文 Word 表格。
