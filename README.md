# 验收资料编辑软件

给一个工程项目做的**验收资料自动生成与管理系统**。对标「筑业云资料」：

**建一个工程 = 建一个文件夹；点一次「一键成册」= 只生成必选目录项并填好项目字段。可选表默认 0 份，右键「新建表格」才追加。**

当前进度：**P7 交付 + GenOffice 源码嵌入**（P0 填充回归仍保持 37 份 / 171 处 / 0 残留；P1–P7 保持绿）。编辑内核优先 **嵌入 `vendor/genoffice` 的 `docx-engine`（Apache-2.0 钉死 commit）**：右侧「正文」可改正文/表格文字并写回**工程副本**。`pnpm add @genoffice/docx-engine` 仍是 npm 404（private:true），不再当作产品 V1。嵌入不可用时回退 **E1 表单 + 只读预览**。不是 Word 替代品。发行包内嵌引擎、模板与便携 Python；**dsh 运行时约 420MB，基础包默认不含**。凭据只走 `DEEPSEEK_API_KEY` 环境变量。

> 施工入口请先读 [`docs/00_交付说明.md`](docs/00_交付说明.md) 和 [`docs/设计文档/施工交接说明.md`](docs/设计文档/施工交接说明.md)，不要从设计文档第一页通读。

---

## 怎么跑 P0 回归

需要 Python 3.12+（标准库即可，**不要装 lxml / python-docx / docxtpl**）。

```bash
# 推荐：一条命令跑完回归（断言 37 份 / 171 处已填充 / 0 残留）
python tools/run_regression.py

# 等价的手工试跑
python assets/engine/fill_engine.py --demo
python assets/engine/fill_engine.py --demo --json
```

`--demo` 读取 [`examples/demo_project.json`](examples/demo_project.json)，只读 [`assets/templates/`](assets/templates/)，把结果写到 **`work/demo-fill/`**（不会回写模板）。

成功时最后一行（`--json`）形如：

```json
{"ok": true, "engine": "fill", "summary": "37 份 / 171 处已填充 / 0 处残留", "stats": {"docs": 37, "filled": 171, "residual": 0, ...}}
```

stdout 中会穿插 `#PROGRESS <done>/<total> <文件>` 进度行；解析 JSON 时只看**最后一行**。

---

## 怎么跑 P1（数据与规则）

同样是 Python 3.12+ 标准库（**不要装 PyYAML / lxml**；规则 YAML 由 `lib/yaml_lite.py` 解析）。

```bash
python tools/run_p1_regression.py

python assets/engine/datafill_engine.py \
  --project examples/demo_project.json \
  --out work/fillplan.json --json
```

FillPlan 写入 `--out`（`sort_keys` 规范化 JSON）。同一输入跑两次，文件逐字节一致。把日期字段配成自动填、或规则引用字典里不存在的 key → **exit 3**。

---

## 怎么跑 P2（生成与校验闭环）

```bash
python tools/run_p2_regression.py

# 一键成册（仅必选：首刀 二-01～05；可选默认 0 份）
python assets/engine/docgen_engine.py \
  --project work/p2-booklet/project.json --item all --json

# 编号（目录项内不重排：删掉 02，03 仍是 03）
python assets/engine/numbering_engine.py \
  --project work/p2-booklet/project.json --item 二-01 --json

# 校验闸门（残留带 段N / 表M行R列C 定位）
python assets/engine/verify_engine.py \
  --dir work/p2-booklet --project work/p2-booklet/project.json --json
```

`docgen --item all` **只生成必选**（ADR-21）；重复点「生成全部」跳过已有必选、**不会**批量生成可选。`--item 二-01 --count 1` 在已有 01 时追加 02。目录树右键「新建表格」= 对该 item 显式 `--item`。无模板项三选一：`--mode blank|upload|skip`（默认 `template`，无模板时按 blank 落盘）。

填充引擎 v1.0 默认 `--anchor on`：每个已填字段写 `yz_<key>` 书签 + `word/customXml/item1.xml` 台账。`--anchor off` 回到纯替换。缺值仍保留 `{{key}}`；日期不自动填。

---

## 怎么跑 P3（dsh / AI 层）

组合包源码在 [`packages/dsh-yanshou-docs`](packages/dsh-yanshou-docs)（v0.2：七个工具、双轨制配置、`dsh.bundle.patch` only）。**不 fork dsh**；凭据只走 `DEEPSEEK_API_KEY` 环境变量。

