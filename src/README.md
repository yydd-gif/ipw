# Electron 壳（P7 · E1 + 打包）

入口：仓库根目录 `package.json` → `npm run dev`。可选环境变量 `YANSHOU_PROJECT=/path/to/project` 在启动时自动打开该工程文件夹。

主进程 `src/main.js` 通过 `src/runtime.js` 解析安装根与便携 Python，再 `child_process` 调用：

- `assets/engine/shell_bridge.py`（建档 / 打开 / 字段 / 子表 / 成册 / 打印 / 预览 / 回收站 / 周报月报 / AI 闸门 / **模板体检**）
- 其余引擎仍为 Python，**不把引擎改写成 JS**。

打包后根目录是 `process.resourcesPath`（extraResources），开发时是仓库根。工作目录打包后写到 `userData/work`，避免只读安装目录。

编辑模式由 `src/fidelity-status.json` 声明：当前为 **E1 表单 + 只读预览 + 子表网格**。

打包：`npm run pack:linux` / `npm run pack:win`，说明见 [`docs/打包说明.md`](../docs/打包说明.md)。

AI 入口在无 `DEEPSEEK_API_KEY` 或断网时全部置灰；**生成周报/月报不依赖模型**。
