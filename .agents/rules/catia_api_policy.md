# CATIA Automation API 强制约束原则 (Ground Truth Policy)

## 核心铁律
1. **严禁凭空脑补 (Zero Hallucination)**：
   - 严禁依赖 LLM 记忆幻觉编写任何 CATIA V5 COM / Automation API 接口、属性、方法、参数或枚举常量。
   - 诸如 `ServicePackNumber`、`BuildNumber` 这类看似合理实则不存在的伪属性必须彻底杜绝。

2. **单一可信源 (Single Source of Truth - catalyst.db)**：
   - 本项目及所有相关自动化脚本中涉及的每一个 CATIA API 必须先从本地 `catalyst.db` 检索验证。
   - 检索方式：
     - CLI 检索：`catalyst_cli.py get <Interface>` / `catalyst_cli.py search <keyword> -t <type>` / `catalyst_cli.py enum <EnumName>`
     - 代码层：直接通过 `from src.engine.db import CatalystDB` 查库。
     - MCP 服务：通过 `get_catia_interface` / `search_catia_api` / `get_catia_enum` 工具。

3. **代码实现规范**：
   - 所有属性名大小写、参数数量、返回值类型（如 `long`, `CATBSTR`, `CATSafeArrayVariant`）必须与 `catalyst.db` 中的 IDL 描述 100% 严格一致。
   - 若在 `catalyst.db` 中检索不到对应 API，必须明确告知接口未在 CATIA V5 Automation 中暴露，禁止自行捏造。
