# 验收资料编辑软件

给一个工程项目做的**验收资料自动生成与管理系统**。对标「筑业云资料」：

**建一个工程 = 建一个文件夹；点一次「一键成册」= 套完 37 份模板并填好 39 个字段。**

当前进度：**P1 数据与规则**（P0 填充回归仍保持 37 份 / 171 处 / 0 残留）。

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

## 仓库布局（双轨制）

按 [`施工交接说明.md` §5](docs/设计文档/施工交接说明.md) 落地：**安装资产只读 + 工程数据可拷走**。

```
assets/                         ← 安装资产（只读约定）
  templates/                    37 份现役模板（中文分册名，冻结；引擎不得写入）
  templates-backup/             注入后冻结副本 + SHA256清单.json
  spec/                         字段字典 / 表名缩写字典 / 填数规则.yaml（P1 正式 9 类规则）/ 软件目录.docx
  engine/                       7 个确定性引擎（fill P0 可用；datafill P1 可用；其余骨架）
  runtime/                      内嵌 Python 预留位（P7）
lib/                            project.json 原子读写、字段字典、规则引擎
tools/                          体检与回归脚本（stdlib only；含 run_p1_regression.py）
docs/                           交付说明 + 设计文档 + 原始资料 + AI 组合包 + dsh 参考
examples/demo_project.json      试跑工程数据
src/                            Electron 壳预留（P4）
work/                           引擎输出（gitignore；永不指向 templates）
```

模板文件名保持中文（本环境 / git 均支持 UTF-8）。若某台机器无法检出中文路径，对照 `assets/spec/表名缩写字典.csv` 的「目录项名」列与分册名即可。

工程数据目录（用户选的文件夹）的契约见 [`数据与规则规格.md` §1.2](docs/设计文档/数据与规则规格.md)，P0 尚未建桌面壳，试跑输出暂落在 `work/`。

---

## 7 个引擎

| 脚本 | 状态 | 说明 |
|---|---|---|
| `assets/engine/fill_engine.py` | **P0 可用** | zip → XML → 按 infolist 写回；同段落跨 run 合并替换 |
| `datafill_engine.py` | **P1 可用** | 9 类规则 → FillPlan；`--json` / exit 0/1/2/3 |
| `docgen_engine.py` | P0 骨架 | P2 一键成册 |
| `numbering_engine.py` | P0 骨架 | P2 编号（目录项内不重排） |
| `verify_engine.py` | P0 残留扫描 | P2 补齐 §7 全量校验 |
| `subtable_engine.py` | P0 骨架 | P5 八张子表 |
| `aggregate_engine.py` | P0 骨架 | P6 日志→周报→月报 |

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
