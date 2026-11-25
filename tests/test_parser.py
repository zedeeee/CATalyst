import shutil
import tempfile
from pathlib import Path
import pytest
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
        assert "Returns the first limit." in data["properties"][0]["description"]
        
        assert len(data["methods"]) == 1
        assert data["methods"][0]["name"] == "SetDirection"
        assert data["methods"][0]["return_type"] == "void"
        assert "Sets the direction." in data["methods"][0]["description"]
        assert len(data["methods"][0]["params"]) == 1
        assert data["methods"][0]["params"][0]["name"] == "iLine"
        assert data["methods"][0]["params"][0]["type"] == "Any"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_parse_interface_member_docs_params_and_role(parser, tmp_path):
    """Ensure <dl><dd>, Parameters:, Returns:, and Role descriptions are not dropped."""
    html_content = """
    <html><body>
    <h1>SyntheticMaterial</h1>
    <script>generatedFatherClass('interface_SyntheticMaterial_1','SyntheticMaterial','0');</script>
    <b><i> Represents a synthetic material object.</i></b><br>
    <b>Role</b>: Holds rendering and analysis properties for a CATMaterial library.<hr>
    <a name="PutIcon"><dt>
    <table><tr><td>o Sub <b>PutIcon</b>(<td><script>activateLink('CATBSTR','CATBSTR')</script> <td><tt>iPath</tt>)</table></dt>
    <dl>
      <dd>
     Read the icon of a material from JPEG file.
     The parameter is the path of the folder where the JPEG is going to be read
     Ex : E:\\folder\\
     <dl>
       <dt><b>Parameters:</b>
       <dd>
         <dl>
           <dt><tt>iPath</tt>
           <dd>Folder path containing JPEG thumbnails.
         </dl>
       <dt><b>Returns:</b>
       <dd>S_OK if succeeded, E_FAIL otherwise.
     </dl>
    </dl>
    </body></html>
    """
    fw_dir = tmp_path / "CATMatInterfaces"
    fw_dir.mkdir()
    fp = fw_dir / "interface_SyntheticMaterial_1.htm"
    fp.write_text(html_content, encoding="utf-8")

    data = parser.parse_interface(fp)
    assert "Represents a synthetic material object." in data["description"]
    assert "Holds rendering and analysis properties" in data["description"]

    assert len(data["methods"]) == 1
    m = data["methods"][0]
    assert m["name"] == "PutIcon"
    assert "path of the folder" in m["description"]
    assert "Ex : E:\\folder\\" in m["description"]
    assert "S_OK if succeeded" in m["returns_desc"]
    assert m["params"][0]["name"] == "iPath"
    assert m["params"][0]["type"] == "CATBSTR"
    assert "Folder path containing JPEG thumbnails." in m["params"][0]["description"]


def test_parse_multiline_func_return_type(parser, tmp_path):
    """Multi-row Func tables must capture the return type after ') As', not the first param type."""
    html_content = """
    <html><body>
    <script>generatedFatherClass('interface_SyntheticShapeFactory_1','SyntheticShapeFactory','0');</script>
    <b><i>Factory fixture.</i></b><hr>
    <table><tr><td>o Func <b>AddNewPad</b>(<td><script type="text/javascript"> activateLink('Sketch','Sketch')</script> <td><tt>iSketch</tt>,<tr><td></td><td><script type="text/javascript"> activateLink('double','double')</script> <td><tt>iHeight</tt>) As <script type="text/javascript"> activateLink('Pad','Pad')</script> </table></dt>
    <dl><dd>Creates and returns a new pad.</dl>
    </body></html>
    """
    fw_dir = tmp_path / "PartInterfaces"
    fw_dir.mkdir()
    fp = fw_dir / "interface_SyntheticShapeFactory_1.htm"
    fp.write_text(html_content, encoding="utf-8")

    data = parser.parse_interface(fp)
    assert len(data["methods"]) == 1
    m = data["methods"][0]
    assert m["name"] == "AddNewPad"
    assert m["return_type"] == "Pad"
    assert m["params"] == [
        {"name": "iSketch", "type": "Sketch"},
        {"name": "iHeight", "type": "double"},
    ]



