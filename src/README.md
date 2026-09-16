# Electron 壳（P5 · E1 + 子表）

入口：仓库根目录 `package.json` → `npm run dev`。可选环境变量 `YANSHOU_PROJECT=/path/to/project` 在启动时自动打开该工程文件夹（跳过系统对话框，便于演示与 GUI 试跑）。

主进程 `src/main.js` 通过 `child_process` 调用：

- `assets/engine/shell_bridge.py`（建档 / 打开 / 字段 / 子表 `_assets` / 半自动同步 / 成册 / 打印标记 / 预览 / 回收站）
- `assets/engine/export_engine.py`（单份 / 整册 PDF）
- `assets/engine/subtable_engine.py`（8 张清单表行克隆）

**不把 Python 引擎改写成 JS。** 编辑模式由 `src/fidelity-status.json` 声明：当前为 **E1 表单 + 只读预览 + 子表网格**（`@genoffice/docx-engine` 未发布到 npm，V3 产品路径 BLOCKED，因此不做 E2/E3 正文流式编辑）。

四色状态点只表示填写态（灰/蓝/绿/红 = empty/draft/complete/error）。**已打印**是树上单独的「印」角标，写入 `project.json` 的 `_printStates`，关软件重开仍在。

项目级字段保存会弹出半自动同步：「仅本份」写入 `_documents[本份]` 且不改其他文档；「同步全册」改档案并用 `yz_` 锚点回写。
