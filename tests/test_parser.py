from dataclasses import asdict
import json

import pytest

from bamboo import BambooError, parse, from_dict


def test_parse_metadata_notes_emphasis_indent_and_break():
    b = parse(
        "@title 竹簡\n@volume 卷二\n@preset red-ruled\n\n# 題名\n\n　　甲[[注]]{{乙}}\n\n---\n丙"
    )
    assert b.title == "竹簡" and b.volume == "卷二"
    assert b.blocks[1].indent == 2
    assert [i.kind for i in b.blocks[1].inlines] == ["text", "note", "emphasis"]
    assert b.blocks[2].kind == "pagebreak"


def test_source_json_round_trip():
    b = parse("@title 測試\n甲[[乙]]{{丙}}")
    assert from_dict(json.loads(json.dumps(asdict(b)))) == b


def test_escape_and_multiline_source():
    b = parse("@title 測試\n甲\\[\\[乙\\]\\]\n丙")
    assert b.blocks[0].text == "甲[[乙]]丙"


@pytest.mark.parametrize(
    "source",
    [
        "",
        "---",
        "甲[[乙",
        "甲{{}}",
        "甲]]",
        "甲[[乙{{丙}}]]",
        "甲\n@title 乙",
        "@preset missing\n甲",
        "@title 甲\n@title 乙\n丙",
    ],
)
def test_invalid_markup(source):
    with pytest.raises(BambooError):
        parse(source)


@pytest.mark.parametrize(
    "change",
    [
        {"profile": {"column": 4}},
        {"schema_version": 2},
        {"schema_version": True},
        {"blocks": "甲"},
        {"blocks": [{"text": "甲", "inlines": []}]},
        {"blocks": [{"kind": "pagebreak", "text": "甲"}]},
        {"blocks": [{"text": "甲", "indent": 22}]},
        {"blocks": [{"kind": [], "text": "甲"}]},
        {"title": 3},
        {"preset": []},
    ],
)
def test_invalid_json(change):
    data = {"title": "測試", "blocks": [{"text": "甲"}], **change}
    with pytest.raises(BambooError):
        from_dict(data)
