"""Typed, editable collections. Money is stored as decimal text, never float."""

from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from datetime import date
import re
from .model import BambooError


def text(value, name, limit=200, empty=True):
    if (
        not isinstance(value, str)
        or len(value) > limit
        or any(ord(c) < 32 and c != "\n" for c in value)
        or (not empty and not value.strip())
    ):
        raise BambooError(
            f"{name}需要{1 if not empty else 0}～{limit}个字，不可包含控制字符"
        )
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise BambooError("记录标识无效")


def money(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{1,12}(?:\.\d{1,2})?", value.strip()
    ):
        raise BambooError("礼金请输入非负金额，最多两位小数和十二位整数")
    return Decimal(value).quantize(Decimal(".01"))


def money_upper(value):
    amount = money(value)
    cents = int(amount * 100)
    integer, fraction = divmod(cents, 100)
    digits = "零壹贰叁肆伍陆柒捌玖"

    def group(n):
        result = ""
        zero = False
        for place, unit in [(1000, "仟"), (100, "佰"), (10, "拾"), (1, "")]:
            d, n = divmod(n, place)
            if d:
                if zero:
                    result += "零"
                result += digits[d] + unit
                zero = False
            elif result and n:
                zero = True
        return result

    parts = []
    remaining = integer
    while remaining:
        parts.append(remaining % 10000)
        remaining //= 10000
    result = ""
    gap = False
    for i in range(len(parts) - 1, -1, -1):
        n = parts[i]
        if not n:
            if result:
                gap = True
            continue
        if result and (gap or n < 1000):
            result += "零"
        result += group(n) + ["", "万", "亿"][i]
        gap = False
    result = (result or "零") + "元"
    jiao, fen = divmod(fraction, 10)
    if not fraction:
        return result + "整"
    if jiao:
        result += digits[jiao] + "角"
    elif fen:
        result += "零"
    if fen:
        result += digits[fen] + "分"
    return result


@dataclass(frozen=True)
class GiftRecord:
    id: str
    name: str
    amount: str = "0.00"
    gift: str = ""
    date: str = ""
    note: str = ""

    def __post_init__(self):
        identifier(self.id)
        text(self.name, "姓名", 40, False)
        object.__setattr__(self, "amount", format(money(self.amount), ".2f"))
        text(self.gift, "礼品", 120)
        text(self.note, "备注", 300)
        text(self.date, "日期", 10)
        if self.date:
            try:
                date.fromisoformat(self.date)
            except ValueError as e:
                raise BambooError("日期需要为有效的年-月-日") from e


@dataclass(frozen=True)
class GiftLedger:
    records: tuple = ()
    occasion: str = ""
    date: str = ""
    per_page: int = 6
    kind: str = "gift"

    def __post_init__(self):
        if self.kind != "gift":
            raise BambooError("无效礼簿类型")
        text(self.occasion, "事由", 80)
        text(self.date, "日期", 30)
        validate_records(self.records, GiftRecord)
        object.__setattr__(self, "records", tuple(self.records))
        if type(self.per_page) is not int or not 1 <= self.per_page <= 20:
            raise BambooError("每页最多记录数应为1～20")
        if sum((money(r.amount) for r in self.records), Decimal(0)) >= Decimal(
            "1000000000000"
        ):
            raise BambooError("礼金总额超出十二位整数范围")


def validate_records(records, cls):
    if (
        not isinstance(records, (tuple, list))
        or len(records) > 10000
        or any(not isinstance(r, cls) for r in records)
    ):
        raise BambooError("无效记录列表，最多10000条")
    ids = [r.id for r in records]
    if len(ids) != len(set(ids)):
        raise BambooError("记录标识不可重复")


def from_dict(data):
    if not isinstance(data, dict):
        raise BambooError("专用文档需要为对象")
    types = {"gift": (GiftLedger, GiftRecord)}
    if data.get("kind") not in types:
        raise BambooError("未知专用文档类型")
    cls, record_cls = types[data["kind"]]
    if set(data) - {f.name for f in fields(cls)}:
        raise BambooError("专用文档含未知字段")
    records = data.get("records", [])
    if not isinstance(records, list):
        raise BambooError("记录需要为数组")
    try:
        parsed = [record_cls(**r) for r in records]
        return cls(**{**data, "records": tuple(parsed)})
    except TypeError as e:
        raise BambooError(f"无效记录字段：{e}") from e


def validate(value):
    if value is not None and not isinstance(value, GiftLedger):
        raise BambooError("无效专用文档")


def summary(document):
    if isinstance(document, GiftLedger):
        total = sum((money(r.amount) for r in document.records), Decimal(0))
        return {
            "kind": "gift",
            "count": len(document.records),
            "total": format(total, ".2f"),
            "uppercase": money_upper(format(total, ".2f")),
        }
    return {}
