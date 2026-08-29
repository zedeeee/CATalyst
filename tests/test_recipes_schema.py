import json
import ast
import urllib.parse
from pathlib import Path

try:
    import pytest
except ImportError:
    class DummyPytest:
        def fixture(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
    pytest = DummyPytest()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_community_recipes_schema():
    recipes_dir = PROJECT_ROOT / "data" / "recipes"
    assert recipes_dir.exists(), "data/recipes directory must exist"

    required_top_keys = ["interface_name", "title", "workbench", "tags", "provenance", "description", "code"]
    required_prov_keys = ["source_type", "source_url", "source_ref", "author", "license", "original_language", "verified_date"]

    json_files = list(recipes_dir.glob("*.json"))
    assert len(json_files) > 0, "At least one community recipe JSON file must exist"

    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as f:
            recipes = json.load(f)

        assert isinstance(recipes, list), f"{json_file} must contain a JSON array of recipe objects"

        for idx, recipe in enumerate(recipes):
            # 1. Validate top-level keys
            for key in required_top_keys:
                assert key in recipe and recipe[key], f"Recipe #{idx} in {json_file.name} missing or empty '{key}'"

            # 2. Validate provenance structure
            prov = recipe["provenance"]
            assert isinstance(prov, dict), f"Recipe #{idx} provenance must be a dict"
            for pkey in required_prov_keys:
                assert pkey in prov and prov[pkey], f"Recipe #{idx} provenance missing '{pkey}'"

            # 3. Validate source_url format
            url = prov["source_url"]
            parsed_url = urllib.parse.urlparse(url)
            assert parsed_url.scheme in ("http", "https") and parsed_url.netloc, f"Recipe #{idx} has invalid source_url: {url}"

            # 4. Validate Python AST Syntax
            code_str = recipe["code"]
            try:
                ast.parse(code_str)
            except SyntaxError as e:
                assert False, f"Recipe #{idx} has invalid Python syntax: {e}"

            # 5. Security & target checks
            assert "win32com" in code_str, f"Recipe #{idx} must target win32com"
            assert "c:\\users" not in code_str.lower(), f"Recipe #{idx} contains unsanitized user paths"

