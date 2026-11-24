# CATalyst 官方文档与样板源码穿透增量看板 (Linkage Diff Report)

> 基于 `catalyst.db` 与 `dist/local/catalyst_docs.db` 全库构建时自动生成的双向代码反向索引看板。

## 1. 核心穿透覆盖率指标对比

| 指标项 | 穿透前 (v0.2.0 Baseline) | 穿透后 (P1 Enriched) | 增量与改善 |
| :--- | :--- | :--- | :--- |
| **总接口总数** | 1137 个 | 1137 个 | - |
| **覆盖的接口数** | 691 个 (60.8%) | **773 个 (68.0%)** | **+82 个接口脱离零用例状态** |
| **总方法与属性数** | 19484 个 | 19484 个 | - |
| **穿透关联代码片段** | 3,777 条 (CHM Snippets) | **18250 条** | **+14473 条官方实战调用** |
| - 官方样板宏调用 (`.CATScript`) | 0 处穿透定位 | **5168 处精确行号代码** | 覆盖 2,415 个官方样板宏 |
| - 官方文档用例代码 (`.htm`) | 0 处穿透定位 | **9305 处实战代码** | 穿透 12,179 篇官方 HTML |

## 2. 重点解冻接口清单 (原零用例 -> 现已打通官方实战)

以下明星接口在官方 IDL 中无独立用例，现已通过源码反向索引成功穿透至官方样例与文档：

| 接口名称 | 关联官方样板宏调用数 | 关联官方文档代码数 | 典型穿透示例 |
| :--- | :--- | :--- | :--- |
| `Abqclampbc` | 0 处 | 4 处 | `Official CAA Macro` |
| `Abqdisplacementbc` | 0 处 | 3 处 | `Official CAA Macro` |
| `Activities` | 19 处 | 20 处 | `Official CAA Macro` |
| `Analysisexport` | 0 处 | 4 处 | `Official CAA Macro` |
| `Analysisimage` | 0 处 | 30 处 | `Official CAA Macro` |
| `Analysisimport` | 0 处 | 4 处 | `Official CAA Macro` |
| `Analysislinkeddocuments` | 0 处 | 41 处 | `Official CAA Macro` |
| `Analysismaterial` | 238 处 | 81 处 | `importMaterialLibrary.CATScript` |
| `Analysismeshmanager` | 0 处 | 44 处 | `Official CAA Macro` |
| `Analysismeshpart` | 6 处 | 333 处 | `Official CAA Macro` |
| `Analysismeshparts` | 0 处 | 54 处 | `Official CAA Macro` |
| `Analysismodel` | 0 处 | 85 处 | `Official CAA Macro` |
| `Analysispostmanager` | 0 处 | 8 处 | `Official CAA Macro` |
| `Annotation` | 0 处 | 16 处 | `Official CAA Macro` |
| `Annotations` | 0 处 | 4 处 | `Official CAA Macro` |
| `Annotationset` | 0 处 | 2 处 | `Official CAA Macro` |
| `Annotationsets` | 0 处 | 2 处 | `Official CAA Macro` |
| `Arrbomreport` | 0 处 | 1 处 | `Official CAA Macro` |
| `Arrnomenclature` | 0 处 | 7 处 | `Official CAA Macro` |
| `Arrnomenclatures` | 0 处 | 3 处 | `Official CAA Macro` |
| `Arrnomenclaturetree` | 0 处 | 2 处 | `Official CAA Macro` |
| `Arrsystemlineproduct` | 0 处 | 2 处 | `Official CAA Macro` |
| `Attachmentcont` | 0 处 | 1 处 | `Official CAA Macro` |
| `Basiccomponents` | 0 处 | 1 处 | `Official CAA Macro` |
| `Booleanshape` | 9 处 | 0 处 | `Official CAA Macro` |
| *(其余 57 个接口略)* | ... | ... | ... |

## 3. 典型地雷规避实战示例 (Material.PutIcon)

```vb
' 达索官方工程师在 CAAScdMatUseCases/importMaterialLibrarySource.htm 留下的避坑现场
oMaterial.PutIcon(sFolderIcon & sSep & oFamily.Name & sSep) ' & oMaterial.Name & ".jpg")
```

- **问题根因**：IDL 将入参声明为 `iPath: CATBSTR`，开发者常误传文件路径；CATIA 底层强行拼接造成 `E_FAIL`。
- **穿透防护**：现在通过 `get_catia_interface('Material', member_name='PutIcon')` 查询，系统自动注入结构化 `pitfall_warning` 并附带该官方样板精准行号。