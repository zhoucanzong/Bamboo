# Bamboo 0.4.0 验证记录

验证日期：2026-09-08。

## 检查范围

完整检查共 146 个用例，包含 7 个真实浏览器测试。新增检查覆盖独立元素开关、24 种方向与样式组合、编号引用重编号、标签边框、Word 域结构及导入回读。原有检查包含 40 组固定种子随机混合文档。新增检查覆盖事务原子性、稳定段落标识、Unicode 删除、锚点移动、撤销重做、选区格式、保存恢复及 Word 实际内容导入。

浏览器检查实际操作纸面输入、连续输入顺序、回车分段、跨段选区、拖选添加短旁注、组合输入只提交一次、撤销重做、刷新恢复、普通文本打开及 PDF/HTML/DOCX 下载。另检查无令牌、跨站和旧版本请求被拒绝。

示例使用本机宋体进行字体覆盖检查和子集化；字体文件不放入源码。当前环境的核心依赖为 Python 3.9、PyMuPDF、python-docx 与 fontTools。

## 导出验收

| 对象 | 检查方式 | 范围 |
| --- | --- | --- |
| PDF | 提取原生文本、检查字体与书签、渲染逐页图像 | 两叶古籍样书；正文、夹注、朱色标记、双鱼尾与版心 |
| HTML | 离线浏览器加载、检查内嵌字体、翻叶缩放与打印 | 固定字位 SVG、原文区、无网络字体依赖 |
| DOCX 竖排流式 | 原生正文、方向、网格、双行夹注，LibreOffice 实际渲染 | 样书与 PDF 均为 2 页，未把正文变成图片 |
| DOCX 横排流式 | 原生横排、双行注与独立课注样式 | 样书与 PDF 均为 2 页 |
| DOCX 朱批样式 | 原生 ruby、长旁批文字框与顶部眉批 | 与 PDF 均为 1 页；验证文字存在及区域位置 |
| DOCX 页下注 | 引用 ID、脚注部件、自动编号与实际渲染 | 原生页下注，随引用在竖排页面内布局 |
| DOCX 可选图片版 | 页面锚点、源文快照和实际渲染 | 保留原有整页图片模式的回归用例 |

## 增删重排验收

在已导出的 Word 文件中插入已有文字段落，不重新运行排版引擎，再由阅读器渲染：横排文档由 2 页自动增至 3 页，竖排朱批文档由 1 页自动增至 7 页。重复段落中的原生 ruby 随文字出现在各页；原有长旁批和眉批迁移到其所在段落的页面。

这证明正文是可重排的文字流，不是按固定页拆开的图片或逐字框。它不证明长批注能逐字更新段内位置或自动跨页续框；这些限制仍会写入导出警告。

当前实际渲染使用所选宋体及 LibreOffice；浏览器验收使用 Chromium。未声称在所有 Microsoft Word、WPS 或移动端版本上完成测试。相同页数也不等同于逐字位置完全一致。

## 如何复查

```sh
python -m pytest -q
BAMBOO_BROWSER_TEST=1 python -m pytest tests/test_editor_browser.py -q
python -m bamboo edit
python -m bamboo check examples/daodejing.bamboo
python -m bamboo render examples/daodejing.bamboo -o output/flow --name daodejing
python -m bamboo render examples/horizontal.bamboo -o output/horizontal --name horizontal
python -m bamboo render examples/annotations.json -o output/annotations --name annotations
python -m bamboo render examples/custom.json -o output/custom --name custom
```

自动化测试不等同于实际渲染验收。更换字体、修改分页或 DOCX 页面结构后，应重新检查整份样书的每一页，特别是夹注续栏、版心长标题和尾页内容。`manifest.json` 记录源文摘要、字体摘要、各输出文件的字节数与 SHA-256，可用于确认检查的文件与交付的文件一致。
