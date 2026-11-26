#!/usr/bin/env python
"""
Command Line Interface for CATalyst.
Allows querying CATIA V5 interfaces and enums with Markdown output.
"""

import argparse
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.engine.db import CatalystDB
from src.engine.formatter import dump_compact_json, format_interface_card

def format_interface_markdown(data: dict) -> str:
    if "member_not_found" in data:
        return f"# {data['name']}\n> {data.get('message', 'Member not found.')}"

    md = []
    md.append(f"# {data['name']}")
    if data.get('framework'):
        md.append(f"**Framework**: `{data['framework']}`\n")
    
    if data.get('inheritance_chain'):
        chain_str = " -> ".join([f"`{c}`" for c in data['inheritance_chain']])
        md.append(f"**Inheritance**: {chain_str}\n")
        
    if data.get('description'):
        md.append(f"> {data['description']}\n")

    if data.get('navigation_path'):
        nav = data['navigation_path']
        md.append(f"**Navigation Path (`{nav['source']} -> {nav['target']}`)**: `{nav['python_chain']}`\n")
    
    if data.get('properties'):
        md.append("## Properties")
        md.append("| Name | Type | ReadOnly | Inherited From | Description |")
        md.append("|---|---|---|---|---|")
        for p in data['properties']:
            ro = "Yes" if p["readonly"] else "No"
            decl = p["declared_in"] if p["declared_in"] != data["name"] else "-"
            desc = (p.get("description") or "").replace("\n", " ")
            md.append(f"| `{p['name']}` | `{p['type']}` | {ro} | `{decl}` | {desc} |")
        md.append("\n")
            
    if data.get('methods'):
        md.append("## Methods")
        for m in data['methods']:
            params_str = ", ".join([f"{p['name']}: {p['type']}" for p in m["params"]])
            sig = f"{m['name']}({params_str}) -> {m['return_type']}"
            decl = f" *(Inherited from {m['declared_in']})*" if m['declared_in'] != data['name'] else ""
            md.append(f"### `{sig}`{decl}")
            if m.get("description"):
                md.append(f"> {m['description']}")
            if m.get("returns_desc"):
                md.append(f"> **Returns**: {m['returns_desc']}")
            if m.get("pitfall_warning"):
                pw = m["pitfall_warning"]
                md.append(f"> **[CAVEAT - {pw.get('severity', 'WARN')}]** {pw.get('summary', '')}")
                if pw.get("safe_pattern"):
                    md.append(f"> **Safe Pattern**: `{pw['safe_pattern']}`")
            if m.get("python_mapping"):
                py_map = m["python_mapping"]
                if "pywin32_call" in py_map:
                    md.append(f"> **Python (pywin32)**: `{py_map['pywin32_call']}`")
                if "out_parameters" in py_map:
                    md.append(f"> *{py_map['out_parameters']}*")
                if "safearray_note" in py_map:
                    md.append(f"> *{py_map['safearray_note']}*")
            md.append("")
        md.append("\n")
        
    if data.get('usecases'):
        md.append("## Examples")
        for uc in data['usecases']:
            md.append(f"**Context: {uc['context']}**")
            md.append("```vbscript")
            md.append(uc['code'])
            md.append("```\n")
            
    return "\n".join(md)

