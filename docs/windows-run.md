# Windows 运行说明（备胎线 v1）

面向不熟命令行的 Windows 用户。请用 **PowerShell**（Win 键搜「PowerShell」）。不要把 cmd 的 `set` / `rmdir` / `cd /d` 粘进 PowerShell。

仓库：<https://github.com/yydd-gif/ipw>  
产品：验收到手（acceptance-studio）v1 · 表单 + 只读预览  
需要：Node.js **20+**（推荐 22 LTS）、本机 **Python 3**（命令能跑 `python` 或 `python3`）

---

## 1. 拿代码

任选：GitHub Desktop 克隆 `main`，或仓库页 Code → Download ZIP，解压到例如 `文档\ipw`。确认该层有 `package.json`。

## 2. 安装 Node.js

1. <https://nodejs.org/zh-cn> 下载 LTS msi，勾选 **Add to PATH**。
2. **关掉旧终端，新开 PowerShell**，检查：

```powershell
node -v
npm -v
```

应为 v20 或更高。

系统 Node 路径损坏时，把 Node zip 解到 `文档\nodejs`，每个新窗口先执行：

```powershell
$env:Path = "$env:USERPROFILE\Documents\nodejs;" + $env:Path
```

## 3. 安装 Python 3

1. <https://www.python.org/downloads/windows/> 安装 3.11+，勾选 **Add python.exe to PATH**。
2. 新开 PowerShell：

```powershell
python --version
```

本仓库 `fill_engine.py` **只用标准库**，一般不必 `pip install`。官方引擎 / 37 套模板会在后续 PR 再钉依赖。Win 便携 Python 随包装发也延期。

若 `python` 可用而 `python3` 没有，可先：

```powershell
Set-Alias python3 python
```

或安装后保证 `python3` 在 PATH。应用默认找 `python3`，也可用环境变量 `ACCEPTANCE_PYTHON` 指向 `python.exe`。

## 4. 安装依赖并运行

在项目根（能 `dir package.json`）的 PowerShell：

```powershell
npm install
npm run typecheck
npm test
npm run dev
```

仓库根目录 `.npmrc` 已设置：

```text
electron_mirror=https://npmmirror.com/mirrors/electron/
```

这是 `@electron/get` 读取的 `npm_config_electron_mirror`。普通 `npm install` 就会从 npmmirror 拉 `electron.exe`，**不必**再手设环境变量。

### Electron 二进制仍缺失时（PowerShell）

```powershell
$env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
Remove-Item -Recurse -Force .\node_modules\electron -ErrorAction SilentlyContinue
npm install electron --save-dev --force
Get-ChildItem .\node_modules\electron\dist\electron.exe
npm run dev
```

或运行 `.\scripts\ensure-electron.ps1`。不要用 cmd 的 `set`。若仍没有 `electron.exe`，把项目目录加入杀毒排除后再试。

## 5. 可选：LibreOffice 转 PDF

安装 [LibreOffice](https://www.libreoffice.org/) 后，导出当前条目会走 `soffice --headless --convert-to pdf`。没有则写入占位 PDF（文件头仍是 `%PDF-`），可改另存填充后的 `.docx`。

## 6. 常见问题

- **npm 不是内部命令**：新开终端；或按第 2 节把便携 Node 加进当前窗口 PATH。
- **fill / 一键成册提示找不到 Python**：新开终端跑 `python --version`；设置 `$env:ACCEPTANCE_PYTHON = 'C:\Path\to\python.exe'`。
- **公司代理**：`npm config set proxy http://主机:端口` 与 `https-proxy` 后再 `npm install`。