```bash
# 不需要模型 Key：静态契约 + 模板保护单测 +（有 pnpm 则）build/pack +（有 dsh 则）真 --dump-config
python tools/run_p3_smoke.py
```

---

## 怎么跑 P4（V1–V4 保真门 + Electron 壳）

Python 3.12+ 标准库 + **`pypdf`**（整册 PDF 合并/页码；中文嵌入系统 TTF，本仓库用 `requirements-p4.txt`）。

```bash
pip install -r requirements-p4.txt
python tools/run_p4_gate.py     # V1–V4 证据（写 src/fidelity-status.json）
python tools/run_p4_smoke.py    # 门禁 + shell_bridge + 打印状态持久化 + P0–P3 回归
# 或
npm run p4:smoke
```

桌面壳（Node ≥ 22.14，建议 22.19+）：

```bash
npm install
npm run dev
# 可选：跳过系统文件夹对话框，直接打开已有工程（GUI 试跑 / 演示）
YANSHOU_PROJECT=/path/to/project npm run dev
```

Linux 无沙箱环境会自动加 `--no-sandbox`。界面：新建/打开工程文件夹 → 左侧三页签树 → 右侧 **正文（嵌入编辑）** / 只读预览 / 台账 / 子表 / 作业 + 39 字段 E1 表单 → **一键成册** → 打印标记 → 导出整册 PDF。正文保存只写工程副本，**永不写 `assets/templates/`**。

V1–V4 怎么读结果：看 PR 说明或 `src/fidelity-status.json`。**V1 是源码钉死 + typecheck + bundle**，不是 npm add。**V2 必须走 Block 渲染器**（`tools/run_embed_gate.mjs`），不能只用 zip/XML。**V3 必须走 `saveDocx` 的 generated/xml 路径再 `diff_parts`**；clone-only XML 不算产品通过。嵌入失败时壳回退 E1。

---

## 怎么跑嵌入编辑（GenOffice 源码）

`@genoffice/docx-engine` **未发布 npm**。产品依赖钉死在 [`vendor/genoffice/`](vendor/genoffice/)（Apache-2.0，见 `PIN.json` / `LICENSE` / `NOTICE`）。官方 `apps/docs` TipTap 壳没有嵌入 API，未整包引进。

```bash
npm install                 # prepare → src/editor/bundle.cjs
npm run embed:typecheck
npm run embed:gate          # V2 渲染 37 份 + V3 改一字 saveDocx + diff_parts
python tools/run_embed_regression.py
# 或
npm run embed:smoke
```

工作副本写到 `work/embed-v23/`，不碰模板。嵌入失败时壳回退 E1，状态条会写明原因。

---

## 怎么跑 P5（编辑升级 + 子表）

```bash
python tools/run_p5_regression.py
# 或先跳过 P0–P4
python tools/run_p5_regression.py --skip-prior
npm run p5:smoke
```

- `subtable_engine.py`：按 `字段字典.json` → `tables[].columns` 识别 8 张子表，喂 N 行到空表出 N 行（克隆行、不动 `w:tblGrid`）。Zip→XML 写工程文档，**永不写 `assets/templates/`**。空数组保留模板静态行。
- 壳：E1「子表」页 8 张网格；保存走引擎回写已生成文档。
- 改项目级字段会提示「仅本份 / 同步全册 / 撤销」。仅本份只写 `_documents[本份]`，不改档案、不碰其他文档。有 P2 `yz_` 锚点则按书签回写。
- 成册时程序侧把八 1 卷册补到 8 分册、八 2 目录勾选表按清单生成、八 3 隔页扩到 8 组。

```bash
python assets/engine/subtable_engine.py \
  --doc work/some.docx --table deviceList --data rows.json --json
```

---

## 怎么跑 P6（AI 能力落地）

施工日志 → 周报 → 月报是 **T7 确定性聚合**（`aggregate` / `statistic` / `count` 规则），不调用模型。起草/润色/扩写/智能填表/查错问答走壳侧 AI 入口；**无 `DEEPSEEK_API_KEY` 或断网时全部置灰**，其余功能照常用。凭据只读环境变量，不进 Git。

```bash
python tools/run_p6_regression.py
# 或先跳过 P0–P5
python tools/run_p6_regression.py --skip-prior
npm run p6:smoke
```

