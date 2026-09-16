# Electron 壳（P7 打包 + GenOffice 源码嵌入）

入口：仓库根目录 `package.json` → `npm run dev`。可选环境变量 `YANSHOU_PROJECT=/path/to/project` 在启动时自动打开该工程文件夹。

主进程 `src/main.js` 通过 `src/runtime.js` 解析安装根与便携 Python，再 `child_process` 调用：

- `assets/engine/shell_bridge.py`（建档 / 打开 / 字段 / 子表 / 成册 / 打印 / 预览 / 回收站 / 周报月报 / AI 闸门 / **模板体检**）
- 其余引擎仍为 Python，**不把引擎改写成 JS**。

嵌入编辑走 `src/editor/host.js` → `src/editor/bundle.cjs`（由 `packages/docx-embed` 把钉死的 `vendor/genoffice` 打成 CJS）。打开工程 DOCX → 右侧「正文」改正文/表格文字 → 保存回工程副本。路径落在 `assets/templates/` 会抛 `TEMPLATE_PROTECTED`。

打包后根目录是 `process.resourcesPath`（extraResources），开发时是仓库根。工作目录打包后写到 `userData/work`，避免只读安装目录。

编辑模式由 `src/fidelity-status.json` 声明：`genoffice-embed` 或回退 **E1**。不是 Office 替代品。

打包：`npm run pack:linux` / `npm run pack:win`，说明见 [`docs/打包说明.md`](../docs/打包说明.md)。`pack.js` 会先 `embed:build`。

AI 入口在无 `DEEPSEEK_API_KEY` 或断网时全部置灰；**生成周报/月报不依赖模型**。
