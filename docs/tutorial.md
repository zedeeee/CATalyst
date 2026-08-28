# CATalyst 实战指导手册

本手册教你如何利用 CATalyst 配合大语言模型（LLM）或纯手动编写零 BUG 的 CATIA V5 自动化脚本（VBScript / Python）。

## 核心痛点与解法
以前写 CATIA 宏，最头疼的是**不知道对象有什么属性**，尤其是**继承来的属性**。
例如：你要修改 `Pad`（凸台）的第一个极限长度。
你在官方文档看 `Pad`，里面只有 `FirstLimit` 属性。你去查 `Limit`，只有 `Dimension` 属性。你去查 `Length`，只有 `Value` 属性。在庞大的继承树和层级跳跃中，AI 极易产生幻觉。

用 CATalyst，你只需要一行命令就能得到完整签名的铺平结果，彻底消除盲区。

---

## 场景一：配合 AI 编写宏代码
当你在 Cursor、Windsurf 或普通 ChatGPT 中写宏时，**不要让 AI 猜 API**！

**错误做法**：
> "帮我写个CATIA宏，遍历所有零件并隐藏它们" 
*(AI 会虚构出 `part.Hide()` 这种不存在的函数)*

**正确做法（配合 CATalyst）**：
1. 先用 CLI 搜索你要找的功能：
   ```bash
   python catalyst_cli.py search "hide"
   ```
   发现需要用到 `Selection` 对象的 `VisProperties`。
2. 提取签名喂给 AI：
   ```bash
   python catalyst_cli.py get VisProperties > api_context.md
   ```
3. 把生成的文件扔给 AI 并提问：
   > "基于我提供的 VisProperties API 签名，写一个隐藏当前选中所有零件的宏。"

---

## 场景二：Python (pycatia / win32com) 开发
CATIA Automation 原生是 VBScript，但在 Python 中使用 `win32com` 时，所有对象底层都是 `CDispatch`，IDE **完全没有代码提示**。

**实战用法**：
当你通过 Python 拿到一个 `Viewer3D` 对象，想知道如何设置背景色时：
1. 查文档：
   ```bash
   python catalyst_cli.py get Viewer3D
   ```
2. 看到展开的方法列表中有：
   `PutBackgroundColor(iColorArray: CATSafeArrayVariant) -> void`
3. 在 Python 中安全调用：
   ```python
   import win32com.client
   catia = win32com.client.Dispatch("CATIA.Application")
   viewer = catia.ActiveWindow.ActiveViewer
   
   # 根据查到的参数类型传入 Array/List
   viewer.PutBackgroundColor([255, 0, 0]) # 设置为红色
   ```

---

## 场景三：枚举常量陷阱
VBScript 里可以直接写 `catPartDocument`，但在 Python 里，由于没有加载对应的 TypeLib，这个枚举变量可能会提示未定义，你通常必须传入它对应的**整数或精确字符串**。

**怎么查？**
```bash
python catalyst_cli.py enum CatDocumentTypes
```

输出将准确告诉你支持哪些枚举名，结合官方文档中枚举项的顺序（V5 枚举一般隐式对应 `0, 1, 2...` 或者你可以直接搜具体的枚举常量对应的值）：
| Name | Description |
|---|---|
| `catPartDocument` | Part document |
| `catProductDocument` | Product document |

---

## 终极武器：Agent MCP 模式 (推荐)
如果你使用的是支持 MCP (Model Context Protocol) 的 AI IDE（例如配置了 Antigravity 的环境）：
AI 会在你提问时，**自动**在后台调用 `get_catia_interface` 和 `search_catia_api` 补全知识。你只需要说：

> "帮我写个倒角宏，我不确定怎么用 EdgeFillet 接口，你自己查一下本地的 CATalyst 库然后给我写代码。"

AI 会自动完成以下操作：
1. 调用 `search_catia_api("EdgeFillet")`
2. 发现 `VarRadEdgeFillet` / `ConstRadEdgeFillet`
3. 调用 `get_catia_interface("ConstRadEdgeFillet")`
4. 读取被 CATalyst 融合了 `DressUpShape` 父类属性的完整签名
5. 直接输出 100% 可执行、零幻觉的 VBScript 代码。
