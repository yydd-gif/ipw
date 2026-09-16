# -*- coding: utf-8 -*-
"""Minimal YAML 1.1 subset loader (stdlib only).

Enough for `assets/spec/填数规则.yaml`: block maps/lists, flow []/{} ,
quoted scalars, comments, ints/floats/bools/null. Not a full YAML 1.2 engine.
"""
from __future__ import annotations

from typing import Any, List, Tuple


class YamlLiteError(ValueError):
    """Raised when the constrained YAML subset cannot be parsed."""


def load_yaml(text: str) -> Any:
    if text is None:
        raise YamlLiteError('YAML text is None')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if text.startswith('\ufeff'):
        text = text[1:]
    lines = _preprocess(text.split('\n'))
    if not lines:
        return None
    value, nxt = _parse_block(lines, 0, -1)
    if nxt < len(lines):
        raise YamlLiteError('trailing content at line %d' % (lines[nxt][0] + 1))
    return value


def load_yaml_file(path) -> Any:
    from pathlib import Path
    return load_yaml(Path(path).read_text(encoding='utf-8'))


# ---------------------------------------------------------------- preprocess

def _preprocess(raw: List[str]) -> List[Tuple[int, int, str]]:
    """Return (lineno, indent, content) skipping blanks and full-line comments."""
    out = []
    for i, line in enumerate(raw):
        stripped = _strip_comment(line)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(' '))
        if '\t' in stripped[:indent + 1] and stripped[:indent].find('\t') >= 0:
            raise YamlLiteError('tabs not allowed for indent (line %d)' % (i + 1))
        content = stripped[indent:]
        if not content:
            continue
        out.append((i, indent, content))
    return out


def _strip_comment(line: str) -> str:
    out = []
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == '\\' and quote == '"' and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == '#':
            break
        out.append(ch)
        i += 1
    return ''.join(out).rstrip()


# ---------------------------------------------------------------- block

def _parse_block(lines, idx, parent_indent):
    if idx >= len(lines):
        return None, idx
    lineno, indent, content = lines[idx]
    if indent <= parent_indent:
        raise YamlLiteError('unexpected dedent at line %d' % (lineno + 1))
    if content.startswith('- ') or content == '-':
        return _parse_list(lines, idx, indent)
    return _parse_map(lines, idx, indent)


def _parse_map(lines, idx, indent):
    result = {}
    while idx < len(lines):
        lineno, ind, content = lines[idx]
        if ind < indent:
            break
        if ind > indent:
            raise YamlLiteError('bad indent at line %d' % (lineno + 1))
        if content.startswith('- ') or content == '-':
            raise YamlLiteError('sequence item in mapping at line %d' % (lineno + 1))
        key, rest, _has_value = _split_key(content, lineno)
        if key in result:
            raise YamlLiteError('duplicate key %r at line %d' % (key, lineno + 1))
        if rest == '':
            if idx + 1 < len(lines) and lines[idx + 1][1] > indent:
                value, idx = _parse_block(lines, idx + 1, indent)
            else:
                value = None
                idx += 1
        else:
            value = _parse_flow_or_scalar(rest, lineno)
            idx += 1
        result[key] = value
    return result, idx


def _parse_list(lines, idx, indent):
    result = []
    while idx < len(lines):
        lineno, ind, content = lines[idx]
        if ind < indent:
            break
        if ind > indent:
            raise YamlLiteError('bad indent at line %d' % (lineno + 1))
        if not (content.startswith('- ') or content == '-'):
            break
        body = content[1:].lstrip()
        if body == '':
            if idx + 1 < len(lines) and lines[idx + 1][1] > indent:
                value, idx = _parse_block(lines, idx + 1, indent)
            else:
                value = None
                idx += 1
            result.append(value)
            continue
        if _looks_like_key(body):
            key, rest, _ = _split_key(body, lineno)
            item = {}
            if rest == '':
                if idx + 1 < len(lines) and lines[idx + 1][1] > indent:
                    nested, idx = _parse_block(lines, idx + 1, indent)
                    item[key] = nested
                else:
                    item[key] = None
                    idx += 1
            else:
                item[key] = _parse_flow_or_scalar(rest, lineno)
                idx += 1
            while idx < len(lines) and lines[idx][1] > indent:
                more, idx = _parse_map(lines, idx, lines[idx][1])
                overlap = set(item) & set(more)
                if overlap:
                    raise YamlLiteError(
                        'duplicate key %r at line %d' % (sorted(overlap)[0], lineno + 1))
                item.update(more)
            result.append(item)
            continue
        result.append(_parse_flow_or_scalar(body, lineno))
        idx += 1
    return result, idx


def _looks_like_key(body: str) -> bool:
    if body.startswith('{') or body.startswith('['):
        return False
    if body.startswith('"') or body.startswith("'"):
        try:
            _key, rest, i = _read_quoted(body, 0)
            rest = body[i:].lstrip()
            return rest.startswith(':')
        except YamlLiteError:
            return False
    if body.startswith('http://') or body.startswith('https://'):
        return False
    return ': ' in body or body.endswith(':')


def _split_key(content: str, lineno: int):
    if content.startswith('"') or content.startswith("'"):
        key, _consumed, i = _read_quoted(content, 0)
        rest = content[i:].lstrip()
        if not rest.startswith(':'):
            raise YamlLiteError('expected : after quoted key at line %d' % (lineno + 1))
        rest = rest[1:]
        if rest.startswith(' '):
            rest = rest[1:]
        return key, rest, True
    if ': ' in content:
        key, rest = content.split(': ', 1)
        return key.strip(), rest, True
    if content.endswith(':'):
        return content[:-1].strip(), '', True
    raise YamlLiteError('cannot parse key at line %d: %r' % (lineno + 1, content[:60]))


