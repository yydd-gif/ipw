# 验收到手（Acceptance Studio）v1 · 备胎线

Electron 桌面应用：工程 / 政务信息化 / 混合项目的**验收资料编辑**。本版按 ADR-5 走 **备胎线**——上表单写入 `project.json`，离线 Python `fill_engine` 填充 `{{key}}`，下侧只读预览。**不是** OnlyOffice WYSIWYG。

右栏黄条固定文案：`当前为表单模式（编辑内核未就绪）`。`EditorHost` 预留 `FormPreviewHost` / `OnlyOfficeHost` 交换位。

## 本版能做什么

1. 启动先进入**项目管理**：新建 / 最近 / 打开 `project.json`。
2. **EditorShell**：左八册目录树 · 右上表单 + 右下只读预览 · 底栏 导出 / 打印预览 / 打印。
3. 目录色点：灰空 / 琥珀草稿 / 绿已齐 / 红异常（含「重要且空」）。打印图标单独：灰未打印 / 亮已打印。改内容打回未打印；**预览 ≠ 已打印**。
4. 无模板条目只有上传区，不造假表。
5. 导出硬阻断残留 `{{}}` 与未填必填；打印未齐仅软提示，允许继续。
6. **一键成册**直接 spawn 离线 `engine/fill_engine.py`（不经过 dsh）。AI 区离线灰置。

演示模板只有 3 份。完整 37 套官方模板 + 生产引擎、Win 便携 Python、dsh AI、OnlyOffice 嵌入见文末「明确延期」。

## 环境

- Node.js 20+（推荐 22）
- Python 3（`python3`，仅用标准库；可选 `engine/requirements.txt`）
- 可选：LibreOffice / `soffice`（DOCX→PDF）。没有则导出占位 PDF，并同时可另存填充后的 docx。

## 运行

Windows 见 [docs/windows-run.md](docs/windows-run.md)（含 Electron 国内镜像说明）。

```bash
npm install
npm run typecheck
npm test            # scripts/smoke.ts
npm run dev
```

`.npmrc` 已钉死：

```ini
electron_mirror=https://npmmirror.com/mirrors/electron/
```

`npm install` 会用该镜像拉 Electron 二进制，不必再手设环境变量。PowerShell 里不要粘贴 cmd 的 `set`。

数据目录默认 `userData/acceptance-studio/`（可用 `ACCEPTANCE_STUDIO_HOME` 覆盖），每个项目一份 `projects/<id>/project.json`。

## 架构

```text
表单 / 项目主数据  →  project.json + items.overrides
        ↓
离线 python3 engine/fill_engine.py  ({{key}} → docx + preview.html)
        ↓
只读预览  /  导出  /  打印状态机
```

| 模块 | 路径 |
| --- | --- |
| 八册目录 | `src/shared/catalog.ts` |
| 表单字段 | `src/shared/fields.ts` |
| 项目存储 | `src/core/studio.ts` |
| 填充桥 | `src/core/fill-bridge.ts` |
| 填充引擎 | `engine/fill_engine.py` |
| 编辑内核交换 | `src/renderer/src/editor/EditorHost.tsx` |

## 明确延期（不挡 v1）

- OnlyOffice / 真 WYSIWYG 嵌入
- 官方 37 套模板包导入
- Windows 便携 Python 随包装发
- dsh AI（智能填写 / 校核）

## 技术栈

Electron + Vite + React + TypeScript；项目 JSON；Python 3 stdlib 填充 Word。
