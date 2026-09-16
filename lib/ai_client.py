# -*- coding: utf-8 -*-
"""DeepSeek chat client. Credentials: DEEPSEEK_API_KEY env only.

Never invents a model reply. If the gate is closed or the HTTP call fails,
the caller gets AiUnavailable / AiCallError — tests must treat that as SKIP,
not as a polished document.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

from lib.ai_gate import AiUnavailable, api_base, api_key, require_ai

DEFAULT_MODEL = 'deepseek-flash'


class AiCallError(RuntimeError):
    """Live HTTP call failed. Not a substitute reply."""


def _model() -> str:
    return os.environ.get('YANSHOU_AI_MODEL') or DEFAULT_MODEL


def chat(messages: List[dict], *, temperature: float = 0.2,
         max_tokens: int = 1200, status: Optional[dict] = None) -> dict:
    """POST /chat/completions. Returns {text, model, usage, live: True}."""
    st = require_ai(status)
    key = api_key()
    if not key:
        raise AiUnavailable('no-api-key', st)
    url = api_base() + '/chat/completions'
    body = {
        'model': _model(),
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        url, data=data, method='POST',
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode('utf-8')
            payload = json.loads(raw)
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')[:400]
        raise AiCallError('HTTP %s: %s' % (e.code, detail)) from e
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise AiCallError('模型调用失败：%s' % e) from e
    choices = payload.get('choices') or []
    text = ''
    if choices:
        msg = (choices[0] or {}).get('message') or {}
        text = msg.get('content') or ''
    return {
        'text': text,
        'model': payload.get('model') or _model(),
        'usage': payload.get('usage') or {},
        'live': True,
        'source': 'model',
    }


REWRITE_SYSTEM = (
    '你是验收资料编辑软件里的文书助手。只根据用户给出的原文与项目上下文改写，'
    '不得编造工程事实、日期、人数、金额或未出现的工作内容。'
    '输出只要改写后的正文，不要解释。'
)


def rewrite(text: str, mode: str, context: Optional[dict] = None) -> dict:
    """draft / polish / expand. Requires a live model."""
    mode = (mode or 'polish').strip().lower()
    if mode not in ('draft', 'polish', 'expand'):
        mode = 'polish'
    verbs = {
        'draft': '根据要点起草一段正式验收资料正文',
        'polish': '润色下面这段文字，保持事实不变',
        'expand': '在不增加新事实的前提下扩写下面这段文字',
    }
    ctx_lines = []
    for k, v in (context or {}).items():
        if v in (None, ''):
            continue
        ctx_lines.append('%s：%s' % (k, v))
    user = verbs[mode] + '。\n'
    if ctx_lines:
        user += '项目上下文（不得改动这些事实）：\n' + '\n'.join(ctx_lines[:20]) + '\n\n'
    user += '原文：\n' + (text or '')
    result = chat([
        {'role': 'system', 'content': REWRITE_SYSTEM},
        {'role': 'user', 'content': user},
    ])
    result['mode'] = mode
    return result