```bash
# 5 篇带 logDate 的施工日志 → 周报四栏（窗口内无日志则 exit 1，不生成空周报）
python assets/engine/aggregate_engine.py \
  --period week --project work/some/project.json \
  --from 2026-09-07 --to 2026-09-11 --json

python assets/engine/ai_engine.py --action status --json
python assets/engine/ai_engine.py --action extract --text '工程名称：……' --json
# 下面这条在无 Key 时 ok=false，不会伪造润色正文
python assets/engine/ai_engine.py --action polish --text '完成设备安装。' --json
```

Live 模型验收（本机有 Key 时才跑，CI/无 Key 的 VM 记 SKIP）：

```bash
export DEEPSEEK_API_KEY=...          # 不要写进仓库
python assets/engine/ai_engine.py --action polish --text '完成设备安装。' --project <工程>/project.json --json
```

AI 落盘追加写入工程 `_logs/ai.jsonl` 与 `_logs/changes.jsonl`。智能填表必须先出确认面板（`confirmed[]`），空列表拒绝回写。

---

## 怎么跑 P7（交付固化）

用户手册：[`docs/使用手册.md`](docs/使用手册.md)。打包与 Windows 目标：[`docs/打包说明.md`](docs/打包说明.md)。

```bash
python tools/run_health.py              # 模板体检（37 份 / 171 处 / 只读保护）
python tools/run_p7_regression.py --skip-pack
npm run p7:smoke                        # 若 dist/linux-unpacked 已存在会顺带验包

# 构建 Linux 烟测包（本机即可）
npm install
npm run pack:linux

# Windows 安装包 + 免安装 zip（必须在 Windows 构建机 / GitHub windows-latest）
npm run pack:win
```

干净 Windows **不要求**系统 Python / Node：electron-builder 打进去的壳 + `scripts/fetch_python_runtime.py` 拉的 embeddable CPython + vendor 的 pypdf。本 Linux 环境不能交叉链接出 `.exe`，只保证脚本、CI 配置和 linux dir/zip。dsh 运行时默认不打进基础包。

---

## 可选：加装 dsh / AI 运行时

基础发行包**不含**约 420MB 的 dsh 运行时。需要模型后端时再装：

```bash
pip install "deepseek-harness-sdk==0.1.5rc1"   # ADR-18：原生 dsh，不依赖系统 Node
export DSH_HOME=/path/to/dsh-home              # 必须非空，绝不回退 ~/.dsh
mkdir -p "$DSH_HOME"
export DEEPSEEK_API_KEY=...                    # 不要写进 cordis.patch.yml / Git

dsh --profile yanshou --from-default-profile sdk
cd packages/dsh-yanshou-docs && pnpm install && pnpm build && pnpm pack
dsh plugin --profile yanshou add ./dsh-yanshou-docs-0.2.0.tgz   # 必须用 tarball，不要 link:
dsh --profile yanshou --dump-config
# 期望：# == dsh-yanshou-docs
# bundles = [@deepseek-ai/dsh-base, @deepseek-ai/dsh-sdk-app, dsh-yanshou-docs]
```

Headless / CI 默认 `ask` 会挂：生产壳走审批回调（P4）；CI 才用 `DSH_PERMISSION_MODE=danger-full-access`（见包内 `scripts/headless.env`）。**不要**把该值写进组合包 patch。

---

## 仓库布局（双轨制）

按 [`施工交接说明.md` §5](docs/设计文档/施工交接说明.md) 落地：**安装资产只读 + 工程数据可拷走**。

```
assets/                         ← 安装资产（只读约定）
  templates/                    37 份现役模板（中文分册名，冻结；引擎不得写入）
  templates-backup/             注入后冻结副本 + SHA256清单.json
  spec/                         字段字典 / 表名缩写字典 / 填数规则.yaml（P1 正式 9 类规则）/ 软件目录.docx
  engine/                       确定性引擎 + export/shell_bridge/ai + 体检桥
  runtime/                      便携 Python 说明（二进制由打包脚本拉到 build/runtime）
lib/                            project.json、规则、子表、同步、体检、CJK PDF
  vendor/                       打包时 pip 的 pypdf（gitignore）
packages/dsh-yanshou-docs/      P3 组合包源码（运行时不打进基础包）
tools/                          体检与回归（run_health / run_p7_regression 等）
scripts/                        fetch_python_runtime / prepare_pack / pack.js
docs/                           使用手册.md · 打包说明.md · 设计文档
examples/demo_project.json      试跑工程数据
src/                            Electron 壳（E1 表单 + 嵌入正文编辑 + 打包）
vendor/genoffice/               钉死的 GenOffice 源码（docx-engine + custgeom，Apache-2.0）
packages/docx-embed/            Block 渲染器 + saveDocx 适配
.github/workflows/pack.yml      Linux 烟测 + Windows nsis/zip/portable
work/                           引擎输出（gitignore；永不指向 templates）
```

