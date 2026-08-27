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
    
    search_parser = subparsers.add_parser("search", help="Search interfaces and enums")
    search_parser.add_argument("query", type=str, help="Search query")
    
    enum_parser = subparsers.add_parser("enum", help="Get enum details")
    enum_parser.add_argument("name", type=str, help="Name of the enum (e.g., CatHoleType)")
    
    args = parser.parse_args()
    
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
        results = db.search(args.query)
        if not results:
            print("No matches found.")
            sys.exit(0)
            
        print(f"Found {len(results)} matches:\n")
        for r in results:
            print(f"- [{r['type'].upper()}] **{r['name']}**")
            if r['description']:
                desc = r['description'].replace('\n', ' ')[:100]
                print(f"  > {desc}...")

if __name__ == "__main__":
    main()
