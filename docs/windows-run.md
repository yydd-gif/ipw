# Windows 运行说明（验收到手 M1）

本文面向**不熟命令行的 Windows 用户**。按编号做即可：先拿到代码，再装好 Node，最后在项目根目录跑三条命令。

**请用「命令提示符」粘贴本文命令**（按 `Win` 键搜索「命令提示符」或 `cmd`）。Windows 11 默认的 PowerShell 也能用，但个别命令写法不同，文中已单独标出。

仓库：<https://github.com/yydd-gif/ipw>（默认分支 **main**）  
产品：验收到手（acceptance-studio）  
需要：Node.js **20 及以上**（推荐 **22 LTS**；本机也曾用过 24，一般也可以）

完成后应能跑通：

1. `npm run verify:m1`（无界面校验核心链路）
2. `npm run dev`（打开 Electron 桌面窗口）

---

## 0. 先看一眼：系统 Node 是否还能用

本机 Yydd 曾经出现过：**系统 Node 路径损坏**，原来的 `D:\Program Files\nodejs` 不可用，当时改用「文档」目录下的便携版 Node。

**当前系统 Node 可能已经恢复。** 请先做一次检查，再决定走「首选安装」还是「便携版应急」。

1. 按 `Win` 键，搜索 **命令提示符**（或 **PowerShell**），打开一个新窗口。
2. 复制下面这一行，粘贴进去，按回车：

```bat
node -v
```

3. 再复制这一行，回车：

```bat
npm -v
```

