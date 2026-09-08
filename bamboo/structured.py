"""Typed, editable collections. Money is stored as decimal text, never float."""

from dataclasses import dataclass, fields, replace
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
    types = {"gift": (GiftLedger, GiftRecord), "genealogy": (Genealogy, FamilyPerson)}
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
    if value is not None and not isinstance(value, (GiftLedger, Genealogy)):
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
    if isinstance(document, Genealogy):
        return {
            "kind": "genealogy",
            "count": len(document.records),
            "generations": max(
                family_generations(document.records).values(), default=0
            ),
        }
    return {}


@dataclass(frozen=True)
class FamilyPerson:
    id: str
    name: str
    parents: tuple = ()
    spouses: tuple = ()
    birth: str = ""
    death: str = ""
    biography: str = ""

    def __post_init__(self):
        identifier(self.id)
        text(self.name, "姓名", 40, False)
        for key in ["parents", "spouses"]:
            values = getattr(self, key)
            if (
                not isinstance(values, (tuple, list))
                or any(not isinstance(v, str) for v in values)
                or len(values) != len(set(values))
            ):
                raise BambooError("亲属关系不可重复")
            for value in values:
                identifier(value)
            if self.id in values:
                raise BambooError("人物不能与自己建立亲属关系")
            object.__setattr__(self, key, tuple(values))
        if len(self.parents) > 2:
            raise BambooError("每个人物最多指定两位父母")
        text(self.birth, "生年", 40)
        text(self.death, "卒年", 40)
        text(self.biography, "传记", 2000)


@dataclass(frozen=True)
class Genealogy:
    records: tuple = ()
    occasion: str = ""
    date: str = ""
    per_page: int = 8
    kind: str = "genealogy"

    def __post_init__(self):
        if self.kind != "genealogy":
            raise BambooError("无效族谱类型")
        validate_records(self.records, FamilyPerson)
        object.__setattr__(self, "records", tuple(self.records))
        text(self.occasion, "堂号", 80)
        text(self.date, "修谱日期", 30)
        if type(self.per_page) is not int or not 1 <= self.per_page <= 12:
            raise BambooError("每张世系图容纳1～12个人物")
        family_generations(self.records)
        partners = {r.id: set(r.spouses) for r in self.records}
        order = {r.id: i for i, r in enumerate(self.records)}
        for r in self.records:
            for spouse in r.spouses:
                partners[spouse].add(r.id)
        object.__setattr__(
            self,
            "records",
            tuple(
                replace(
                    r, spouses=tuple(sorted(partners[r.id], key=lambda i: order[i]))
                )
                for r in self.records
            ),
        )


def family_generations(records):
    """Spouses share a generation; collapse couples, then topologically rank parents."""
    ids = {r.id for r in records}
    representatives = {i: i for i in ids}

    def root(i):
        while representatives[i] != i:
            representatives[i] = representatives[representatives[i]]
            i = representatives[i]
        return i

    for r in records:
        if not set(r.parents + r.spouses) <= ids:
            raise BambooError(f"{r.name}的亲属尚未录入")
        for spouse in r.spouses:
            representatives[root(spouse)] = root(r.id)
    edges = {root(i): set() for i in ids}
    indegree = {i: 0 for i in edges}
    for r in records:
        for parent in r.parents:
            a, b = root(parent), root(r.id)
            if a == b:
                raise BambooError("父母与子女不能处于同一配偶关系组")
            if b not in edges[a]:
                edges[a].add(b)
                indegree[b] += 1
    ready = sorted(i for i, d in indegree.items() if d == 0)
    level = {i: 1 for i in ready}
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for child in edges[current]:
            level[child] = max(level.get(child, 1), level[current] + 1)
            indegree[child] -= 1
            if not indegree[child]:
                ready.append(child)
    if visited != len(edges):
        raise BambooError("亲子关系形成循环，请检查世代关系")
    return {i: level[root(i)] for i in ids}
