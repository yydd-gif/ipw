#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 DoD regression: T7 aggregate + offline AI gate (no live model required).

  python tools/run_p6_regression.py
  python tools/run_p6_regression.py --skip-prior

DoD（施工交接说明 §6 P6）:
  ① 一周 5 篇日志 → 周报四个栏目成型且事实无误（不编造）
  ② 抽取 10 个字段候选，人工确认后可一键回填
  ③ 断网/无 Key 时 AI 入口全部置灰，其余功能不受影响
  ④ 每次 AI 落盘都能在 _logs 里查到
Live model（DEEPSEEK_API_KEY）缺席时标记 SKIP，绝不把规则抽取/假正文当成模型回复。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from _paths import ENGINE, EXAMPLES, REPO, TEMPLATES, WORK  # noqa: E402

sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(REPO))

from _common import TemplateProtectionError, assert_not_template_write  # noqa: E402
from lib.aggregate import UNRECORDED  # noqa: E402
from lib.ai_extract import extract_candidates  # noqa: E402
from lib.ai_gate import ai_status  # noqa: E402
from lib.audit_log import read_jsonl  # noqa: E402
from lib.date_window import previous_week, resolve_window  # noqa: E402
from lib.field_dict import load_field_dict  # noqa: E402
from lib.project_store import read_project  # noqa: E402

BRIDGE = ENGINE / 'shell_bridge.py'
DICT = load_field_dict(REPO / 'assets' / 'spec' / '字段字典.json')
FABRICATED = '竣工验收顺利通过并荣获省级奖项'


def check(ok: bool, name: str, detail: str, failures: list) -> None:
    mark = 'PASS' if ok else 'FAIL'
    print('  [%s] %s — %s' % (mark, name, detail))
    if not ok:
        failures.append('%s: %s' % (name, detail))


