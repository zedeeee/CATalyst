---
name: catalyst-query
description: Queries the local CATalyst V5 Automation API database to retrieve precise interfaces, methods, properties, enums, and usecases. Use this whenever generating CATIA V5 macros or Python automation scripts to prevent hallucinations.
---

# CATalyst V5 API Query Skill

This skill allows you to retrieve exact COM signatures and inherited properties for CATIA V5 Automation.

## When to use this skill
- Whenever a user asks you to write a CATIA V5 macro, script, or plugin.
- When you are unsure about the exact spelling of a CATIA interface, property, or method.
- When you need to see how a specific CATIA interface is used in official VBScript examples.

## Prerequisites
The user must have compiled the CATalyst database locally. If the database is missing, instruct the user to run `uv run build.py` at the root of the CATalyst repository.

## Instructions

1. Use your `run_command` tool to execute queries against the CATalyst CLI.
2. The CLI is located at `catalyst_cli.py` in the CATalyst repository root. You can run it via `uv run python catalyst_cli.py <command> <args>`.

### Available Commands

**1. Search for APIs:**
If you don't know the exact interface name, search for it first:
```bash
uv run python catalyst_cli.py search "fillet"
```
This returns a list of matches (interfaces and enums).

**2. Get Interface Signatures:**
Once you know the exact interface name (e.g., `Pad`), retrieve its full definition:
```bash
uv run python catalyst_cli.py get Pad
```
This returns a comprehensive Markdown document containing:
- All properties and methods (including those inherited from parent classes like `Prism` or `Shape`).
- The expected types for all parameters and return values.
- Official VBScript examples showing how to instantiate or manipulate the interface.

**3. Get Enumeration Values:**
If you need the exact integer or constant names for an enum (e.g., `CatHoleType`):
```bash
uv run python catalyst_cli.py enum CatHoleType
```

## Rules for CATIA V5 Automation Generation
- **Never Guess**: Do not invent properties or methods. If you cannot find the API via this skill, inform the user that it might not be exposed to Automation or you need a different keyword.
- **Respect Inheritance**: The `get` command automatically merges inherited properties. You can safely call any method listed under "Methods", even if the "Inherited From" column shows it belongs to a parent class.
- **Type Checking**: Pay attention to the expected types (e.g., `CATBSTR` is a string, `CATSafeArrayVariant` is usually a tuple/list in Python or Array in VBS).
