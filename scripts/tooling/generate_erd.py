#!/usr/bin/env python3
"""
ERD Generation Script — Generate drawDB-compatible ERD from SQLAlchemy models

Generates Entity Relationship Diagrams for CONFIT database schema understanding,
ERD review, tenant boundary review, and documentation.

Output formats:
- drawDB-compatible JSON (for import into drawdb.app)
- Mermaid ERD (for version-controlled documentation)
- PlantUML (alternative)

Usage:
    python3 scripts/tooling/generate_erd.py --output docs/architecture/erd.drawio.json
    python3 scripts/tooling/generate_erd.py --format mermaid --output docs/architecture/erd.mmd
    python3 scripts/tooling/generate_erd.py --format plantuml --output docs/architecture/erd.puml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import inspect
from backend.app.core.database import Base
import backend.app.models  # noqa: F401 - registers all mappers


def get_table_info() -> list[dict[str, Any]]:
    """Extract table and column information from SQLAlchemy metadata."""
    tables = []
    
    for table_name, table in sorted(Base.metadata.tables.items()):
        if table_name == "alembic_version":
            continue
            
        columns = []
        for col in table.columns:
            col_info = {
                "name": col.name,
                "type": str(col.type),
                "nullable": col.nullable,
                "primary_key": col.primary_key,
                "default": str(col.default.arg) if col.default and col.default.arg is not None else None,
                "autoincrement": col.autoincrement,
                "comment": col.comment,
            }
            # Add foreign key info
            fks = []
            for fk in col.foreign_keys:
                fks.append({
                    "column": col.name,
                    "referenced_table": fk.column.table.name,
                    "referenced_column": fk.column.name,
                })
            if fks:
                col_info["foreign_keys"] = fks
            columns.append(col_info)
        
        # Table-level info
        table_info = {
            "name": table_name,
            "columns": columns,
            "comment": table.comment,
        }
        tables.append(table_info)
    
    return tables


def generate_drawdb_json(tables: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate drawDB-compatible JSON schema."""
    # drawDB format (simplified)
    return {
        "version": 1,
        "tables": [
            {
                "name": t["name"],
                "columns": [
                    {
                        "name": c["name"],
                        "type": c["type"],
                        "primaryKey": c["primary_key"],
                        "notNull": not c["nullable"],
                        "autoIncrement": c["autoincrement"],
                        "default": c["default"],
                        "comment": c["comment"],
                        "foreignKeys": c.get("foreign_keys", []),
                    }
                    for c in t["columns"]
                ],
                "comment": t["comment"],
            }
            for t in tables
        ],
        "relationships": [],
    }


def generate_mermaid_erd(tables: list[dict[str, Any]]) -> str:
    """Generate Mermaid ER diagram."""
    lines = ["erDiagram"]
    
    # Entities
    for table in tables:
        lines.append(f"    {table['name']} {{")
        for col in table["columns"]:
            pk = "PK" if col["primary_key"] else ""
            fk = "FK" if col.get("foreign_keys") else ""
            nullable = "" if not col["nullable"] else "NULL"
            tags = " ".join(filter(None, [pk, fk, nullable]))
            tag_str = f" {tags}" if tags else ""
            lines.append(f"        {col['type']} {col['name']}{tag_str}")
        lines.append("    }")
    
    # Relationships
    for table in tables:
        for col in table["columns"]:
            for fk in col.get("foreign_keys", []):
                lines.append(f"    {table['name']} ||--o{{ {fk['referenced_table']} : \"{fk['column']}\"")
    
    return "\n".join(lines)


def generate_plantuml_erd(tables: list[dict[str, Any]]) -> str:
    """Generate PlantUML ER diagram."""
    lines = [
        "@startuml",
        "hide circle",
        "skinparam linetype ortho",
        "",
    ]
    
    for table in tables:
        lines.append(f"entity \"{table['name']}\" {{")
        for col in table["columns"]:
            pk = "<<PK>>" if col["primary_key"] else ""
            fk = "<<FK>>" if col.get("foreign_keys") else ""
            not_null = "NOT NULL" if not col["nullable"] else ""
            parts = [col["type"], col["name"], pk, fk, not_null]
            lines.append(f"  + {' '.join(filter(None, parts))}")
        lines.append("}")
        lines.append("")
    
    # Relationships
    for table in tables:
        for col in table["columns"]:
            for fk in col.get("foreign_keys", []):
                lines.append(f"\"{table['name']}\" ||--o{{ \"{fk['referenced_table']}\"")
    
    lines.append("@enduml")
    return "\n".join(lines)


def generate_markdown_summary(tables: list[dict[str, Any]]) -> str:
    """Generate human-readable markdown summary."""
    lines = [
        "# CONFIT Database Schema (ERD)",
        "",
        f"Generated from SQLAlchemy models. **{len(tables)} tables**.",
        "",
        "## Tables",
        "",
    ]
    
    for table in tables:
        lines.append(f"### `{table['name']}`")
        if table["comment"]:
            lines.append(f"> {table['comment']}")
        lines.append("")
        lines.append("| Column | Type | PK | FK | Nullable | Default |")
        lines.append("|--------|------|----|----|----------|---------|")
        for col in table["columns"]:
            pk = "✓" if col["primary_key"] else ""
            fk = "✓" if col.get("foreign_keys") else ""
            nullable = "YES" if col["nullable"] else "NO"
            default = col["default"] or ""
            lines.append(f"| {col['name']} | {col['type']} | {pk} | {fk} | {nullable} | {default} |")
        lines.append("")
    
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate ERD from SQLAlchemy models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/tooling/generate_erd.py --output docs/architecture/erd.drawio.json
  python3 scripts/tooling/generate_erd.py --format mermaid --output docs/architecture/erd.mmd
  python3 scripts/tooling/generate_erd.py --format markdown --output docs/architecture/erd.md
        """
    )
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output file path")
    parser.add_argument("--format", "-f", choices=["drawdb", "mermaid", "plantuml", "markdown"], 
                        default="drawdb", help="Output format")
    
    args = parser.parse_args()
    
    print("Loading SQLAlchemy metadata...")
    tables = get_table_info()
    print(f"Found {len(tables)} tables")
    
    # Generate output
    if args.format == "drawdb":
        content = json.dumps(generate_drawdb_json(tables), indent=2)
    elif args.format == "mermaid":
        content = generate_mermaid_erd(tables)
    elif args.format == "plantuml":
        content = generate_plantuml_erd(tables)
    elif args.format == "markdown":
        content = generate_markdown_summary(tables)
    else:
        print(f"Unknown format: {args.format}", file=sys.stderr)
        return 1
    
    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Written to {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())