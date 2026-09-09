<div align="center">

# Bamboo · 简牍

**古籍与传统文书的编辑排版引擎**

从纸面输入，到成书导出。

横竖排 · 17 种页面样式 · 册簿 · 族谱 · 工尺谱

[快速开始](#快速开始) · [专用文档](#专用文档) · [页面样式](#页面样式) · [导出与分享](#导出与分享) · [文档](#文档)

</div>

![简牍排版示例：题签、序言、诗文与典籍](docs/assets/styles.png)

简牍提供可直接操作的编辑界面：点击纸面输入文字，拖选添加注释，调整版式后即时重排。支持古籍正文、册簿、族谱和工尺谱，可导出 **PDF、HTML 与可编辑 Word 文档**。

## 用熟悉的方式编辑

- **直接书写**：中文输入法、粘贴、分段、选区、撤销与重做。
- **横竖自由组合**：同一本书的不同篇章可分别设置文字方向、纸张尺寸和页码。
- **细致表达注释**：双行夹注、段后注、短旁注、旁批、眉批、脚注与关联编号注释。
- **按需装饰版面**：边框、界栏、版心、鱼尾、书名和卷次均可独立设置。
- **统一文字风格**：11 种可复用文字样式，涵盖正文、题名、序言、诗文、署名和题跋等。
- **保留编辑成果**：文档自动保存在本机，可保存副本并继续编辑。

<details>
<summary>查看纸面编辑界面</summary>

![简牍纸面编辑界面](docs/assets/editor.png)

</details>

## 朱批手稿

黑字正文、朱色句读、栏间旁批与多栏眉批可以组合排版。批注可分别调整颜色、字号和小栏数；开启自动续排后，长批注会利用栏间空位续栏或续页。点击红色批注即可编辑。

选择“朱批手稿”页面样式，在字体选项中选择楷体或霞鹜文楷，开启“对页预览”可并排查看两页。未安装文楷时，可点击“获取霞鹜文楷”，或运行 `bamboo fonts --install-wenkai` 下载到本机缓存。

[打开朱批手稿样例](examples/manuscript-notes.json)

<details>
<summary>查看黑字朱批与红色句读排版</summary>

![朱批手稿的两页排版效果](docs/assets/manuscript.png)

</details>

Word 保留可编辑正文与批注文字框。密集朱批按导出时的页内位置排放；在 Word 中改变正文分页后，应在简牍原稿中修改并重新导出。

## 快速开始

需要 **Python 3.9 或更新版本**。

```sh
git clone https://github.com/zhoucanzong/Bamboo.git
cd Bamboo

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

bamboo edit
```

在 Windows 命令提示符（cmd）中，可将激活环境的命令替换为 `.venv\Scripts\activate`。

启动后，在浏览器中打开 **http://127.0.0.1:8765**。

1. 点击 **新建**，在纸面上输入正文；或选择工具栏中的 **册簿、族谱、工尺谱**。
2. 选择页面样式，调整横竖方向、字号、纸张和留白。
3. 选中文字添加注释，或在专用编辑器中填写记录。
4. 点击 **导出**，选择 PDF、HTML 或 Word。

普通回车分段，`Shift + 回车` 在段内换行，适合诗文分行。使用 `Ctrl / ⌘ + Z` 撤销。

<details>
<summary><strong>启动选项与文档保存</strong></summary>

```sh
# 指定端口与文档目录，不自动打开浏览器
bamboo edit --no-browser --port 8765 --workspace output/editor
```

默认文档目录为 `output/editor/documents`。重启时使用相同目录，即可继续编辑已保存的文档。

- **打开**：载入 Word、UTF-8 文本或编辑文档副本。
- **保存副本**：下载可再次打开的编辑文件，便于备份和迁移。
- **自动保存**：保存当前内容；撤销历史保留在本次服务会话中。

</details>

## 专用文档

### 册簿 · 清楚记录每一笔

填写姓名、金额、物品、日期和备注，支持增删、排序与纸面点击定位。自动生成金额大写、每页小计和总计，提供横排与竖排两种形式。

[打开册簿样例](examples/register.json)

<details>
<summary>查看册簿编辑界面</summary>

![册簿记录与金额统计](docs/assets/register-editor.png)

</details>

### 族谱 · 让人物关系有序呈现

录入人物、生卒信息与传记，选择父母和配偶，自动计算世代并生成世系图。支持关系校验、跨页续接提示和人物传记页。

[打开族谱样例](examples/genealogy.json)

<details>
<summary>查看族谱编辑界面</summary>

![族谱世系图与人物记录](docs/assets/genealogy-editor.png)

</details>

### 工尺谱 · 谱字与唱词相互对应

编辑分句、谱字、板眼、音区标注和唱词，支持一字多音、对应组移动及自动分组分页。常用谱字提供候选，也可填写原谱记号。

[打开工尺谱样例](examples/gongche.json) · [了解记谱范围](docs/gongche.md)

<details>
<summary>查看工尺谱编辑界面</summary>

![工尺谱的谱字、板眼与唱词](docs/assets/gongche-editor.png)

</details>

下载样例后，在简牍中点击 **打开** 即可编辑。工尺谱样例用于演示排版，不对应真实曲目；当前功能不包含自动演奏。

## 页面样式

题签封面、序言、诗文与正文可以组合成册。选择一个页面样式作为起点，再独立调整配色、边框、界栏、字号与留白。

| 类别 | 可选样式 |
| --- | --- |
| **古籍双面** | 朱栏序言、诗文疏排、典籍密排、素墨古籍、米纸刻本 |
| **单页竖排** | 朱批手稿、无装饰书页、单页墨栏、蓝栏抄本、大字疏排、袖珍小本、宽栏批校、序跋留白、经文长行 |
| **横排阅读** | 横排书页、横排研读、横排双栏 |

点击 **页面样式** 可查看全部 17 种预览。应用到当前篇章，或从当前段落另起一篇；已录入的正文会随新版式重排。

[查看页面样式选集](examples/page-styles.json) · [查看题签与诗文样例](examples/styles.json)

<details>
<summary>展开页面样式库与鱼尾符号库</summary>

![17 种页面样式预览](docs/assets/page-styles.png)

6 种鱼尾样式各支持上、下、左、右方向。题签边框可选无、单线或双线；文字方印支持朱文、白文，使用当前文档字体。

![可选鱼尾符号](docs/assets/symbols.png)

</details>

## 导出与分享

| 格式 | 适合用途 | 保留内容 |
| --- | --- | --- |
| **PDF** | 阅读、打印、存档 | 确定的分页与版面，可选择的文字 |
| **HTML** | 离线阅读、浏览器展示 | 内嵌字体、页面预览与可复制原文 |
| **Word / DOCX** | 继续编辑、文稿交接 | 横竖文字、表格、注释及可编辑图形 |

PDF 与 HTML 使用同一版面。Word 的最终换行和分页由阅读器计算，可能与预览存在差异；脚注和复杂批注的呈现方式也有所不同。

在 Word 中大量修改册簿记录、族谱框线或工尺谱合并结构后，建议回到简牍核对数据并重新排版。更多细节见 [格式说明](docs/typography.md) 与 [验证记录](docs/validation.md)。

## 文档

| 入口 | 内容 |
| --- | --- |
| [编辑指南与接口](docs/editor.md) | 编辑操作、保存恢复、专用文档与接入方式 |
| [版式与格式说明](docs/typography.md) | 注释、符号、专用版式和当前支持范围 |
| [工尺谱说明](docs/gongche.md) | 谱字、唱词对应及记谱边界 |
| [排版架构](docs/architecture.md) | 文档模型、布局与导出设计 |
| [验证记录](docs/validation.md) | 自动化检查与实际渲染结果 |
| [全部样例](examples/) | 可编辑样例与批处理输入 |

<details>
<summary><strong>开发与批处理</strong></summary>

```sh
python -m pip install -e '.[test]'
python -m pytest -q

# 将样例导出为 PDF、HTML 和 Word
bamboo render examples/styles.json -o output/styles --name styles

# 只导出可编辑 Word
bamboo render examples/register.json --formats docx -o output/register
```

需要指定字体时，可使用 `--font /path/to/font.otf`。浏览器测试的运行方式见 [验证记录](docs/validation.md)。

</details>

## 许可证

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

本许可适用于简牍自有代码，第三方组件遵循各自许可证，详见 [第三方组件说明](THIRD_PARTY_NOTICES.md)。
