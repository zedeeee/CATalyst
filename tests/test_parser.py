import pytest
import tempfile
from pathlib import Path
from src.parser.html_parser import CatiaHtmlParser

@pytest.fixture
def parser():
    return CatiaHtmlParser()

def test_parse_interface(parser):
    html_content = """
    <html>
    <head><title>Catia V5 - Interface Pad</title></head>
    <body>
    <table class="DocHeader">
        <tr><td class="DocHeader1">
            <h1><a name="Top"></a>Pad</h1>
        </td></tr>
        <tr><td class="CAAiDntCheck">
            <b>Framework</b>: <a href="#">PartInterfaces</a>
        </td></tr>
    </table>
    
    <table class="classbr">
        <tr><td>class <b>Pad</b></td></tr>
    </table>
    
    <p><b><i> Represents the pad shape.</i></b><br></p>
    
    <h2>Property Index</h2>
    <dl>
        <dt><img alt="o" src="../_index/images/prop.gif"> <a href="#FirstLimit"><b>FirstLimit</b></a></dt>
        <dd>Returns the first limit.</dd>
    </dl>
    
    <h2>Method Index</h2>
    <dl>
        <dt><img alt="o" src="../_index/images/meth.gif"> <a href="#SetDirection"><b>SetDirection</b></a></dt>
        <dd>Sets the direction.</dd>
    </dl>
        <h2>Properties</h2>
        <a name="FirstLimit"></a><a name="FirstLimit()"></a>
        <table><tr><td>
            o Property <b>FirstLimit</b>( ) As <script>activateLink('Limit','')</script>  (Read Only)
        </td></tr></table>
        <dl><dd>Returns the first limit.</dd></dl>
        
        <h2>Methods</h2>
        <a name="SetDirection"></a><a name="SetDirection(Reference)"></a>
        <table><tr><td>
            o Sub <b>SetDirection</b>( <tt>iLine</tt> )
        </td></tr></table>
        <dl><dd>Sets the direction.</dd></dl>
    </body>
    </html>
    """
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    try:
        part_interfaces_dir = Path(temp_dir) / "PartInterfaces"
        part_interfaces_dir.mkdir()
        
        temp_path = part_interfaces_dir / "interface_Pad_123.htm"
        with open(temp_path, mode='w') as f:
            f.write(html_content)
            
        data = parser.parse_interface(temp_path)
        assert data["name"] == "Pad"
        assert data["framework"] == "PartInterfaces"
        assert "Represents the pad shape." in data["description"]
        
        assert len(data["properties"]) == 1
        assert data["properties"][0]["name"] == "FirstLimit"
        assert data["properties"][0]["type"] == "Limit"
        assert data["properties"][0]["readonly"] is True
        
        assert len(data["methods"]) == 1
        assert data["methods"][0]["name"] == "SetDirection"
        assert data["methods"][0]["return_type"] == "void"
        assert len(data["methods"][0]["params"]) == 1
        assert data["methods"][0]["params"][0]["name"] == "iLine"
        assert data["methods"][0]["params"][0]["type"] == "Any"
    finally:
        temp_path.unlink()
