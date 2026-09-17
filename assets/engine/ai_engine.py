#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 AI engine CLI · draft/polish/expand / extract / apply / qa / status.

Live model replies are never invented. No key / offline → ok=false, reason set.
Extract uses the deterministic alias engine (source=rules) so the confirmation
panel can be tested without DEEPSEEK_API_KEY. Apply still requires an explicit
confirmed[] list — nothing is written back otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows embeddable CPython (python._pth) omits the script dir from sys.path.
_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent.parent, _HERE):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from _common import (
    BASE, DICT_PATH,
    TemplateProtectionError, assert_not_template_write,
    emit_progress, emit_result, exit_env, exit_param, result_payload,
)

REPO = BASE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.ai_client import AiCallError, rewrite  # noqa: E402
from lib.ai_extract import extract_candidates  # noqa: E402
from lib.ai_gate import AiUnavailable, ai_status, require_ai  # noqa: E402
from lib.audit_log import log_change  # noqa: E402
from lib.field_dict import FieldDictError, load_field_dict  # noqa: E402
from lib.project_store import ProjectStoreError, read_project, write_project  # noqa: E402

ENGINE = BASE / 'engine'


def _root(project_path: Path) -> Path:
    p = Path(project_path)
    return p.parent if p.name == 'project.json' else p


def _project_file(path: Path | None) -> Path | None:
    if path is None:
        return None
    p = Path(path)
    if p.is_dir():
        return p / 'project.json'
    return p


def _load_json_arg(raw: str) -> dict | list:
    if not raw:
        return {}
    p = Path(raw)
    if p.is_file():
        return json.loads(p.read_text(encoding='utf-8'))
    return json.loads(raw)


def _run_verify(project_file: Path) -> dict:
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(ENGINE / 'verify_engine.py'),
         '--dir', str(_root(project_file)),
         '--project', str(project_file), '--json'],
        cwd=str(REPO), capture_output=True, text=True, encoding='utf-8',
        timeout=180,
    )
    last = ''
    for line in (proc.stdout or '').splitlines():
        if line.strip().startswith('{'):
            last = line.strip()
    payload = json.loads(last) if last else {
        'ok': proc.returncode == 0, 'summary': (proc.stderr or proc.stdout or '')[-400],
    }
    payload['_exit'] = proc.returncode
    return payload


def action_status() -> dict:
    st = ai_status()
    return result_payload(
        True, 'ai', 'AI %s（%s）' % (
            '可用' if st.get('available') else '不可用', st.get('reason')),
        stats=st,
    )


def action_extract(text: str) -> dict:
    fd = load_field_dict(DICT_PATH)
    cands = extract_candidates(text, fd, limit=10)
    return result_payload(
        True, 'ai', '抽取 %d 个字段候选（source=rules，待确认）' % len(cands),
        stats={'count': len(cands), 'source': 'rules', 'liveModel': False},
        items=cands,
    )


def action_rewrite(mode: str, text: str, context: dict, project_file: Path | None) -> dict:
    st = require_ai()
    ctx = dict(context or {})
    if project_file and project_file.exists():
        project = read_project(project_file, apply_migration=False)
        for k in ('projectName', 'ownerUnit', 'constructionUnit', 'buildSite'):
            if project.get(k) and k not in ctx:
                ctx[k] = project[k]
    emit_progress(0, 1, 'model %s' % mode)
    result = rewrite(text, mode, ctx)
    if project_file:
        log_change(
            _root(project_file),
            op='ai.%s' % mode,
            channel='ai',
            source='model',
            model=result.get('model'),
            live=True,
            charsIn=len(text or ''),
            charsOut=len(result.get('text') or ''),
        )
    payload = result_payload(
        True, 'ai', '%s 完成（live model）' % mode,
        stats={'mode': mode, 'liveModel': True, 'model': result.get('model'),
               'source': 'model'},
        items=[{'text': result.get('text') or '', 'mode': mode}],
    )
    payload['text'] = result.get('text') or ''
    payload['usage'] = result.get('usage') or {}
    return payload


def action_apply(project_file: Path, confirmed: list, rel_path: str = '') -> dict:
    if not isinstance(confirmed, list) or not confirmed:
        return result_payload(
            False, 'ai', '没有已确认的字段，拒绝回写',
            errors=[{'reason': 'apply requires confirmed[]', 'level': 'block'}],
        )
    fd = load_field_dict(DICT_PATH)
    enabled = fd.enabled
    project = read_project(project_file, apply_migration=True)
    now_fields = {}
    applied = []
    for item in confirmed:
        if not isinstance(item, dict):
            continue
        key = str(item.get('key') or '')
        if key not in enabled or key == 'docNo':
            continue
        val = item.get('value')
        if val in (None, ''):
            continue
        now_fields[key] = val
        applied.append({'key': key, 'value': val, 'label': item.get('label') or key})
    if not now_fields:
        return result_payload(
            False, 'ai', '确认列表没有可写字段',
            errors=[{'reason': 'no writable keys', 'level': 'block'}],
        )
    sources = project.setdefault('_fieldSources', {})
    if rel_path:
        ov = project.setdefault('_documents', {}).setdefault(rel_path, {})
        ov.update(now_fields)
        target = rel_path
    else:
        project.update(now_fields)
        for k in now_fields:
            sources[k] = {
                'source': 'S5', 'ruleId': 'ai.extract', 'by': 'ai-confirmed',
            }
        target = 'project'
    write_project(project_file, project, backup=True)
    log_change(
        _root(project_file),
        op='ai.apply',
        channel='ai',
        source='rules' if not any(i.get('source') == 'model' for i in confirmed) else 'mixed',
        live=False,
        target=target,
        fields=now_fields,
        count=len(now_fields),
    )
    return result_payload(
        True, 'ai', '已回写 %d 个已确认字段' % len(now_fields),
        stats={'count': len(now_fields), 'target': target, 'liveModel': False},
        items=applied,
    )


