# CATalyst 实战使用手册

本手册展示如何通过 CATalyst 的 **10 个 MCP 工具** 与 **对称 CLI（`catalyst_cli.py`）**，编写零幻觉的 CATIA V5 自动化脚本（Python `win32com` / VBScript）并解决非 COM 的配置与批处理难题。

> **前提**：请先在仓库根目录完成一次一键安装（Windows：`.\install.ps1`；macOS/Linux：`./install.sh`）。

---

## 场景一：展开继承链，消除 COM API 幻觉

CATIA V5 的原始帮助文档默认不展示父类成员。例如 `Pad`（凸台）的 `GetDirection` 实际定义在父类 `Prism` 上；控制显示/隐藏的接口名是 `VisPropertySet`（而非 `Selection.VisProperties` 属性名本身）。

```bash
# 1. 不确定接口名时先做全局检索（支持按类型过滤：interface / enum / property / method）
uv run python catalyst_cli.py search "SetShow" --type method

# 2. 按需精准查询单个成员（极省 Token，自动带出 declared_in 继承来源与 pywin32 提示）
uv run python catalyst_cli.py get VisPropertySet --member SetShow
uv run python catalyst_cli.py get Pad --member GetDirection
```

---

## 场景二：Python (`win32com`) 调用 `CATSafeArrayVariant` 与 `[out]` 参数

在 Python 中通过 `win32com.client` 操作 CATIA 时，动态分发对象没有 IDE 补全，且涉及数组或 `[out]` 参数容易踩坑：

```bash
# 查询 Viewer3D 的背景色设置方法（自动从父类 Viewer 融合出来）
uv run python catalyst_cli.py get Viewer3D --member PutBackgroundColor
```

输出中会明确标出：
- 签名：`PutBackgroundColor(color: CATSafeArrayVariant) -> void`（`declared_in: Viewer`）
- `python_mapping` 提示：`CATSafeArrayVariant` 在 Python 中传入 `list` 或 `tuple`。

```python
import win32com.client

catia = win32com.client.Dispatch("CATIA.Application")
viewer = catia.ActiveWindow.ActiveViewer
viewer.PutBackgroundColor([0.2, 0.2, 0.2])  # RGB 浮点分量 (0.0 ~ 1.0)
```

---

## 场景三：枚举常量双向查询

在 Python `win32com` 未提前生成 TypeLib 绑定时，常需要把枚举常量名转换为对应整数，或根据返回的整数反查含义：

```bash
# 查询完整枚举表
uv run python catalyst_cli.py enum CatProductSource

# 通过整数反查枚举名（例如 1 -> catProductMade）
uv run python catalyst_cli.py enum CatProductSource --value 1

# 通过成员名反查所属枚举及数值
uv run python catalyst_cli.py enum --member catVisPropertyNoShowAttr
```

示例输出（实测来自 `catalyst.db`）：

| 枚举名 | 成员名 | 整数值 | 说明 |
| :--- | :--- | :---: | :--- |
| `CatProductSource` | `catProductMade` | `1` | The product is made within the company |
| `CatProductSource` | `catProductBought` | `2` | The product is bought from outside of the company |
| `CatVisPropertyShow` | `catVisPropertyShowAttr` | `0` | The show state |
| `CatVisPropertyShow` | `catVisPropertyNoShowAttr` | `1` | The No Show state |

---

## 场景四：社区实战配方与 `Selection.Search` 语法

遇到高频工业场景（批量导出 STEP、装配体 BOM/惯量、Catalog 批处理、工程图图框等），直接按自然语言意图检索经过 AST 校验的 `win32com` 配方：

```bash
# 自然语言 BM25 检索社区实战配方
uv run python catalyst_cli.py recipe "export step"
uv run python catalyst_cli.py recipe "CreateCatalogFromcsv"

# 查阅特定接口的官方 VBScript 或社区 Python 用例
uv run python catalyst_cli.py usecase Pad --source official

# 查询精确的 Selection.Search 工作台前缀与语法
uv run python catalyst_cli.py syntax --workbench PartDesign
```

---

## 场景五：非 COM 能力检索（离线手册 / `Tools > Options` / 官方样板）

当本机构建了可选的 `dist/local/catalyst_docs.db` 后，可以直接检索 COM 之外的工程知识（例如批处理命令语法、无 `SettingController` 暴露的 `Tools > Options` 选项、`CATNls` 键值及官方 `.csv`/`.CATPart`/`.catalog` 样板）：

```bash
# 搜索用户手册与 Tools > Options 文档
uv run python catalyst_cli.py docs "Catalog Batch Mode" --category user_guide

# 读取指定章节正文（同时带出官方警告、关联样板和本地截图路径）
uv run python catalyst_cli.py doc-page "cceug_C2/cceugbt0102.htm" --section "Batch Mode"

# 搜索 CATNls 界面文案与选项键（支持 CamelCase 自动拆分）
uv run python catalyst_cli.py settings "FavoriteCatalog"

# 搜索官方文本样板（带正文）或二进制 CAD 模板（带本机绝对路径）
uv run python catalyst_cli.py samples "BatchCatalog" --ext .csv --content
uv run python catalyst_cli.py samples "AISC_C" --ext .catpart
```

---

## 场景六：AI Agent / 编辑器自动调用 MCP（推荐）

运行 `.\install.ps1`（或 `./install.sh`）将 `catalyst` 注册到 Antigravity、Claude Code、Codex 或其他支持 MCP 的 AI Agent / 代码编辑器后，无需手动敲 CLI，直接自然语言提问即可：

> "帮我写一个 Python `win32com` 脚本，给当前 Part 里的倒角特征读取半径并批量导出 STEP，先用 CATalyst 确认 `ConstRadEdgeFillet` 接口签名和 STEP 导出配方。"

AI Agent 会自动在后台串联调用：
1. `get_catia_interface(name="ConstRadEdgeFillet")` 核对真实签名与继承属性；
2. `search_catia_recipes(query="export step")` 获取工业级 `win32com` 导出模式；
3. 若涉及 `Tools > Options` 或批处理协议，再自动调用 `search_catia_docs` / `search_catia_settings` / `search_catia_samples`；
4. 输出经过签名核验的可执行脚本。
