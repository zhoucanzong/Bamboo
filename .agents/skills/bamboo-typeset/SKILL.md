---
name: bamboo-typeset
description: 用简牍排印或编辑中文古籍及册簿、族谱、工尺谱。适用于横竖混排、夹注、段后注、朱批、眉批及 PDF、HTML、流式 Word 导出。
---

先保留用户原文、繁简、段落和注释归属。没有指定边框、版心或鱼尾时，从 blank 版式开始；它也适合作为无装饰竖排的起点。

**有 Bamboo MCP 时**：用 `list_styles` 选版式，以 `create_document` 建立原稿。已给出文档标识时，用 `read_document` 读取原稿和版本，避免重建副本。修改用 `edit_document`，传当前 `expected_revision`；冲突后先读取变化。调用 `check_document` 和 `export_document`，取返回的文件路径和原稿。路径指服务所在电脑。

**只有命令行时**：使用装有简牍的 Python 环境。将原稿写成 UTF-8 JSON，在用户的工作目录内选择新的输出目录和文件名。下面的命令以用户需要 PDF、HTML 和 Word 为例：

```sh
python -m bamboo check source.json
python -m bamboo render source.json -o out --name book --formats pdf html docx --docx-mode flow
```

没有现成原稿时，以 [带注书页](assets/annotated-page.json) 为结构示例，用用户内容替换示例文字；不要把演示批语当作原文。向用户交付排版成果，不要求用户编写源文件。若用户要在纸面上继续修改，交付原稿 JSON，并说明可在 `bamboo edit` 中打开。

- 正文、夹注在同一段落的 `inlines` 内按阅读顺序排列，小字双行用 `kind: note`。随段讲解另设 `kind: commentary` 段落。
- 眉批及栏间旁批用 `annotations` 关联原文；`block`、`inline`、`offset` 从零开始，偏移取该行内文本中的 Unicode 码点。上方眉批用 `placement: top`，栏间用 `side`，需要避让、续栏续页时设 `flow: true`，并留出批注空间。句读颜色在 `profile.punctuation_color` 单独设置。
- 册簿、族谱、工尺谱保留记录、亲属关系、谱字与唱词的对应。使用仓库 `examples/register.json`、`examples/genealogy.json`、`examples/gongche.json` 中对应的结构化原稿；独立安装 Skill 时也可从[示例目录](https://github.com/zhoucanzong/Bamboo/tree/skill/examples)查看。不要把关系或金额汇总改写成一段说明文字。
- 默认交付流式 Word；仅在用户选择整页图像保真时使用 facsimile。核对导出警告和实际生成的文件，密集朱批要重点检查锚点与跨页位置。PDF、HTML 给出固定版面；大幅改动流式 Word 正文后，需在简牍原稿调整并重新导出密集批注。
