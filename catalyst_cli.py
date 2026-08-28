#!/usr/bin/env python
"""
Command Line Interface for CATalyst.
Allows querying CATIA V5 interfaces and enums with Markdown output.
"""

import argparse
import sys
from src.engine.db import CatalystDB

def format_interface_markdown(data: dict) -> str:
    md = []
    md.append(f"# {data['name']}")
    md.append(f"**Framework**: `{data['framework']}`\n")
    
    if data.get('inheritance_chain'):
        chain_str = " -> ".join([f"`{c}`" for c in data['inheritance_chain']])
        md.append(f"**Inheritance**: {chain_str}\n")
        
    md.append(f"> {data['description']}\n")
    
    if data['properties']:
        md.append("## Properties")
        md.append("| Name | Type | ReadOnly | Inherited From |")
        md.append("|---|---|---|---|")
        for p in data['properties']:
            ro = "Yes" if p["readonly"] else "No"
            decl = p["declared_in"] if p["declared_in"] != data["name"] else "-"
            md.append(f"| `{p['name']}` | `{p['type']}` | {ro} | `{decl}` |")
        md.append("\n")
            
    if data['methods']:
        md.append("## Methods")
        for m in data['methods']:
            params_str = ", ".join([f"{p['name']}: {p['type']}" for p in m["params"]])
            sig = f"{m['name']}({params_str}) -> {m['return_type']}"
            decl = f" *(Inherited from {m['declared_in']})*" if m['declared_in'] != data['name'] else ""
            md.append(f"### `{sig}`{decl}")
        md.append("\n")
        
    if data['usecases']:
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
    md.append(f"> {data['description']}\n")
    
    md.append("## Values")
    md.append("| Name | Description |")
    md.append("|---|---|")
    for v in data['values']:
        desc = v['description'].replace('\n', ' ')
        md.append(f"| `{v['name']}` | {desc} |")
        
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(description="CATalyst V5 Automation API CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    get_parser = subparsers.add_parser("get", help="Get full interface details")
    get_parser.add_argument("name", type=str, help="Name of the interface (e.g., Pad)")
    
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

    enum_parser = subparsers.add_parser("enum", help="Get enum details")
    enum_parser.add_argument("name", type=str, help="Name of the enum (e.g., CatHoleType)")

    info_parser = subparsers.add_parser("info", help="Get diagnostic report of running CATIA instance")
    info_parser.add_argument("--clsid", type=str, default=None, help="Custom CLSID for ROT bridge connection")

    args = parser.parse_args()

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
        res = db.get_interface(args.name)
        if res:
            print(format_interface_markdown(res))
        else:
            print(f"Interface '{args.name}' not found.")
            sys.exit(1)

    elif args.command == "enum":
        res = db.get_enum(args.name)
        if res:
            print(format_enum_markdown(res))
        else:
            print(f"Enum '{args.name}' not found.")
            sys.exit(1)

    elif args.command == "search":
        results = db.search(args.query, item_type=args.type, limit=args.limit)
        if not results:
            print("No matches found.")
            sys.exit(0)

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
