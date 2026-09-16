# 验收资料编辑软件

给一个工程项目做的**验收资料自动生成与管理系统**。对标「筑业云资料」：

**建一个工程 = 建一个文件夹；点一次「一键成册」= 套完 37 份模板并填好 39 个字段。**

当前进度：**P5 编辑升级 + 子表**（P0 填充回归仍保持 37 份 / 171 处 / 0 残留；P1–P4 保持绿）。编辑内核走 **E1 表单 + 只读预览 + 8 张子表网格**（V1 `pnpm add @genoffice/docx-engine` 为 npm 404，V3 产品路径 BLOCKED，不假装通过；不做 E2/E3 流式内核）。

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

# 一键成册（56 项：37 套模板 + 19 无模板空白）
python assets/engine/docgen_engine.py \
  --project work/p2-booklet/project.json --item all --json

# 编号（目录项内不重排：删掉 02，03 仍是 03）
python assets/engine/numbering_engine.py \
  --project work/p2-booklet/project.json --item 二-01 --json

# 校验闸门（残留带 段N / 表M行R列C 定位）
python assets/engine/verify_engine.py \
  --dir work/p2-booklet --project work/p2-booklet/project.json --json
```

`docgen --item all` 默认跳过已生成的文档（重复点「生成全部」不重复）；`--item 二-01 --count 1` 在已有 01 时追加 02。无模板项三选一：`--mode blank|upload|skip`（默认 `template`，无模板时按 blank 落盘以保证 56 项都生成）。

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

Linux 无沙箱环境会自动加 `--no-sandbox`。界面：新建/打开工程文件夹 → 左侧三页签树（填写四色点 + 独立「印」角标）→ 右侧台账/只读预览/作业面板 + 39 字段 E1 表单 → **一键成册**（child_process：`datafill` → `fill` → `docgen` → `verify`）→ 打印标记（`_printStates`）→ 导出整册 PDF。

V1–V4 怎么读结果：看 PR 说明或 `src/fidelity-status.json`。**V3 未放行时不要接 genoffice 编辑器。**

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

## 仓库布局（双轨制）

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
  engine/                       7 个确定性引擎 + P4 export/shell_bridge + P5 子表
  runtime/                      内嵌 Python 预留位（P7）
lib/                            project.json 原子读写、字段字典、规则引擎、编号池、CJK PDF、子表/同步
packages/dsh-yanshou-docs/      P3 组合包 v0.2（七工具 / patch 层 / 模板保护）
tools/                          体检与回归脚本（含 run_p1 / run_p2 / run_p3_smoke / run_p4_smoke / run_p5_regression.py）
docs/                           交付说明 + 设计文档 + 原始资料 + AI 组合包指针 + dsh 参考
examples/demo_project.json      试跑工程数据
src/                            Electron 壳 MVP（E1）
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
| `aggregate_engine.py` | P0 骨架 | P6 日志→周报→月报 |
| `export_engine.py` | **P4 可用** | 单份/整册 PDF（pypdf 合并 + 中文页码） |
| `shell_bridge.py` | **P5** | Electron JSON 桥：建档/字段/子表/_assets/半自动同步/成册/打印 |

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
