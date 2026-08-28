# CATIA V5 CHM 提取指南

CATalyst 默认自带 R27 版本的预编译数据库。但如果你需要适配特定版本（如 R21 或 V5-6R2019），你需要从本地安装的 CATIA 中提取官方 Automation 帮助文档。

## 提取步骤

### 1. 定位安装目录
官方 `V5Automation.chm` 文件通常位于 CATIA 安装目录的 `code\bin` 下。
典型路径：
- `C:\Program Files\Dassault Systemes\B27\win_b64\code\bin\V5Automation.chm`
- `C:\Program Files\Dassault Systemes\B21\intel_a\code\bin\V5Automation.chm`

### 2. 验证文件
确保该文件双击打开应能看到 "V5 Automation" 标题的帮助文档。

### 3. 复制到 CATalyst
将该文件复制到本项目的 `data` 目录下，并确保文件名为 `V5Automation.chm`。
```bash
cp "C:\Program Files\Dassault Systemes\B27\win_b64\code\bin\V5Automation.chm" data/
```

### 4. 重新构建数据库
在项目根目录运行构建脚本：
```bash
uv run build.py
```
这会自动解包 CHM 并重建 `dist/catalyst.db`。