| 结果 | 怎么做 |
| --- | --- |
| 两个命令都成功，且 `node -v` 显示 `v20` 或更高（例如 `v22.x`、`v24.x`） | 系统 Node 可用。跳到 [第 1 节拿代码](#1-准备工作拿代码)，装 Node 可跳过。 |
| 提示「不是内部或外部命令」，或报错找不到文件 | 系统 Node 没装好，或 PATH 坏了。走 [第 2 节](#2-安装-nodejs两条路径)。 |
| `where.exe node` 指向 `D:\Program Files\nodejs`，但该文件夹不存在 / 打不开 | **不要再用这个路径。** 走 [2.2 便携版应急](#22-备用系统-node-坏了便携版)。 |

查看 Node 实际指向哪里（可选；命令提示符和 PowerShell 都用这一行）：

```bat
where.exe node
```

**警告：不要依赖已损坏的 `D:\Program Files\nodejs`。** 即使 PATH 里还写着这个目录，也不要从那里运行 `node.exe`。

---

## 1. 准备工作：拿代码

**不必先装 Git。** 下面两种方式任选其一。

建议把代码放到好找的位置，例如：`文档\ipw`（完整路径通常是 `C:\Users\你的用户名\Documents\ipw`）。

### 方式 A：用 GitHub Desktop 克隆 main（推荐，以后好更新）

1. 打开 <https://desktop.github.com/> ，下载并安装 **GitHub Desktop**（安装过程里会带上 Git，一般不用单独装）。
2. 打开 GitHub Desktop，登录 GitHub 账号（没有就先注册）。
3. 菜单 **File → Clone repository…**（文件 → 克隆仓库）。
4. 切到 **URL** 页，仓库地址填：

```text
https://github.com/yydd-gif/ipw
```

5. Local path（本地路径）选一个空文件夹，例如 `文档\ipw`。
6. 点 **Clone**。克隆完成后，确认当前分支是 **main**（窗口顶部一般会显示）。

之后每次要更新代码：在 GitHub Desktop 里打开这个仓库，点 **Fetch origin / Pull**。

### 方式 B：下载 main 的 ZIP（不用 Git）

1. 打开仓库页面：<https://github.com/yydd-gif/ipw>
2. 确认左上角分支是 **main**（绿色按钮上写着 `main`）。
3. 点绿色的 **Code** 按钮 → **Download ZIP**。  
   也可直接下载：<https://github.com/yydd-gif/ipw/archive/refs/heads/main.zip>
4. 解压到例如「文档」。解压后常见文件夹名是 **`ipw-main`**（这是正常的）。
5. 你可以：
   - 把 `ipw-main` **重命名**为 `ipw`；或
   - 保持 `ipw-main` 不改名，后面 `cd` 时用这个名字。

**怎么确认拿到的是项目根目录：** 打开该文件夹，里面应能看到 `package.json`、`README.md`、`src` 等。以后所有命令都在**这一层**执行，不要进到 `src` 里面再跑。

---

## 2. 安装 Node.js（两条路径）

### 2.1 首选：官网 LTS 安装包（系统 Node 正常时用这个）

1. 打开 Node 中文官网：<https://nodejs.org/zh-cn>
2. 下载 **LTS** 的 **Windows 安装包**（文件名类似 `node-v22.x.x-x64.msi`）。推荐 22；不要故意选很旧的 18。
3. 双击安装。安装向导里请勾选：
   - **Add to PATH**（添加到 PATH）——必须勾
   - 其余保持默认即可
4. 点到结束。**关掉已经打开的命令提示符 / PowerShell**，再新开一个（旧窗口读不到新 PATH）。
5. 在新窗口里验证：

```bat
node -v
npm -v
```

应分别打出版本号。`node -v` 需要是 **v20 或更高**。

若验证失败，或你知道本机曾经把 Node 装在 `D:\Program Files\nodejs` 且那个目录已坏：不要反复修那个旧路径，改走 2.2。

### 2.2 备用：系统 Node 坏了（便携版）

适用情况：

- `node` / `npm` 提示不是内部命令
- `where.exe node` 指向 `D:\Program Files\nodejs`，但该目录不可用
- 公司电脑不允许往 `Program Files` 里装软件

**不要**再去修复或依赖 `D:\Program Files\nodejs`。改用「文档」下的便携版。

#### 下载 Windows 二进制 zip（便携，免安装）

1. 打开下载页：<https://nodejs.org/zh-cn/download>  
   或发行目录：<https://nodejs.org/dist/>
2. 进入 **22.x 最新 LTS** 那一层（文件夹名类似 `latest-v22.x` 或 `v22.xx.x`）。
3. 下载 **Windows 64 位 zip**，文件名类似：

```text
node-v22.xx.x-win-x64.zip
```

（不要下 `arm64`，除非你明确知道自己是 ARM 电脑。）

4. 解压到固定位置，推荐：

```text
文档\nodejs
```

完整路径示例：`C:\Users\你的用户名\Documents\nodejs`

解压后，这个文件夹里应能直接看到 **`node.exe`** 和 **`npm.cmd`**。  
如果多了一层 `node-v22.xx.x-win-x64`，请把**里面那一层**的内容放到 `文档\nodejs`，保证路径是：

```text
文档\nodejs\node.exe
文档\nodejs\npm.cmd
```

#### 每次开终端时：先进入项目，再启用便携 Node

便携版**不会自动进 PATH**。每次新开「命令提示符」或 PowerShell，都要先做下面两步（同一窗口里连续做，不要关窗口）。

**1）进入项目根目录**（按你实际放代码的位置改路径）：

命令提示符（cmd）：

```bat
cd /d %USERPROFILE%\Documents\ipw
```

若 ZIP 解压后文件夹仍叫 `ipw-main`：

```bat
cd /d %USERPROFILE%\Documents\ipw-main
```

若用 GitHub Desktop 且克隆到了 `文档\GitHub\ipw`：

```bat
cd /d %USERPROFILE%\Documents\GitHub\ipw
```

确认当前目录有 `package.json`：

```bat
dir package.json
```

**2）让当前窗口用便携 Node（两种写法，选一种）**

写法甲：临时把便携目录加到**当前会话** PATH（推荐，后面可以直接打 `npm`）：

命令提示符：

```bat
set "PATH=%USERPROFILE%\Documents\nodejs;%PATH%"
```

PowerShell：

```powershell
$env:Path = "$env:USERPROFILE\Documents\nodejs;" + $env:Path
```

然后验证：

```bat
node -v
npm -v
where.exe node
```

`where.exe node` 的第一行应是 `...\Documents\nodejs\node.exe`，**不应**再是 `D:\Program Files\nodejs\node.exe`。

写法乙：不改 PATH，用完整路径调用（把 `你的用户名` 换成实际用户名，或继续用 `%USERPROFILE%`）：

```bat
"%USERPROFILE%\Documents\nodejs\node.exe" -v
"%USERPROFILE%\Documents\nodejs\npm.cmd" -v
```

后面安装和运行把 `npm` 全部换成完整路径，例如：

```bat
"%USERPROFILE%\Documents\nodejs\npm.cmd" install
"%USERPROFILE%\Documents\nodejs\npm.cmd" run verify:m1
"%USERPROFILE%\Documents\nodejs\npm.cmd" run dev
```

**注意：** 关掉终端后，临时 PATH 会消失。下次打开窗口，要重新 `cd` 到项目，并重新执行上面的 `set PATH`（或继续用完整路径）。

---

## 3. 在项目根目录执行（核心三步）

以下假定：

- 当前窗口已经 `cd` 到项目根（能 `dir package.json`）
- `node -v` / `npm -v` 已成功（系统安装或便携 PATH 均可）

### 第 1 步：安装依赖（含 postinstall 生成模板）

复制这一行，回车：

```bat
npm install
```

第一次会下载较长时间。成功结束时，一般会看到类似 `added xxx packages`，**没有大片红色报错**。

`npm install` 结束时会自动跑 **postinstall**，生成 `templates/` 里的示例 `.docx`（施工日志、周报等 Word 模板）。

若这一步失败，先看 [第 4 节常见问题](#4-常见问题)。不要急着开窗口。

### 第 2 步：无界面校验 M1（先确认核心链路）

```bat
npm run verify:m1
```

这一步**不会弹出软件窗口**。它会在后台走一遍 M1 演示路径并检查导出 Zip 结构。  
成功时终端里应是正常结束（退出码 0，没有 `Error` 堆栈）。请先跑通这一步，再开桌面窗口。

### 第 3 步：打开桌面窗口

```bat
npm run dev
```

应弹出 **验收到手** 的 Electron 窗口。演示步骤见仓库根目录 [README.md](../README.md) 的「推荐演示路径」。

开发时请保持这个终端不要关：关掉终端等于关掉开发服务，窗口也会一起没。

---

## 4. 常见问题

### 4.1 Electron 窗口起不来

- 先确认 `npm run verify:m1` 已经成功。核心链路没过，先不要纠结窗口。
- 看终端有没有红色报错。常见是 Electron 二进制没下完：再执行一次 `npm install`。
- 公司杀毒软件可能拦截 `node_modules\electron` 里的 `electron.exe`。把项目目录加入杀软「排除项」，或临时允许后再试 `npm run dev`。
- 确认是在**有桌面的 Windows** 上运行（不是纯 SSH / 无界面服务器）。
- 关掉旧的 `npm run dev` 窗口，重新开一个终端，按第 2、3 节再走一遍（便携 Node 要重新设 PATH）。

### 4.2 「npm 不是内部或外部命令」

说明当前窗口找不到 npm。

1. 若刚用安装包装过 Node：**关掉终端，新开一个**，再试 `npm -v`。
2. 若 `where.exe npm` / `where.exe node` 指向 `D:\Program Files\nodejs`：这个路径本机曾经损坏，**不要继续用**。改用 [2.2 便携版](#22-备用系统-node-坏了便携版)。
3. 使用便携版时，确认本窗口已经执行过 `set "PATH=...\Documents\nodejs;%PATH%"`，或改用 `npm.cmd` 的完整路径。

### 4.3 node 版本过低

```bat
node -v
```

若显示 `v18`、`v16` 或更低：本仓库需要 **Node.js 20+**（推荐 22）。请按第 2.1 节安装 LTS，或按 2.2 换成便携 22，并保证 `where.exe node` 指向新的那份。

### 4.4 postinstall 失败 / `templates` 里没有 .docx

`npm install` 会自动执行 `postinstall` → `node scripts/generate-templates.mjs`，在 `templates/` 生成示例 Word。

若 `templates` 文件夹是空的，或缺少 `.docx`，在项目根目录再手动跑一次：

```bat
npm run generate:templates
```

便携 Node 且未设 PATH 时：

```bat
"%USERPROFILE%\Documents\nodejs\npm.cmd" run generate:templates
```

跑完后，`templates` 下应能看到例如 `2.10_施工日志.docx`、`2.12_项目周报.docx` 等文件。然后再执行 `npm run verify:m1`。

### 4.5 公司代理 / 杀软拦截

- **代理：** `npm install` 一直转圈或报 `ETIMEDOUT` / `ECONNREFUSED`。请向网管要 HTTP 代理地址，在**同一终端**里设置后再装（把地址换成你们公司的）：

```bat
npm config set proxy http://代理主机:端口
npm config set https-proxy http://代理主机:端口
```

装完若要取消：

```bat
npm config delete proxy
npm config delete https-proxy
```

- **杀软 / 上网管控：** 可能拦截 GitHub、nodejs.org、Electron 下载。把项目目录和 `文档\nodejs` 加入排除；或换能访问外网的网络后再 `npm install`。
- **GitHub ZIP 下不下来：** 请别人帮忙下载 `main.zip` 拷到 U 盘，再按第 1 节方式 B 解压。

### 4.6 怎么确认自己在项目根目录

在终端输入（命令提示符）：

```bat
echo %CD%
dir package.json
```

PowerShell 用：

```powershell
Get-Location
dir package.json
```

打印出来的路径应是代码文件夹（里面有 `package.json`）。若提示找不到 `package.json`，说明还没 `cd` 进去，或进错了子文件夹。

---

## 5. 命令速查（复制用）

系统 Node 正常时（已在项目根目录）：

```bat
npm install
npm run verify:m1
npm run dev
```

模板缺失时：

```bat
npm run generate:templates
```

便携 Node + 命令提示符（路径按实际修改）：

```bat
cd /d %USERPROFILE%\Documents\ipw
set "PATH=%USERPROFILE%\Documents\nodejs;%PATH%"
node -v
npm -v
npm install
npm run verify:m1
npm run dev
```
