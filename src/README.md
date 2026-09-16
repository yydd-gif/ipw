# Electron 壳（P4 · E1 MVP）

入口：仓库根目录 `package.json` → `npm run dev`。可选环境变量 `YANSHOU_PROJECT=/path/to/project` 在启动时自动打开该工程文件夹（跳过系统对话框，便于演示与 GUI 试跑）。

主进程 `src/main.js` 通过 `child_process` 调用：

- `assets/engine/shell_bridge.py`（建档 / 打开 / 字段 / 成册 / 打印标记 / 预览 / 回收站）
- `assets/engine/export_engine.py`（单份 / 整册 PDF）

**不把 Python 引擎改写成 JS。** 编辑模式由 `src/fidelity-status.json` 声明：当前为 **E1 表单 + 只读预览**（`@genoffice/docx-engine` 未发布到 npm，V3 产品路径 BLOCKED）。

四色状态点只表示填写态（灰/蓝/绿/红 = empty/draft/complete/error）。**已打印**是树上单独的「印」角标，写入 `project.json` 的 `_printStates`，关软件重开仍在。