# ---------------------------------------------------------------- flow / scalar (index based)

class _Scan:
    def __init__(self, text: str, lineno: int = 0):
        self.text = text
        self.i = 0
        self.lineno = lineno

    def skip_ws(self) -> None:
        t, i = self.text, self.i
        n = len(t)
        while i < n and t[i] in ' \t\n':
            i += 1
        self.i = i

    def peek(self) -> str:
        return self.text[self.i] if self.i < len(self.text) else ''

    def error(self, msg: str) -> YamlLiteError:
        where = 'line %d' % (self.lineno + 1) if self.lineno else 'flow'
        return YamlLiteError('%s (%s at col %d)' % (msg, where, self.i + 1))


def _parse_flow_or_scalar(text: str, lineno: int):
    sc = _Scan(text.strip(), lineno)
    value = _parse_value(sc)
    sc.skip_ws()
    if sc.i < len(sc.text):
        raise sc.error('unexpected trailing %r' % sc.text[sc.i:sc.i + 40])
    return value


def _parse_value(sc: _Scan):
    sc.skip_ws()
    ch = sc.peek()
    if ch == '':
        return None
    if ch == '{':
        return _parse_flow_map(sc)
    if ch == '[':
        return _parse_flow_list(sc)
    if ch in ('"', "'"):
        val, _consumed, i = _read_quoted(sc.text, sc.i)
        sc.i = i
        return val
    return _parse_plain(sc)


def _parse_flow_map(sc: _Scan) -> dict:
    assert sc.peek() == '{'
    sc.i += 1
    result = {}
    sc.skip_ws()
    if sc.peek() == '}':
        sc.i += 1
        return result
    while True:
        sc.skip_ws()
        key = _parse_flow_key(sc)
        sc.skip_ws()
        if sc.peek() != ':':
            raise sc.error('expected : after key %r' % key)
        sc.i += 1
        val = _parse_value(sc)
        if key in result:
            raise sc.error('duplicate flow key %r' % key)
        result[key] = val
        sc.skip_ws()
        ch = sc.peek()
        if ch == ',':
            sc.i += 1
            sc.skip_ws()
            if sc.peek() == '}':
                sc.i += 1
                return result
            continue
        if ch == '}':
            sc.i += 1
            return result
        raise sc.error('expected , or } in flow mapping')


def _parse_flow_key(sc: _Scan) -> str:
    sc.skip_ws()
    ch = sc.peek()
    if ch in ('"', "'"):
        key, _consumed, i = _read_quoted(sc.text, sc.i)
        sc.i = i
        return key
    start = sc.i
    t = sc.text
    while sc.i < len(t) and t[sc.i] not in ':,{}[] \t\n':
        sc.i += 1
    # allow dots / $ in unquoted keys until space
    # actually we stopped at space; include internal $ . which are not in the stop set
    key = t[start:sc.i].strip()
    if not key:
        raise sc.error('empty key in flow mapping')
    return key


def _parse_flow_list(sc: _Scan) -> list:
    assert sc.peek() == '['
    sc.i += 1
    result = []
    sc.skip_ws()
    if sc.peek() == ']':
        sc.i += 1
        return result
    while True:
        val = _parse_value(sc)
        result.append(val)
        sc.skip_ws()
        ch = sc.peek()
        if ch == ',':
            sc.i += 1
            sc.skip_ws()
            if sc.peek() == ']':
                sc.i += 1
                return result
            continue
        if ch == ']':
            sc.i += 1
            return result
        raise sc.error('expected , or ] in flow sequence')


def _parse_plain(sc: _Scan):
    start = sc.i
    t = sc.text
    depth_brace = depth_brack = 0
    while sc.i < len(t):
        ch = t[sc.i]
        if ch == '{':
            depth_brace += 1
        elif ch == '}':
            if depth_brace == 0:
                break
            depth_brace -= 1
        elif ch == '[':
            depth_brack += 1
        elif ch == ']':
            if depth_brack == 0:
                break
            depth_brack -= 1
        elif ch == ',' and depth_brace == 0 and depth_brack == 0:
            break
        elif ch == '#' and depth_brace == 0 and depth_brack == 0:
            break
        sc.i += 1
    raw = t[start:sc.i].rstrip()
    return _parse_scalar(raw)


def _read_quoted(text: str, i: int):
    quote = text[i]
    i += 1
    out = []
    while i < len(text):
        ch = text[i]
        if quote == '"' and ch == '\\' and i + 1 < len(text):
            nxt = text[i + 1]
            escapes = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', "'": "'"}
            out.append(escapes.get(nxt, nxt))
            i += 2
            continue
        if ch == quote:
            return ''.join(out), True, i + 1
        out.append(ch)
        i += 1
    raise YamlLiteError('unterminated quoted string')


def _parse_scalar(raw: str):
    if raw == '' or raw in ('~', 'null', 'Null', 'NULL'):
        return None
    if raw in ('true', 'True', 'TRUE', 'yes', 'Yes', 'YES'):
        return True
    if raw in ('false', 'False', 'FALSE', 'no', 'No', 'NO'):
        return False
    if len(raw) >= 2 and raw[0] in ('"', "'") and raw[-1] == raw[0]:
        inner, _ok, end = _read_quoted(raw, 0)
        if end == len(raw):
            return inner
    if raw.isdigit() or (raw.startswith('-') and raw[1:].isdigit()):
        try:
            return int(raw)
        except ValueError:
            pass
    try:
        if raw.count('.') == 1 and any(c.isdigit() for c in raw):
            return float(raw)
    except ValueError:
        pass
    return raw