def action_qa(project_file: Path) -> dict:
    """Q&A error check. Offline → refuse (UI is grayed). Online: verify engine.

    Findings are tagged source=verify, never as a fake model reply. A live
    narration is only added when the gate is open AND the HTTP call succeeds.
    """
    st = require_ai()
    emit_progress(0, 1, 'verify')
    verified = _run_verify(project_file)
    findings = verified.get('errors') or verified.get('items') or []
    summary = verified.get('summary') or '校验完成'
    narration = ''
    live = False
    model = ''
    try:
        from lib.ai_client import chat
        prompt = (
            '下面是验收资料校验闸门的结果，用中文简要说明还差什么、该补哪些字段。'
            '不要编造结果里没有的问题。\n\n' + json.dumps(verified, ensure_ascii=False)[:4000]
        )
        told = chat([
            {'role': 'system', 'content': '你是验收资料查错助手。只陈述校验结果。'},
            {'role': 'user', 'content': prompt},
        ], max_tokens=600)
        narration = told.get('text') or ''
        live = True
        model = told.get('model') or ''
    except (AiUnavailable, AiCallError):
        narration = ''
        live = False
    log_change(
        _root(project_file),
        op='ai.qa',
        channel='ai',
        source='model' if live else 'verify',
        live=live,
        model=model,
        summary=summary,
        findingCount=len(findings) if isinstance(findings, list) else 0,
    )
    payload = result_payload(
        True, 'ai', summary,
        stats={
            'liveModel': live,
            'source': 'model' if live else 'verify',
            'model': model,
            'verifyOk': bool(verified.get('ok')),
            'verifyExit': verified.get('_exit'),
        },
        items=findings if isinstance(findings, list) else [],
        errors=verified.get('errors') or [],
    )
    payload['narration'] = narration
    payload['verify'] = {
        'ok': verified.get('ok'),
        'summary': summary,
        'stats': verified.get('stats') or {},
    }
    payload['gate'] = {k: st.get(k) for k in ('available', 'reason', 'hasKey')}
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description='ai_engine · P6 AI 入口')
    ap.add_argument('--action', default='status',
                    choices=('status', 'extract', 'draft', 'polish', 'expand',
                             'apply', 'qa'))
    ap.add_argument('--project', type=Path)
    ap.add_argument('--text', default='')
    ap.add_argument('--payload', default='', help='JSON object or path')
    ap.add_argument('--rel-path', dest='rel_path', default='')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    as_json = a.as_json or True
    pj = _project_file(a.project)

    try:
        if a.action == 'status':
            return emit_result(action_status(), True)

        payload_obj = _load_json_arg(a.payload) if a.payload else {}
        if not isinstance(payload_obj, dict):
            payload_obj = {'items': payload_obj}

        if a.action == 'extract':
            text = a.text or str(payload_obj.get('text') or '')
            if not text.strip():
                return exit_param('extract 需要 --text', True, 'ai')
            return emit_result(action_extract(text), True)

        if a.action in ('draft', 'polish', 'expand'):
            text = a.text or str(payload_obj.get('text') or '')
            if not text.strip():
                return exit_param('%s 需要 --text' % a.action, True, 'ai')
            ctx = payload_obj.get('context') if isinstance(payload_obj.get('context'), dict) else {}
            return emit_result(action_rewrite(a.action, text, ctx, pj), True)

        if a.action == 'apply':
            if not pj or not pj.exists():
                return exit_param('apply 需要 --project', True, 'ai')
            confirmed = payload_obj.get('confirmed') or payload_obj.get('items') or []
            if a.payload and isinstance(_load_json_arg(a.payload), list):
                confirmed = _load_json_arg(a.payload)
            return emit_result(action_apply(pj, confirmed, a.rel_path), True)

        if a.action == 'qa':
            if not pj or not pj.exists():
                return exit_param('qa 需要 --project', True, 'ai')
            return emit_result(action_qa(pj), True)

        return exit_param('未知 action', True, 'ai')
    except AiUnavailable as e:
        st = e.status or ai_status()
        payload = result_payload(
            False, 'ai', str(e),
            stats=st,
            errors=[{'reason': e.reason, 'level': 'block'}],
        )
        payload['available'] = False
        return emit_result(payload, True)
    except AiCallError as e:
        payload = result_payload(
            False, 'ai', '模型调用失败（未伪造回复）：%s' % e,
            stats={'liveModel': False, 'source': 'error'},
            errors=[{'reason': str(e), 'level': 'block'}],
        )
        return emit_result(payload, True)
    except (FieldDictError, ProjectStoreError, TemplateProtectionError,
            json.JSONDecodeError, ValueError, OSError) as e:
        return exit_env(str(e), True, 'ai')


if __name__ == '__main__':
    sys.exit(main())
