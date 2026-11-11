# 通过 MCP 使用简牍

在安装了简牍的电脑上，MCP 客户端可以通过标准输入输出启动服务，直接创建、编辑和导出原稿。无需启动网页编辑器或开放网络端口。

## 安装与连接

在仓库根目录使用 Python 3.10 或更新版本的虚拟环境安装：

```sh
python -m pip install -e '.[mcp]'
```

将以下配置加入支持 stdio 的客户端。把两处绝对路径替换为本机路径；Windows 的命令路径可以使用虚拟环境中的 `Scripts/python.exe`。

```json
{
  "mcpServers": {
    "bamboo": {
      "command": "/absolute/path/to/venv/bin/python",
      "args": ["-m", "bamboo", "mcp", "--workspace", "/absolute/path/to/bamboo-library"]
    }
  }
}
```

客户端负责启动服务。手动运行同一命令时，它会等待协议消息。缺少本机中文字库时，可通过客户端的环境变量 `BAMBOO_FONT` 指定可嵌入的中文字体。

## 从原稿到成书

1. 调用 `list_styles` 选择版式。调用 `create_document`，例如：

   ```json
   {"page_style":"manuscript-notes","book":{"title":"读书记","blocks":[{"inlines":[{"text":"学而时习之。"},{"kind":"note","text":"随文双行小注"}]}]}}
   ```

2. 保存返回的 `document_id` 和 `revision`。用 `list_documents` 找回既有原稿，或用 `read_document` 读取正文、段落标识和选区。
3. 用 `edit_document` 提交当前 `expected_revision` 和命令数组，例如 `[{"type":"set_metadata","values":{"title":"读书札记"}}]`。正文修改、段后注、眉批等均使用编辑器的事务命令。版本过期或命令无效时整组不写入；请重新读取后再决定如何修改。MCP 不保存撤销栈。
4. 用 `check_document` 检查排版及字体。调用 `export_document`，例如传入 `document_id` 和 `formats: ["pdf","html","docx"]`。结果包含文件路径、页数与提示。页数指固定版式，Word 会按阅读器重排。

原稿保存在所选目录的 SQLite 数据库，重启后使用同一目录即可继续。每次导出使用新的子目录，不覆盖上次成书。返回的 `source.json` 可在简牍界面通过“打开”继续编辑；它与数据库中的原稿是独立副本。MCP 实现使用[官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk)。
