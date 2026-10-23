"""
CATIA COM Automation Client & Diagnostic Module.
Provides safe connection handling and diagnostic reports for active CATIA V5 sessions.
"""

import sys
import platform
from typing import Optional, Dict, Any


class CatiaClient:
    """
    Client for interacting with and diagnosing running CATIA V5 COM instances.
    """

    def __init__(self, clsid: Optional[str] = None):
        self.prog_id = clsid if clsid else "CATIA.Application"
        self._application = None

    @staticmethod
    def is_pywin32_available() -> bool:
        """Checks if win32com is installed and usable on the current system."""
        try:
            import win32com.client  # noqa: F401
            return True
        except ImportError:
            return False

    def connect(self) -> Any:
        """
        Attempts to connect to an active CATIA V5 instance via COM ROT (Running Object Table).
        Returns the CATIA Application dispatch object or None if not found/error.
        """
        if sys.platform != "win32":
            raise OSError("CATIA V5 Automation is only supported on Windows platforms.")

        if not self.is_pywin32_available():
            raise ImportError(
                "The 'pywin32' package is required to connect to CATIA V5. "
                "Install it via `pip install pywin32` or `uv pip install pywin32`."
            )

        import win32com.client
        try:
            self._application = win32com.client.GetActiveObject(self.prog_id)
            return self._application
        except Exception:
            self._application = None
            raise

    def is_running(self) -> bool:
        """Returns True if an active CATIA V5 instance can be reached."""
        try:
            self.connect()
            return self._application is not None
        except Exception:
            return False

    def get_diagnostic_report(self) -> str:
        """
        Generates a comprehensive Markdown diagnostic report of the host environment
        and the currently active CATIA V5 instance.
        """
        lines = []
        lines.append("# CATIA V5 Diagnostic Report\n")
        lines.append("## Host Environment")
        lines.append(f"- **Operating System**: `{platform.system()} {platform.release()}` ({platform.architecture()[0]})")
        lines.append(f"- **Python Version**: `{platform.python_version()}`")
        lines.append(f"- **Platform**: `{sys.platform}`")
        lines.append(f"- **pywin32 Available**: `{'Yes' if self.is_pywin32_available() else 'No'}`\n")

        if sys.platform != "win32":
            lines.append("## CATIA Connection Status")
            lines.append("> ❌ **Unavailable**: CATIA V5 Automation COM API requires a Windows environment.\n")
            return "\n".join(lines)

        if not self.is_pywin32_available():
            lines.append("## CATIA Connection Status")
            lines.append("> ⚠️ **pywin32 Missing**: Please install pywin32 (`pip install pywin32`).\n")
            return "\n".join(lines)

        lines.append("## CATIA Connection Status")
        try:
            app = self.connect()
            lines.append("> ✅ **Connected**: Successfully attached to active CATIA V5 session via Running Object Table (ROT).\n")
            lines.append("## Instance Information")
            
            # Application Name & Caption
            try:
                name = getattr(app, "Name", "CATIA")
                caption = getattr(app, "Caption", "CATIA V5")
                lines.append(f"- **Application Name**: `{name}`")
                lines.append(f"- **Window Caption**: `{caption}`")
            except Exception:
                pass

            # System Configuration details
            try:
                sys_conf = getattr(app, "SystemConfiguration", None)
                if sys_conf:
                    rel = getattr(sys_conf, "Release", "Unknown")
                    sp = getattr(sys_conf, "ServicePack", "Unknown")
                    lines.append(f"- **Release**: `V5R{rel}`")
                    lines.append(f"- **Service Pack**: `SP{sp}`")
            except Exception:
                pass

            # Visibility
            try:
                vis = getattr(app, "Visible", None)
                if vis is not None:
                    lines.append(f"- **Visible**: `{'Yes' if vis else 'No'}`")
            except Exception:
                pass

            # Documents
            try:
                docs = getattr(app, "Documents", None)
                if docs:
                    doc_count = getattr(docs, "Count", 0)
                    lines.append(f"- **Open Documents**: `{doc_count}`")
                    if doc_count > 0:
                        active_doc = getattr(app, "ActiveDocument", None)
                        if active_doc:
                            doc_name = getattr(active_doc, "Name", "Unknown")
                            lines.append(f"- **Active Document**: `{doc_name}`")
            except Exception:
                pass

        except Exception as e:
            lines.append(f"> ❌ **Connection Failed**: Unable to connect to active CATIA instance (`{e}`).\n")
            lines.append("### Troubleshooting Steps:")
            lines.append("1. **Verify Process**: Ensure CATIA V5 (`CNEXT.exe`) is running and fully initialized.")
            lines.append("2. **Integrity / Privilege Level**: Ensure CATalyst and CATIA run with matching privilege levels (e.g., both non-admin or both Administrator).")
            lines.append("3. **ROT Registration**: If CATIA was started via automation without UI or under a different session, it may not be in the global ROT.")

        return "\n".join(lines)


if __name__ == "__main__":
    client = CatiaClient()
    print(client.get_diagnostic_report())
