# CATalyst Project Agent Guidelines

## CATIA API 调用铁律 (Ground Truth Policy)
- **绝对禁止脑补 API**：严禁凭 LLM 记忆幻觉捏造 CATIA V5 的 COM 接口名、属性名、方法名或枚举常量。
- **唯一可信数据源**：所有 CATIA Automation API 必须严格通过本地 `dist/catalyst.db` 检索校验（使用 `catalyst_cli.py` 或 `src/engine/db.py`）。
- **签名一致性**：大小写、参数列表及返回值类型必须 100% 符合 IDL 规范。