def format_enum_markdown(data: dict) -> str:
    md = []
    md.append(f"# {data['name']} (Enum)")
    if data.get('description'):
        md.append(f"> {data['description']}\n")

    if data.get('navigation_path'):
        nav = data['navigation_path']
        md.append(f"**Navigation Path (`{nav['source']} -> {nav['target']}`)**: `{nav['python_chain']}`\n")
    
    if data.get('matched_value'):
        mv = data['matched_value']
        md.append(f"**Matched Value**: `{mv['name']}` = `{mv['value']}`\n")
        if mv.get('description'):
            md.append(f"> {mv['description']}\n")
    
    md.append("## Values")
    md.append("| Value | Name | Description |")
    md.append("|---|---|---|")
    for v in data['values']:
        desc = (v.get('description') or '').replace('\n', ' ')
        val_int = v.get('value', '-')
        md.append(f"| `{val_int}` | `{v['name']}` | {desc} |")
        
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(description="CATalyst V5 Automation API CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    get_parser = subparsers.add_parser("get", help="Get full interface details or filter by specific member")
    get_parser.add_argument("name", type=str, help="Name of the interface (e.g., Pad, VisPropertySet)")
    get_parser.add_argument("--member", "-m", type=str, default=None, help="Filter to specific member(s) (exact, comma-list, or wildcard '*Fillet*')")
    get_parser.add_argument("--from", dest="from_interface", type=str, default=None, help="Compute shortest navigation path from root interface")
    get_parser.add_argument("--no-usecases", action="store_true", help="Omit code examples to save space")
    get_parser.add_argument("--detail", choices=["auto", "summary", "compact", "full"], default="auto", help="Output detail level")
    get_parser.add_argument("--format", "-f", dest="output_format", choices=["markdown", "card", "json"], default="markdown", help="Output format")
    get_parser.add_argument("--include-base", action="store_true", help="Include AnyObject/CATBaseDispatch boilerplate members")

    path_parser = subparsers.add_parser("path", help="Find shortest COM object navigation path between two interfaces")
    path_parser.add_argument("target", type=str, help="Target interface name (e.g., Material, Pad, RenderingMaterial)")
    path_parser.add_argument("--from", dest="from_interface", type=str, default="Application", help="Starting interface (default: Application)")
    
    usecase_parser = subparsers.add_parser("usecase", help="Get targeted examples for an interface (Official / Community)")
    usecase_parser.add_argument("interface", type=str, help="Name of the interface (e.g., Pad, Product, VisPropertySet)")
    usecase_parser.add_argument("--member", "-m", type=str, default=None, help="Specific method/property context")
    usecase_parser.add_argument("--source", "-s", choices=["all", "official", "community"], default="all", help="Filter by source")
    usecase_parser.add_argument("--query", "-q", type=str, default=None, help="Optional scenario keywords")
    usecase_parser.add_argument("--limit", "-l", type=int, default=5, help="Max examples to return")

    recipe_parser = subparsers.add_parser("recipe", help="Search community industrial recipes by scenario intent")
    recipe_parser.add_argument("query", type=str, help="Intent or scenario keywords (e.g., 'export step', 'bounding box')")
    recipe_parser.add_argument("--workbench", "-w", type=str, default=None, help="Workbench filter (e.g., PartDesign, Assembly, Drafting)")
    recipe_parser.add_argument("--source", "-s", choices=["all", "official", "community"], default="all", help="Source filter")
    recipe_parser.add_argument("--limit", "-l", type=int, default=5, help="Max recipes to return")

    syntax_parser = subparsers.add_parser("syntax", help="Get Selection.Search query syntax grammar")
    syntax_parser.add_argument("--workbench", "-w", type=str, default=None, help="Workbench (e.g., PartDesign, GSD, Drafting)")
    syntax_parser.add_argument("--type", "-t", type=str, default=None, help="Geometry type (e.g., Pad, Hole, Point)")

    search_parser = subparsers.add_parser("search", help="Search interfaces, enums, properties, and methods")
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument(
        "--type",
        "-t",
        choices=["all", "interface", "enum", "property", "method"],
        default="all",
        help="Filter results by item type",
    )
    search_parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=20,
        help="Max results to return",
    )

    enum_parser = subparsers.add_parser("enum", help="Get enum details or reverse lookup by value/member")
    enum_parser.add_argument("name", type=str, nargs="?", default="", help="Name of the enum or member (e.g., CatProductSource or catProductMade)")
    enum_parser.add_argument("--value", "-v", type=str, default=None, help="Numeric value / index to reverse lookup")
    enum_parser.add_argument("--member", "-m", type=str, default=None, help="Member name to reverse lookup")

    info_parser = subparsers.add_parser("info", help="Get diagnostic report of running CATIA instance")
    info_parser.add_argument("--clsid", type=str, default=None, help="Custom CLSID for ROT bridge connection")

    docs_parser = subparsers.add_parser("docs", help="Search offline CATIA V5 User's Guide and Options docs")
    docs_parser.add_argument("query", type=str, help="Search keywords")
    docs_parser.add_argument("--category", "-c", choices=["all", "user_guide", "options", "automation_doc"], default="all")
    docs_parser.add_argument("--module", "-m", type=str, default="", help="Module filter (e.g., cceug_C2)")
    docs_parser.add_argument("--solution", "-s", type=str, default="", help="Solution filter")
    docs_parser.add_argument("--limit", "-l", type=int, default=10)

    doc_page_parser = subparsers.add_parser("doc-page", help="Read a specific offline documentation page")
    doc_page_parser.add_argument("doc_id", type=str, help="Doc ID (e.g., cceug_C2/cceugbt0102.htm)")
    doc_page_parser.add_argument("--section", type=str, default="", help="Optional heading substring")
    doc_page_parser.add_argument("--max-chars", type=int, default=12000)

    settings_parser = subparsers.add_parser("settings", help="Search CATNls UI option keys and Tools>Options docs")
    settings_parser.add_argument("query", type=str, nargs="?", default="", help="UI wording or option key")
    settings_parser.add_argument("--nls-file", type=str, default="", help="CATNls file stem (e.g., CATCuiOptionEditor)")
    settings_parser.add_argument("--all", dest="all_entries", action="store_true", help="Do not restrict to option/LongHelp files")
    settings_parser.add_argument("--limit", "-l", type=int, default=15)

    samples_parser = subparsers.add_parser("samples", help="Search official CATIA V5 samples (text + binary CAD models)")
    samples_parser.add_argument("query", type=str, nargs="?", default="", help="Filename or content keywords")
    samples_parser.add_argument("--ext", type=str, default="", help="Extension filter (e.g., .csv, .catpart)")
    samples_parser.add_argument("--module", "-m", type=str, default="", help="Module filter")
    samples_parser.add_argument("--content", action="store_true", help="Print full text sample content")
    samples_parser.add_argument("--text-only", action="store_true", help="Exclude binary CAD/Excel samples")
    samples_parser.add_argument("--limit", "-l", type=int, default=10)

    args = parser.parse_args()

    if args.command in ("docs", "doc-page", "settings", "samples"):
        import json
        from src.engine.docs_db import CatalystDocsDB
        try:
            docs_db = CatalystDocsDB()
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)

        if args.command == "docs":
            print(json.dumps(
                docs_db.search_docs(args.query, category=args.category, module=args.module, solution=args.solution, limit=args.limit),
                indent=2, ensure_ascii=False
            ))
        elif args.command == "doc-page":
            res = docs_db.get_doc_page(args.doc_id, section=args.section, max_chars=args.max_chars)
            if not res:
                print(f"Documentation page '{args.doc_id}' not found.")
                sys.exit(1)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.command == "settings":
            print(json.dumps(
                docs_db.search_settings(args.query, nls_file=args.nls_file, options_only=not args.all_entries, limit=args.limit),
                indent=2, ensure_ascii=False
            ))
        elif args.command == "samples":
            print(json.dumps(
                docs_db.search_samples(
                    args.query,
                    ext=args.ext,
                    module=args.module,
                    include_content=args.content,
                    include_binary=not args.text_only,
                    limit=args.limit,
                ),
                indent=2, ensure_ascii=False
            ))
        return

    if args.command == "info":
        try:
            from src.client import CatiaClient
            client = CatiaClient(clsid=args.clsid)
            print(client.get_diagnostic_report())
        except Exception as e:
            print(f"Error connecting to CATIA: {e}")
            sys.exit(1)
        return

    try:
        db = CatalystDB()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.command == "get":
        eff_detail = "full" if args.output_format == "markdown" and args.detail == "auto" else args.detail
        res = db.get_interface(
            args.name,
            member_name=args.member,
            include_usecases=not args.no_usecases,
            detail=eff_detail,
            include_base_members=args.include_base or (args.output_format == "markdown"),
            inline_enums=True,
        )
        if res:
            if getattr(args, "from_interface", None) and "name" in res:
                nav = db.get_navigation_path(
                    res["name"],
                    from_interface=args.from_interface,
                    compact=(eff_detail != "full"),
                )
                if nav:
                    res["navigation_path"] = nav
            if args.output_format == "card":
                print(format_interface_card(res))
            elif args.output_format == "json":
                print(dump_compact_json(res))
            else:
                print(format_interface_markdown(res))
        else:
            print(f"Interface '{args.name}' not found.")
            sys.exit(1)

    elif args.command == "path":
        import json
        nav = db.get_navigation_path(args.target, from_interface=args.from_interface)
        if not nav:
            print(f"No COM navigation path found from '{args.from_interface}' to '{args.target}'.")
            sys.exit(1)
        print(json.dumps(nav, indent=2, ensure_ascii=False))

    elif args.command == "usecase":
        ucs = db.get_usecases(
            args.interface,
            member=args.member,
            source=args.source,
            query=args.query,
            limit=args.limit
        )
        if not ucs:
            print(f"No usecases found for '{args.interface}' (Source: {args.source}).")
            sys.exit(0)
        print(f"# Examples for `{args.interface}`" + (f" (Member: `{args.member}`)" if args.member else "") + "\n")
        for uc in ucs:
            source_tag = "[Official]" if uc.get("source") == "official" else "[Community Reference]"
            title_str = f" - {uc.get('title')}" if uc.get("title") else ""
            print(f"### {source_tag}{title_str}")
            if uc.get("workbench"):
                print(f"**Workbench**: `{uc['workbench']}`")
            if uc.get("provenance"):
                prov = uc['provenance']
                if isinstance(prov, dict):
                    src_ref = prov.get("source_ref") or prov.get("repo") or prov.get("community")
                    src_url = prov.get("source_url")
                    lic = prov.get("license", "MIT")
                    if src_ref:
                        ref_display = f"[{src_ref}]({src_url})" if src_url else f"`{src_ref}`"
                        print(f"**Provenance**: {ref_display} (License: `{lic}`)")
            if uc.get("context"):
                print(f"> {uc['context']}\n")
            lang = "python" if "win32com" in uc["code"] or "import " in uc["code"] else "vbscript"
            print(f"```{lang}")
            print(uc['code'])
            print("```\n")

    elif args.command == "recipe":
        recipes = db.search_recipes(
            query=args.query,
            workbench=args.workbench,
            source=args.source,
            limit=args.limit
        )
        if not recipes:
            print(f"No recipes found matching '{args.query}'.")
            sys.exit(0)
        print(f"# Practical Recipes matching `{args.query}`\n")
        for rc in recipes:
            source_tag = "[Official Tutorial]" if rc.get("source") == "official" else "[Community Recipe]"
            title = rc.get("title") or rc.get("context") or "Untitled Recipe"
            print(f"## {source_tag} {title}")
            print(f"- **Interface**: `{rc.get('interface', 'General')}`")
            if rc.get("workbench"):
                print(f"- **Workbench**: `{rc['workbench']}`")
            if rc.get("tags"):
                print(f"- **Tags**: `{rc['tags']}`")
            if rc.get("provenance"):
                prov = rc['provenance']
                if isinstance(prov, dict):
                    src_ref = prov.get("source_ref") or prov.get("repo") or prov.get("community")
                    src_url = prov.get("source_url")
                    lic = prov.get("license", "MIT")
                    if src_ref:
                        ref_display = f"[{src_ref}]({src_url})" if src_url else f"`{src_ref}`"
                        print(f"- **Provenance**: {ref_display} (License: `{lic}`)")
            if rc.get("context"):
                print(f"\n> {rc['context']}\n")
            lang = "python" if "win32com" in rc["code"] or "import " in rc["code"] else "vbscript"
            print(f"```{lang}")
            print(rc['code'])
            print("```\n")

    elif args.command == "syntax":
        import json
        syntax_data = db.get_search_syntax(workbench=args.workbench, query_type=args.type)
        print(json.dumps(syntax_data, indent=2, ensure_ascii=False))

    elif args.command == "enum":
        res = db.get_enum(name=args.name, value=args.value, member_name=args.member)
        if res:
            print(format_enum_markdown(res))
        else:
            query_str = args.name or args.member or f"value={args.value}"
            print(f"Enum '{query_str}' not found.")
            sys.exit(1)

    elif args.command == "search":
        results = db.search(args.query, item_type=args.type, limit=args.limit)
        member_lookup = None
        if args.type in ("all", "property", "method"):
            member_lookup = db.get_interfaces_by_member(args.query, member_type=args.type if args.type != "all" else None)

        if not results and (not member_lookup or member_lookup["total_host_interfaces"] == 0):
            print("No matches found.")
            sys.exit(0)

        if member_lookup and member_lookup["total_host_interfaces"] > 0:
            print(f"Member '{args.query}' is declared/hosted in {member_lookup['total_host_interfaces']} interfaces:")
            for host in member_lookup["host_interfaces"]:
                print(f"  * `{host}`")
            print()

        if results:
            print(f"Found {len(results)} matches:\n")
            for r in results:
                item_type = r["type"].upper()
                if item_type == "PROPERTY":
                    ro_tag = " [ReadOnly]" if r.get("readonly") else ""
                    type_tag = f" -> `{r['data_type']}`" if r.get("data_type") else ""
                    print(f"- [{item_type}] **{r['name']}**{type_tag}{ro_tag}")
                elif item_type == "METHOD":
                    ret_tag = f" -> `{r['data_type']}`" if r.get("data_type") else ""
                    print(f"- [{item_type}] **{r['name']}**{ret_tag}")
                elif item_type == "INTERFACE":
                    fw = f" (`{r.get('framework')}`)" if r.get("framework") else ""
                    print(f"- [{item_type}] **{r['name']}**{fw}")
                    if r.get("description"):
                        desc = r["description"].replace("\n", " ").strip()
                        if len(desc) > 100:
                            desc = desc[:100] + "..."
                        print(f"  > {desc}")
                elif item_type == "ENUM":
                    print(f"- [{item_type}] **{r['name']}**")
                    if r.get("description"):
                        desc = r["description"].replace("\n", " ").strip()
                        if len(desc) > 100:
                            desc = desc[:100] + "..."
                        print(f"  > {desc}")

if __name__ == "__main__":
    main()


