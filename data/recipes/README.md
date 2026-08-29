# CATalyst 社区实战配方库 (Community Cookbook)

本目录存放经过安全脱敏、纯 `win32com` 编写的 CATIA V5 工业实战高频脚本配方。

---

## 🌟 核心特性

1. **纯文本 JSON 格式**：Git 友好、清晰展示 Diff，方便社区通过 Pull Request 贡献，彻底杜绝 SQLite 二进制合并冲突。
2. **免编译热重载 (Hot Reloading)**：在此目录下新增或修改任何 `.json` 文件后，CATalyst 的 CLI 与 MCP 服务**无需重新编译数据库，保存即生效**。
3. **精准来源追溯 (Provenance Tracking)**：每条配方记录原始论坛帖子 / GitHub 仓库的直达 Web 超链接与开源协议。
4. **企业私有扩展支持**：可在本目录下放置企业内部私有宏（如 `data/recipes/internal_tools.json`），系统启动时自动统一挂载加载。

---

## 📝 贡献新配方规范 (Schema Definition)

在 `data/recipes/` 下的 JSON 文件中追加条目，必须符合以下结构规范：

```json
{
  "interface_name": "目标核心接口名称 (如 Product, Pad, DrawingDocument, General)",
  "title": "配方名称与简述 (如：遍历装配体树并批量导出各零件为 STEP 格式)",
  "workbench": "所属工作台 (如 PartDesign, Assembly, Drafting, GenerativeShapeDesign)",
  "tags": "英文关键词标签，逗号分隔 (如 batch-export,step,assembly,product)",
  "provenance": {
    "source_type": "forum_thread | github_repo | forum_archive | blog_post",
    "source_url": "真实的 Web 网页直达超链接 (如 https://www.coe.org/p/fo/et/thread=26500)",
    "source_ref": "人类可读的项目/帖子标题 (如 COE Forum Topic: Batch Export STEP)",
    "author": "原作者/社区名称 (如 COE Community, Eng-Tips CAD Forum)",
    "license": "开源协议 (如 MIT / Public Domain / Apache-2.0)",
    "original_language": "原始语言 (如 VBScript / VBA / CATScript / Python)",
    "verified_date": "验证归档日期 (YYYY-MM-DD)"
  },
  "description": "应用场景描述与注意事项",
  "code": "标准、可执行、纯 win32com 编写的 Python 函数代码"
}
```

---

## 🛡️ 收录三大原则

1. **绝对脱敏**：严禁包含任何个人/企业特有的硬编码绝对路径（如 `C:\Users\username\...`）或机密物料号。
2. **纯 win32com Target**：代码统一使用原生 `win32com.client` 编写，不引入第三方重型非标准封装。
3. **函数化与异常处理**：每个配方封装为独立函数，包含清晰的入参类型标注与基础 `try...except` 错误处理。