def run(args, cwd=None, timeout=180, env=None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault('PYTHONUTF8', '1')
    return subprocess.run(
        args, cwd=cwd or str(REPO), env=e, timeout=timeout,
        capture_output=True, text=True, encoding='utf-8',
    )


def last_json(text: str) -> dict:
    lines = [ln for ln in (text or '').splitlines() if ln.strip()]
    if not lines:
        raise ValueError('empty output')
    for line in reversed(lines):
        if line.strip().startswith('{'):
            return json.loads(line.strip())
    raise ValueError('no JSON line')


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        raw = z.read('word/document.xml')
    xml = raw.decode('utf-8')
    return re.sub(r'<[^>]+>', '', xml)


def seed_project(folder: Path) -> Path:
    demo = json.loads((EXAMPLES / 'demo_project.json').read_text(encoding='utf-8'))
    demo['_documents'] = {}
    demo['_docs'] = {}
    logs = [
        ('2026-09-07', '完成机房桥架安装。', '晴', 8, '无', '无'),
        ('2026-09-08', '完成综合布线穿线。', '晴', 10, '电缆到货缺 2 箱。', '催厂家补货。'),
        ('2026-09-09', '完成核心交换机上架。', '雨', 12, '无', '无'),
        ('2026-09-10', '完成服务器加电与 BIOS 检查。', '晴', 9, '机柜PDU告警。', '协调供电回路。'),
        ('2026-09-11', '完成系统联调第一轮。', '阴', 11, '无', '安排下周培训场地。'),
    ]
    for i, (day, work, weather, n, issue, coord) in enumerate(logs, start=1):
        rel = '二、过程分册/10、施工日志/SGRZ-%s.docx' % day
        demo['_documents'][rel] = {
            'logDate': day,
            'todayWork': work,
            'weather': weather,
            'workerCount': n,
            'siteIssue': issue,
            'coordination': coord,
        }
        demo['_docs']['D-SGRZ-%03d' % i] = {
            'itemId': '二-10',
            'relPath': rel,
            'docNo': 'YY123-SGRZ-%03d' % i,
            'fillState': 'draft',
        }
    pj = folder / 'project.json'
    folder.mkdir(parents=True, exist_ok=True)
    pj.write_text(json.dumps(demo, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return pj


def extract_sample_text() -> str:
    return '\n'.join([
        '工程名称：洞庭湖数字财政升级工程',
        '建设单位：岳阳市财政局',
        '施工单位：湖南省俊昇伟业信息科技有限公司',
        '监理单位：湖南大福工程咨询有限公司',
        '合同编号：YY-P6-2026',
        '合同金额：128.50',
        '施工地点：岳阳市财政局机房',
        '项目经理：郭工',
        '方案审核批复（备案）文号：岳财信批〔2026〕99号',
        '建设目标：完成核心业务系统升级并通过竣工验收。',
        '主要建设内容：硬件安装、软件部署、联调与培训。',
    ])


def test_date_window(failures: list) -> None:
    print('\n-- date window')
    start, end = previous_week(date(2026, 9, 16))
    check(start.isoformat() == '2026-09-07' and end.isoformat() == '2026-09-13',
          'previous natural week', '%s ~ %s' % (start, end), failures)
    win = resolve_window('week', '2026-09-07', '2026-09-11')
    check(win == (date(2026, 9, 7), date(2026, 9, 11)),
          'explicit range', str(win), failures)


def test_empty_window(failures: list) -> None:
    print('\n-- empty window fails (no empty weekly)')
    demo = EXAMPLES / 'demo_project.json'
    proc = run([sys.executable, str(ENGINE / 'aggregate_engine.py'),
                '--period', 'week', '--project', str(demo), '--json'])
    payload = last_json(proc.stdout)
    check(proc.returncode == 1 and payload.get('ok') is False,
          'demo undated logs → exit 1',
          'exit=%s ok=%s %s' % (proc.returncode, payload.get('ok'), payload.get('summary')),
          failures)
    check('无法汇总' in (payload.get('summary') or ''),
          'error names the missing logs', payload.get('summary'), failures)


def test_five_logs_weekly(failures: list, work: Path) -> Path:
    print('\n-- 5 daily logs → weekly four columns')
    folder = work / 'p6-week'
    if folder.exists():
        shutil.rmtree(folder)
    pj = seed_project(folder)
    proc = run([
        sys.executable, str(ENGINE / 'aggregate_engine.py'),
        '--period', 'week', '--project', str(pj),
        '--from', '2026-09-07', '--to', '2026-09-11', '--json',
    ])
    print(proc.stdout[-800:] if proc.stdout else '')
    if proc.stderr:
        print(proc.stderr[-400:])
    payload = last_json(proc.stdout)
    check(proc.returncode == 0 and payload.get('ok') is True,
          'aggregate week ok',
          'exit=%s %s' % (proc.returncode, payload.get('summary')), failures)
    stats = payload.get('stats') or {}
    cols = stats.get('columns') or {}
    check(stats.get('docs') == 5, '5 source logs', str(stats.get('docs')), failures)
    done = cols.get('weeklyDone') or ''
    for fact in ('机房桥架', '综合布线', '核心交换机', '服务器加电', '系统联调第一轮'):
        check(fact in done, 'weeklyDone contains %s' % fact, done[:120], failures)
    check(FABRICATED not in done, 'no fabricated fact in weeklyDone', done[:80], failures)
    check(cols.get('weeklyUndone') == UNRECORDED,
          'weeklyUndone unrecorded (not invented)', cols.get('weeklyUndone'), failures)
    prob = cols.get('weeklyProblem') or ''
    check('电缆到货缺 2 箱' in prob and '机柜PDU告警' in prob,
          'weeklyProblem from siteIssue', prob, failures)
    check(prob.count('无') == 0 or '无；' not in prob,
          'skipped 无 in problems', prob, failures)
    plan = cols.get('weeklyPlan') or ''
    check('催厂家补货' in plan and '安排下周培训场地' in plan,
          'weeklyPlan from coordination', plan, failures)
    items = {it['key']: it for it in (payload.get('items') or []) if isinstance(it, dict)}
    weather = (items.get('weather') or {}).get('value') or ''
    check('晴 3 天' in weather and '雨 1 天' in weather and '阴 1 天' in weather,
          'weather countDays', weather, failures)
    workers = (items.get('workerCount') or {}).get('value') or ''
    check('平均 10 人' in workers and '最多 12 人' in workers,
          'workerCount avgAndPeak', workers, failures)

    created = payload.get('created') or {}
    dest = folder / (created.get('relPath') or '')
    check(dest.is_file(), 'weekly docx written', str(dest), failures)
    if dest.is_file():
        body = docx_text(dest)
        check('机房桥架' in body and '系统联调第一轮' in body,
              'docx has source facts', body[200:400], failures)
        check(FABRICATED not in body, 'docx has no fabricated prize', 'ok', failures)
        check('{{weeklyDone}}' not in body, 'weeklyDone placeholder filled', 'ok', failures)
        check('{{weeklyProblem}}' not in body, 'weeklyProblem filled', 'ok', failures)
        check('{{weeklyPlan}}' not in body, 'weeklyPlan filled', 'ok', failures)
        check('{{weeklyUndone}}' not in body, 'weeklyUndone column formed', 'ok', failures)

    changes = read_jsonl(folder / '_logs' / 'changes.jsonl')
    check(any(r.get('op') == 'engine.aggregate' for r in changes),
          'aggregate audit in _logs/changes.jsonl', str(len(changes)), failures)

    try:
        assert_not_template_write(TEMPLATES / 'probe-p6.docx')
        check(False, 'template protection', 'did not raise', failures)
    except TemplateProtectionError:
        check(True, 'template protection still on', 'TemplateProtectionError', failures)

    frozen = next(TEMPLATES.rglob('11、项目周报.docx'))
    probe = run([
        sys.executable, str(ENGINE / 'aggregate_engine.py'),
        '--period', 'week', '--project', str(pj),
        '--from', '2026-09-07', '--to', '2026-09-11',
        '--out', str(frozen), '--json',
    ])
    check(probe.returncode == 3, 'refuse write into templates',
          'exit=%s' % probe.returncode, failures)
    return pj


def test_month_from_weeklies(failures: list, week_pj: Path, work: Path) -> None:
    print('\n-- weekly → monthly')
    project = read_project(week_pj, apply_migration=False)
    # plant a second week inside September
    rel = '二、过程分册/11、项目周报/week-2.docx'
    project.setdefault('_documents', {})[rel] = {
        'weekStart': '2026-09-14',
        'logDate': '2026-09-14',
        'weeklyDone': '完成第二轮联调。',
        'weeklyProblem': '培训教室冲突。',
        'weeklyPlan': '准备初验材料。',
    }
    project.setdefault('_docs', {})['D-XMZB-002'] = {
        'itemId': '二-11', 'relPath': rel, 'fillState': 'draft',
    }
    week_pj.write_text(json.dumps(project, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    proc = run([
        sys.executable, str(ENGINE / 'aggregate_engine.py'),
        '--period', 'month', '--project', str(week_pj),
        '--from', '2026-09-01', '--to', '2026-09-30', '--json',
    ])
    payload = last_json(proc.stdout)
    check(proc.returncode == 0 and payload.get('ok') is True,
          'aggregate month ok', payload.get('summary'), failures)
    cols = (payload.get('stats') or {}).get('columns') or {}
    done = cols.get('monthlyDone') or ''
    check('机房桥架' in done or '完成机房' in done or '系统联调' in done,
          'monthlyDone from weeklyDone', done[:160], failures)
    check(FABRICATED not in done, 'monthly no fabricated fact', done[:80], failures)
    check(all(k in cols for k in ('monthlyDone', 'monthlyUndone', 'monthlyProblem', 'monthlyPlan')),
          'monthly four columns', ','.join(cols), failures)


def test_extract_confirm_apply(failures: list, pj: Path) -> None:
    print('\n-- smart-fill extract → confirm → apply')
    text = extract_sample_text()
    cands = extract_candidates(text, DICT, limit=10)
    check(len(cands) >= 10, 'extract ~10 candidates', str(len(cands)), failures)
    check(all(c.get('source') == 'rules' for c in cands),
          'candidates tagged rules (not fake model)',
          str(sorted({c.get('source') for c in cands})), failures)
    keys = [c['key'] for c in cands]
    check('projectName' in keys and 'ownerUnit' in keys and 'contractNo' in keys,
          'core fields present', ','.join(keys[:10]), failures)

    payload_path = pj.parent / 'confirmed.json'
    payload_path.write_text(json.dumps({'confirmed': cands[:10]}, ensure_ascii=False), encoding='utf-8')
    proc = run([
        sys.executable, str(ENGINE / 'ai_engine.py'),
        '--action', 'apply', '--project', str(pj),
        '--payload', str(payload_path), '--json',
    ])
    payload = last_json(proc.stdout)
    check(proc.returncode == 0 and payload.get('ok') is True,
          'apply confirmed candidates', payload.get('summary'), failures)
    project = read_project(pj, apply_migration=False)
    check(project.get('projectName') == '洞庭湖数字财政升级工程',
          'write-back projectName', str(project.get('projectName')), failures)
    check(project.get('contractNo') == 'YY-P6-2026',
          'write-back contractNo', str(project.get('contractNo')), failures)
    ai_logs = read_jsonl(pj.parent / '_logs' / 'ai.jsonl')
    check(any(r.get('op') == 'ai.apply' for r in ai_logs),
          'AI apply trail in _logs/ai.jsonl', str(len(ai_logs)), failures)
    # unconfirmed extract must not write
    before = project.get('chiefSupervisor')
    proc2 = run([
        sys.executable, str(ENGINE / 'ai_engine.py'),
        '--action', 'apply', '--project', str(pj),
        '--payload', json.dumps({'confirmed': []}), '--json',
    ])
    p2 = last_json(proc2.stdout)
    check(p2.get('ok') is False, 'refuse apply without confirm', p2.get('summary'), failures)
    after = read_project(pj, apply_migration=False)
    check(after.get('chiefSupervisor') == before,
          'no silent write on empty confirm', str(after.get('chiefSupervisor')), failures)


def test_offline_gate(failures: list, pj: Path) -> None:
    print('\n-- offline AI gate (no live model)')
    env_off = {
        'YANSHOU_AI_OFFLINE': '1',
        'DEEPSEEK_API_KEY': '',
    }
    # status via engine
    proc = run([sys.executable, str(ENGINE / 'ai_engine.py'), '--action', 'status', '--json'],
               env=env_off)
    st = last_json(proc.stdout).get('stats') or {}
    check(st.get('available') is False, 'status unavailable when offline',
          '%s / %s' % (st.get('available'), st.get('reason')), failures)
    check(st.get('liveModel') is False, 'status does not claim live model',
          str(st.get('liveModel')), failures)

    proc = run([
        sys.executable, str(ENGINE / 'ai_engine.py'),
        '--action', 'polish', '--text', '完成设备安装。', '--json',
        '--project', str(pj),
    ], env=env_off)
    payload = last_json(proc.stdout)
    check(payload.get('ok') is False, 'polish refuses offline',
          payload.get('summary'), failures)
    text = payload.get('text') or ''
    items = payload.get('items') or []
    check(not text and not items,
          'no fabricated polish text', repr(text)[:80], failures)

    proc = run([
        sys.executable, str(ENGINE / 'ai_engine.py'),
        '--action', 'qa', '--project', str(pj), '--json',
    ], env=env_off)
    qa = last_json(proc.stdout)
    check(qa.get('ok') is False, 'qa refuses offline', qa.get('summary'), failures)
    check(not qa.get('narration'), 'qa does not fake a model answer',
          repr(qa.get('narration'))[:60], failures)

    # in-process gate
    old = os.environ.get('DEEPSEEK_API_KEY')
    os.environ.pop('DEEPSEEK_API_KEY', None)
    os.environ['YANSHOU_AI_OFFLINE'] = '1'
    try:
        g = ai_status(probe_network=False)
        check(g.get('available') is False and g.get('reason') in ('offline-flag', 'no-api-key'),
              'ai_status closed', '%s %s' % (g.get('available'), g.get('reason')), failures)
    finally:
        os.environ.pop('YANSHOU_AI_OFFLINE', None)
        if old:
            os.environ['DEEPSEEK_API_KEY'] = old

    # non-AI still works: shell open
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'open',
        '--project', str(pj), '--json',
    ], env=env_off)
    opened = last_json(proc.stdout)
    check(opened.get('ok') is True, 'open project while AI offline',
          opened.get('summary'), failures)
    ai = ((opened.get('stats') or {}).get('ai') or {})
    check(ai.get('available') is False, 'open payload.ai.available=false',
          str(ai), failures)

    html = (REPO / 'src' / 'renderer' / 'index.html').read_text(encoding='utf-8')
    check('ai-only' in html and 'data-act="ai-draft"' in html,
          'AI entries exist in E1 shell', 'ai-only class', failures)
    js = (REPO / 'src' / 'renderer' / 'app.js').read_text(encoding='utf-8')
    check('applyAiGate' in js and 'el.disabled = !on' in js,
          'renderer grays AI when gate closed', 'applyAiGate', failures)
    check('data-act="weekly"' in html, 'weekly (non-AI T7) in ribbon', 'weekly', failures)

    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if not key:
        print('  [SKIP] live model — DEEPSEEK_API_KEY not set on this VM')
    else:
        print('  [INFO] DEEPSEEK_API_KEY present; not asserting a live completion in this suite')


def test_shell_extract(failures: list) -> None:
    print('\n-- shell_bridge extract')
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'ai-extract',
        '--text', extract_sample_text(), '--json',
    ])
    payload = last_json(proc.stdout)
    items = payload.get('items') or []
    check(len(items) >= 10, 'shell extract ≥10', str(len(items)), failures)
    check(all(i.get('source') == 'rules' for i in items),
          'shell extract source=rules', str({i.get('source') for i in items}), failures)


def test_dsh_tools_present(failures: list) -> None:
    print('\n-- dsh tool wiring')
    src = (REPO / 'packages' / 'dsh-yanshou-docs' / 'src' / 'tools.ts').read_text(encoding='utf-8')
    for name in ('yanshou_aggregate', 'yanshou_extract', 'yanshou_rewrite', 'yanshou_qa'):
        check(name in src, 'tools.ts has %s' % name, 'present', failures)
    check('ai_engine.py' in src, 'rewrite/extract spawn ai_engine', 'ai_engine.py', failures)
    secrets = (REPO / 'packages' / 'dsh-yanshou-docs' / 'cordis.patch.yml').read_text(encoding='utf-8')
    check('sk-' not in secrets and 'DEEPSEEK_API_KEY' not in secrets.replace('DEEPSEEK_API_KEY', ''),
          'no secret in patch', 'ok', failures)
    # still never commit a literal key
    check(not re.search(r'sk-[A-Za-z0-9]{8,}', src),
          'no api key in tools.ts', 'ok', failures)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-prior', action='store_true')
    a = ap.parse_args()
    failures: list = []
    print('P6 regression')
    print('=' * 68)

    work = WORK / 'p6-regression'
    work.mkdir(parents=True, exist_ok=True)

    test_date_window(failures)
    test_empty_window(failures)
    week_pj = test_five_logs_weekly(failures, work)
    test_month_from_weeklies(failures, week_pj, work)
    test_extract_confirm_apply(failures, week_pj)
    test_offline_gate(failures, week_pj)
    test_shell_extract(failures)
    test_dsh_tools_present(failures)

    if not a.skip_prior:
        print('\n-- prior P0–P5')
        for script in ('run_regression.py', 'run_p1_regression.py',
                       'run_p2_regression.py', 'run_p3_smoke.py',
                       'run_p5_regression.py'):
            extra = ['--skip-prior'] if script in ('run_p5_regression.py',) else []
            # p5 --skip-prior still runs P5 itself; we want P5 body.
            cmd = [sys.executable, str(TOOLS / script), *extra]
            if script == 'run_p5_regression.py':
                cmd = [sys.executable, str(TOOLS / script), '--skip-prior']
            proc = run(cmd, timeout=600)
            print(proc.stdout[-1500:] if proc.stdout else '')
            if proc.stderr:
                print(proc.stderr[-400:])
            check(proc.returncode == 0, script, 'exit %s' % proc.returncode, failures)

    print()
    print('=' * 68)
    if failures:
        print('FAIL %d' % len(failures))
        for f in failures:
            print('  -', f)
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
