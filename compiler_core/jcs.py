"""RFC 8785 JCS 序列化（juris-calculus W1b 独立实现）。

与 LegalOS W1a 冻结的 TS/Python JCS 行为逐字节一致，oracle 为
tests/fixtures/golden/jcs-vectors.json（与 LegalOS src/contracts/golden 同一冻结内容）。

规则：键按 UTF-16 code unit 升序；字符串双引号/反斜杠/U+0000-1F 转义（\\uXXXX 小写）；
数字用 ES Number::toString（-0->0、指数无 + 号/前导零）；顶层必须 dict/list；
拒绝 NaN/Infinity/循环引用。
"""

from __future__ import annotations

import math
import re
from hashlib import sha256
from typing import Any


def _utf16_sort_key(s: str) -> bytes:
    return s.encode("utf-16-be")


def _escape_string(s: str) -> str:
    out = ['"']
    for ch in s:
        code = ord(ch)
        if code == 0x22:
            out.append('\\"')
        elif code == 0x5C:
            out.append("\\\\")
        elif code < 0x20:
            out.append("\\u%04x" % code)
        else:
            out.append(ch)
    return "".join(out) + '"'


def _shortest_digits(n: float) -> tuple[str, int]:
    r = repr(n)
    if "e" in r or "E" in r:
        mant, exp = r.split("e") if "e" in r else r.split("E")
        exp = int(exp)
        if "." in mant:
            intp, frac = mant.split(".")
            digits = intp + frac
        else:
            digits = mant
        decimal_exp = exp + 1
    else:
        if "." in r:
            intp, frac = r.split(".")
            digits = intp + frac
            decimal_exp = len(intp)
        else:
            digits = r
            decimal_exp = len(r)
    lead = len(digits) - len(digits.lstrip("0"))
    if lead:
        digits = digits.lstrip("0")
        decimal_exp -= lead
    return digits, decimal_exp


def _es_format(digits: str, e: int) -> str:
    k = len(digits)
    if k <= e <= 21:
        return digits + "0" * (e - k)
    if 0 < e <= 21:
        return digits[:e] + "." + digits[e:]
    if -6 < e <= 0:
        return "0." + "0" * (-e) + digits
    mant = digits[0] if k == 1 else digits[0] + "." + digits[1:]
    return mant + "e" + str(e - 1)


def _serialize_number(n: float) -> str:
    if n != n or n in (math.inf, -math.inf):
        raise ValueError("JCS: NaN/Infinity is not a valid JSON number")
    if n == 0:
        return "0"
    if n < 0:
        return "-" + _serialize_number(-n)
    digits, e = _shortest_digits(n)
    return _es_format(digits, e)


def _serialize(value: Any, seen: set[int]) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _escape_string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _serialize_number(value)
    if isinstance(value, list):
        oid = id(value)
        if oid in seen:
            raise ValueError("JCS: circular reference")
        seen.add(oid)
        parts = [_serialize(v, seen) for v in value]
        seen.remove(oid)
        return "[" + ",".join(parts) + "]"
    if isinstance(value, dict):
        oid = id(value)
        if oid in seen:
            raise ValueError("JCS: circular reference")
        seen.add(oid)
        parts = []
        for k in sorted(value.keys(), key=_utf16_sort_key):
            parts.append(_escape_string(k) + ":" + _serialize(value[k], seen))
        seen.remove(oid)
        return "{" + ",".join(parts) + "}"
    raise ValueError("JCS: unsupported value type: %s" % type(value).__name__)


def jcs(input_value: Any) -> str:
    if not isinstance(input_value, (dict, list)):
        raise ValueError("JCS: top-level value must be object or array")
    return _serialize(input_value, set())


def jcs_digest(input_value: Any) -> str:
    return "sha256-" + sha256(jcs(input_value).encode("utf-8")).hexdigest()
