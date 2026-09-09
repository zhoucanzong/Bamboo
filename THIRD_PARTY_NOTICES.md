# 第三方组件说明

Apache License 2.0 适用于 Bamboo 自有代码，不替代第三方组件的许可证，也不意味着所有依赖组合仅受 Apache License 2.0 约束。

| 组件 | 用途 | 许可证来源 |
| --- | --- | --- |
| PyMuPDF / MuPDF | 字体测量、PDF 写出和渲染 | [AGPL 3.0 或 Artifex 商业许可](https://github.com/pymupdf/PyMuPDF) |
| python-docx | 原生 Word 文件读写 | [MIT](https://github.com/python-openxml/python-docx/blob/master/LICENSE) |
| fontTools | 字体读取与子集处理 | [MIT](https://github.com/fonttools/fonttools/blob/main/LICENSE) |
| lxml | XML 处理，由 python-docx 引入 | [BSD 等相关声明](https://lxml.de/copyright.html) |

当前版本仍依赖 PyMuPDF，未将其重新许可为 Apache 2.0。分发、部署或商业集成时，需结合实际使用方式遵守其许可要求；本项目的 LICENSE 不豁免这些义务。

可选的[霞鹜文楷](https://github.com/lxgw/LxgwWenKai)采用 [SIL OFL 1.1](https://github.com/lxgw/LxgwWenKai/blob/main/OFL.txt)。字体获取功能使用固定版本和 SHA-256 校验，并将许可文件一并保存到本机缓存。

字体由使用者的系统或指定文件提供，不随源码分发。字体的使用和嵌入仍受字体自身许可证约束。示例图由简牍生成。

开发和测试用组件依照各自许可证使用，不因安装在开发环境中而成为本项目自有代码。以上链接帮助定位声明，最终以实际分发版本携带的许可证和适用依赖声明为准。
