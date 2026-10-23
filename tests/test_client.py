"""
Unit tests for CatiaClient and diagnostics.
"""

import sys
import pytest
from src.client import CatiaClient


def test_client_initialization():
    client = CatiaClient()
    assert client.prog_id == "CATIA.Application"

    custom_client = CatiaClient(clsid="CATIA.Application.Special")
    assert custom_client.prog_id == "CATIA.Application.Special"


def test_client_diagnostic_report_format():
    client = CatiaClient()
    report = client.get_diagnostic_report()
    assert isinstance(report, str)
    assert "# CATIA V5 Diagnostic Report" in report
    assert "## Host Environment" in report
    assert "Operating System" in report
    assert "Python Version" in report
    assert "## CATIA Connection Status" in report


def test_client_is_pywin32_available():
    # If on windows, pywin32 is expected or tested as boolean
    avail = CatiaClient.is_pywin32_available()
    assert isinstance(avail, bool)