模板文件名保持中文（本环境 / git 均支持 UTF-8）。若某台机器无法检出中文路径，对照 `assets/spec/表名缩写字典.csv` 的「目录项名」列与分册名即可。

工程数据目录（用户选的文件夹）的契约见 [`数据与规则规格.md` §1.2](docs/设计文档/数据与规则规格.md)。P4 壳把该文件夹当作工程：里面是 `project.json` + 分册目录。

---

## 7 个引擎

| 脚本 | 状态 | 说明 |
|---|---|---|
| `assets/engine/fill_engine.py` | **P2 v1.0** | zip → XML → 按 infolist 写回；FillPlan；`yz_` 书签 + customXml 锚点 |
| `datafill_engine.py` | **P1 可用** | 9 类规则 → FillPlan；`--json` / exit 0/1/2/3 |
| `docgen_engine.py` | **P2 可用** | 一键成册 / 单份 / 追加 / 无模板三选一 / 编号绑定 |
| `numbering_engine.py` | **P2 可用** | `{合同编号}-{表名缩写}-{流水号}`；删 02 不重排 03 |
| `verify_engine.py` | **P2 可用** | §7 闸门；残留带 段N/表M行R列C |
| `subtable_engine.py` | **P5 可用** | 8 张子表按表头列名识别；行克隆；空数组保留静态表 |
| `aggregate_engine.py` | **P6 可用** | 日志→周报→月报（T7；无源 exit 1） |
| `ai_engine.py` | **P6 可用** | status/extract/draft/polish/expand/apply/qa；无 Key 不伪造 |
| `export_engine.py` | **P4 可用** | 单份/整册 PDF（pypdf 合并 + 中文页码） |
| `shell_bridge.py` | **P7** | Electron JSON 桥：成册/子表/周报/AI 闸门/**模板体检** |

通用约定（[`数据与规则规格.md` §3 / §6](docs/设计文档/数据与规则规格.md)）：具名长参数、`--json` 时 stdout **最后一行**为契约 JSON、`#PROGRESS` 进度行、退出码 `0/1/2/3`。

---

## 红线

1. **绝不写入 `assets/templates/**`**（试写会抛 `TemplateProtectionError`）。
2. **docx 一律部件级操作**，不用 python-docx / docxtpl 重排。
3. **缺值保留 `{{key}}` 原样**；**日期不自动填**。

---

## 已知漂移（故意 fail-loud）

`python tools/backup_templates.py --verify-only` 会对下面 2 份报源↔备份不一致并 **exit 1**。内容零丢失，冻结备份故意不覆盖，回归脚本会记录此事而**不把它当 P0 失败**：

- `七、竣工验收分册（政务信息化项目）/1、项目情况简介.docx`（Word 另存）
- `二、过程分册/4、施工组织方案.docx`（删了 1 个 `★`）

详见 [`docs/00_交付说明.md`](docs/00_交付说明.md) §六、[`docs/设计文档/模板资产核查报告.md`](docs/设计文档/模板资产核查报告.md)。

示例数据里文档编号 `YY123-SBAZDJLSB-01` 已按缩写字典改为 `YY123-SBAZDSJLB-01`（`SBAZDSJLB`）。`试运行记录` 的覆盖键已对齐实际文件名 `6、试运行记录表.docx`。

---

## 文档地图

| 你要干什么 | 读哪份 |
|---|---|
| 整个项目 / 排期 | `docs/设计文档/施工交接说明.md` §3–§6 |
| 写 Python 引擎 | `docs/设计文档/数据与规则规格.md` |
| 接 dsh / AI | `docs/设计文档/P3-AI层接入施工图.md` |
| 模板资产 | `docs/设计文档/模板占位符标准化规范.md` |
| 架构意图 | `docs/设计文档/软件设计方案-v2.0.md` |
| 用户怎么用 / 怎么打包 | `docs/使用手册.md` · `docs/打包说明.md` |
