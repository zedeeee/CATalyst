"""
CATIA V5 Automation High-Risk Method Pitfall & Caveat Catalog.
Provides structured warnings for APIs whose runtime implementation contracts
diverge significantly from their IDL type library declarations or exhibit silent failure modes.
"""

from typing import Any, Dict, Optional, Tuple

# Key: (interface_name_lower, member_name_lower)
_METHOD_PITFALLS: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("material", "puticon"): {
        "interface": "Material",
        "member": "PutIcon",
        "severity": "CRITICAL",
        "category": "CONTRACT_VIOLATION",
        "summary": "入参 iPath 必须为包含图标的文件夹路径（末尾必须带反斜杠 \\），严禁传入文件全路径！",
        "detail": (
            "CATIA COM IDL 类型库将入参声明为 iPath: CATBSTR，但在底层 C++ 实现中强制硬编码无脑拼接 "
            "oMaterial.Name & \".jpg\"。若传入具体文件名路径（如 C:\\icons\\mat.jpg），内部将拼接为 "
            "C:\\icons\\mat.jpg\\mat.jpg 导致寻址失败，直接抛出没有任何有效错误描述的通用 COM 错误 "
            "E_FAIL (0x80004005 / -2147467259)。官方宏用例 CAAScdMatUseCases 中亦显式将文件名拼接注释掉。"
        ),
        "safe_pattern": "oMaterial.PutIcon(r'C:\\path\\to\\icons\\')  # 末尾反斜杠不可省略",
    },
    ("catalogdocument", "createcatalogfromcsv"): {
        "interface": "CatalogDocument",
        "member": "CreateCatalogFromcsv",
        "severity": "CRITICAL",
        "category": "RUNTIME_ENVIRONMENT",
        "summary": "必须在无 GUI 批处理环境中调用，且输入 CSV 必须为 ANSI 编码，严禁带 UTF-8 BOM。",
        "detail": (
            "CATIA 目录批量编译器底层对 UTF-8 BOM 无法解析，会识别为非法首字符并直接中断；"
            "若在前台交互界面或已有活动文档上下文执行容易导致 CATIA 进程死锁或弹窗阻塞。"
        ),
        "safe_pattern": (
            "catia.Visible = False\n"
            "catalog_doc.CreateCatalogFromcsv(csv_path_ansi, output_catalog_path)"
        ),
    },
    ("designtable", "synchronize"): {
        "interface": "DesignTable",
        "member": "Synchronize",
        "severity": "HIGH",
        "category": "CONCURRENCY_LOCK",
        "summary": "外部关联源文件在同步前必须确保未被独占锁定，且文本格式必须严格采用 Windows CRLF 换行。",
        "detail": (
            "若外部 Excel 文件被其他进程独占打开，调用 Synchronize() 会导致 CATIA COM 进程无限期挂起；"
            "若为外部文本表 (.txt)，若使用 Unix LF 换行，Synchronize() 不会报错但会静默丢弃所有新增配置行。"
        ),
        "safe_pattern": (
            "with open(txt_path, 'w', encoding='gbk', newline='\\r\\n') as f:\n"
            "    f.write(content)\n"
            "design_table.Synchronize()"
        ),
    },
}


def get_method_pitfall(interface_name: str, member_name: str) -> Optional[Dict[str, Any]]:
    """
    Look up known critical runtime caveats/pitfalls for a given interface member.
    Comparison is case-insensitive.
    """
    if not interface_name or not member_name:
        return None
    key = (interface_name.strip().lower(), member_name.strip().lower())
    return _METHOD_PITFALLS.get(key)


def get_interface_pitfalls(interface_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Get all registered method pitfalls for a specific interface.
    """
    if not interface_name:
        return {}
    target = interface_name.strip().lower()
    return {
        member: info
        for (iface, member), info in _METHOD_PITFALLS.items()
        if iface == target
    }
