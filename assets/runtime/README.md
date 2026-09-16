便携 CPython 预留位（P7）。

- 仓库里**不提交** 20–40MB 的解释器。
- 打包时由 `scripts/fetch_python_runtime.py` 拉到 `build/runtime/`，electron-builder 再拷到 `resources/python/`。
- Windows：python.org embed-amd64（干净机器不需要系统 Python）。
- Linux：python-build-standalone `install_only`（抓取失败则烟测包回退系统 python3，并写入 `RUNTIME.json`）。

引擎已改为标准库 `xml.etree.ElementTree`，**不再依赖 lxml**。PDF 导出用 `pypdf`（打包进 `lib/vendor`）。
