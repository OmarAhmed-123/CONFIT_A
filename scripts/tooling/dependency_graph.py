#!/usr/bin/env python3
"""
Dependency Graph Script — CodeGraphContext Integration for CONFIT

Analyzes repository relationships for:
- Dependency analysis
- Impact analysis (what changes affect what)
- Tracing frontend → API → service → database paths
- Locating duplicated logic
- Identifying affected code before modifications

Output: JSON graph for visualization, impact reports

Usage:
    python3 scripts/tooling/dependency_graph.py --output docs/architecture/dependency-graph.json
    python3 scripts/tooling/dependency_graph.py --impact backend/app/services/tryon_service.py
    python3 scripts/tooling/dependency_graph.py --trace frontend/src/services/apiServices.ts backend/app/controllers/tryon_controller.py
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories to analyze
SOURCE_DIRS = [
    REPO_ROOT / "backend" / "app",
    REPO_ROOT / "frontend" / "src",
    REPO_ROOT / "services" / "vton-worker",
    REPO_ROOT / "services" / "vlm-worker",
    REPO_ROOT / "api",
]

# Files/dirs to exclude
EXCLUDE_PATTERNS = [
    "__pycache__",
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "env",
    ".pytest_cache",
    "coverage",
    "htmlcov",
    ".mypy_cache",
    ".ruff_cache",
    "backend/data",
    "backend/alembic/versions",  # Migrations analyzed separately
    "vendor",
]


def should_exclude(path: Path) -> bool:
    """Check if path should be excluded."""
    parts = path.parts
    for pattern in EXCLUDE_PATTERNS:
        if pattern in parts:
            return True
        # Check if any parent matches
        for part in parts:
            if part == pattern or part.startswith(pattern + "."):
                return True
    return False


def get_python_files() -> list[Path]:
    """Get all Python files to analyze."""
    files = []
    for source_dir in SOURCE_DIRS:
        if source_dir.exists():
            for py_file in source_dir.rglob("*.py"):
                if not should_exclude(py_file):
                    files.append(py_file)
    return files


def get_typescript_files() -> list[Path]:
    """Get all TypeScript/TSX files to analyze."""
    files = []
    for source_dir in SOURCE_DIRS:
        if source_dir.exists():
            for ext in ("*.ts", "*.tsx"):
                for ts_file in source_dir.rglob(ext):
                    if not should_exclude(ts_file):
                        files.append(ts_file)
    return files


class PythonImportVisitor(ast.NodeVisitor):
    """AST visitor to extract imports from Python files."""
    
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.imports: list[dict[str, Any]] = []
        self.relative_to_repo = filepath.relative_to(REPO_ROOT)
    
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append({
                "type": "import",
                "module": alias.name,
                "alias": alias.asname,
                "line": node.lineno,
            })
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0:  # Absolute import
            module = node.module or ""
            for alias in node.names:
                self.imports.append({
                    "type": "from_import",
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname,
                    "line": node.lineno,
                })
        else:  # Relative import
            # Calculate absolute module path
            current_parts = self.relative_to_repo.with_suffix("").parts
            if node.level <= len(current_parts):
                base_parts = current_parts[:-node.level]
                module = ".".join(base_parts)
                if node.module:
                    module = module + "." + node.module if module else node.module
            else:
                module = ""
            
            for alias in node.names:
                self.imports.append({
                    "type": "relative_import",
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname,
                    "level": node.level,
                    "line": node.lineno,
                })
        self.generic_visit(node)


def analyze_python_file(filepath: Path) -> dict[str, Any]:
    """Analyze a single Python file for imports and structure."""
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(filepath))
    except Exception as e:
        return {
            "file": str(filepath.relative_to(REPO_ROOT)),
            "error": str(e),
            "imports": [],
            "classes": [],
            "functions": [],
        }
    
    visitor = PythonImportVisitor(filepath)
    visitor.visit(tree)
    
    # Extract classes and functions
    classes = []
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "bases": [ast.unparse(b) if hasattr(ast, 'unparse') else str(b) for b in node.bases],
            })
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
            })
    
    return {
        "file": str(filepath.relative_to(REPO_ROOT)),
        "language": "python",
        "imports": visitor.imports,
        "classes": classes,
        "functions": functions,
        "lines": len(content.splitlines()),
    }


def analyze_typescript_file(filepath: Path) -> dict[str, Any]:
    """Analyze a single TypeScript file for imports (basic regex-based)."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "file": str(filepath.relative_to(REPO_ROOT)),
            "error": str(e),
            "imports": [],
        }
    
    imports = []
    lines = content.splitlines()
    
    # Simple regex-based import extraction
    import_patterns = [
        # import ... from '...'
        r"^import\s+(?:\{[^}]*\}|\w+|\*\s+as\s+\w+)(?:\s*,\s*(?:\{[^}]*\}|\w+))*\s+from\s+['\"]([^'\"]+)['\"]",
        # import '...'
        r"^import\s+['\"]([^'\"]+)['\"]",
        # export ... from '...'
        r"^export\s+(?:\*\s+from\s+|.*\s+from\s+)['\"]([^'\"]+)['\"]",
        # require('...')
        r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
    ]
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        for pattern in import_patterns:
            import re
            matches = re.findall(pattern, stripped)
            for match in matches:
                imports.append({
                    "type": "import",
                    "module": match,
                    "line": i,
                })
    
    return {
        "file": str(filepath.relative_to(REPO_ROOT)),
        "language": "typescript",
        "imports": imports,
        "lines": len(lines),
    }


def build_dependency_graph() -> dict[str, Any]:
    """Build the complete dependency graph."""
    print("Analyzing Python files...")
    python_files = get_python_files()
    print(f"  Found {len(python_files)} Python files")
    
    print("Analyzing TypeScript files...")
    ts_files = get_typescript_files()
    print(f"  Found {len(ts_files)} TypeScript files")
    
    nodes = []
    edges = []
    
    # Build module -> file mapping for resolution
    # Use normalized paths (forward slashes) for consistency
    module_to_file = {}
    file_to_module = {}
    
    def normalize_path(path_str: str) -> str:
        """Normalize path to use forward slashes."""
        return path_str.replace("\\", "/")
    
    # Process Python files first to build mapping
    for filepath in python_files:
        analysis = analyze_python_file(filepath)
        nodes.append(analysis)
        
        # Map file to module name (use forward slashes)
        rel_path = filepath.relative_to(REPO_ROOT)
        normalized_file = normalize_path(str(rel_path))
        module_name = str(rel_path.with_suffix("")).replace("\\", "/").replace("/", ".")
        file_to_module[normalized_file] = module_name
        module_to_file[module_name] = normalized_file
    
    # Process TypeScript files
    for filepath in ts_files:
        analysis = analyze_typescript_file(filepath)
        nodes.append(analysis)
        
        # Map file to module name
        rel_path = filepath.relative_to(REPO_ROOT)
        normalized_file = normalize_path(str(rel_path))
        module_name = str(rel_path.with_suffix("")).replace("\\", "/").replace("/", ".")
        file_to_module[normalized_file] = module_name
        module_to_file[module_name] = normalized_file
    
    # Normalize all node file paths
    for node in nodes:
        node["file"] = normalize_path(node["file"])
    
    # Now create edges with proper resolution
    for node in nodes:
        filepath = node["file"]
        for imp in node.get("imports", []):
            module = imp.get("module", "")
            if not module:
                continue
            
            if not module.startswith("."):
                # Absolute import - could be external or internal
                # Check if it's an internal module
                if module in module_to_file:
                    edges.append({
                        "from": filepath,
                        "to": module_to_file[module],
                        "type": "internal",
                        "line": imp.get("line"),
                    })
                else:
                    # External dependency
                    prefix = "npm:" if node.get("language") == "typescript" else "pypi:"
                    edges.append({
                        "from": filepath,
                        "to": f"{prefix}{module}",
                        "type": "external",
                        "line": imp.get("line"),
                    })
            else:
                # Relative import - resolve to absolute module
                current_module = file_to_module.get(filepath, "")
                if current_module:
                    current_parts = current_module.split(".")
                    level = 0
                    while module.startswith("."):
                        module = module[1:]
                        level += 1
                    
                    if level <= len(current_parts):
                        base_parts = current_parts[:-level]
                        if module:
                            resolved_module = ".".join(base_parts + [module]) if base_parts else module
                        else:
                            resolved_module = ".".join(base_parts)
                        
                        if resolved_module in module_to_file:
                            edges.append({
                                "from": filepath,
                                "to": module_to_file[resolved_module],
                                "type": "internal",
                                "line": imp.get("line"),
                            })
                        else:
                            edges.append({
                                "from": filepath,
                                "to": f"unresolved:{resolved_module}",
                                "type": "unresolved",
                                "line": imp.get("line"),
                            })
    
    print(f"Total nodes: {len(nodes)}")
    print(f"Total edges: {len(edges)}")
    
    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_files": len(nodes),
            "python_files": len([n for n in nodes if n.get("language") == "python"]),
            "typescript_files": len([n for n in nodes if n.get("language") == "typescript"]),
            "total_edges": len(edges),
            "internal_edges": len([e for e in edges if e["type"] == "internal"]),
            "external_edges": len([e for e in edges if e["type"] == "external"]),
            "unresolved_edges": len([e for e in edges if e["type"] == "unresolved"]),
        },
    }


def find_impact(target_file: str) -> dict[str, Any]:
    """Find all files that depend on the target file (impact analysis)."""
    graph = build_dependency_graph()
    
    def normalize_path(path_str: str) -> str:
        return path_str.replace("\\", "/")
    
    # Normalize target to file path (WITH extension, matching graph format)
    target_path = normalize_path(target_file)
    # Ensure it's a relative path from repo root
    target_path = target_path.lstrip("/")
    
    # Find direct dependents
    direct_dependents = []
    for edge in graph["edges"]:
        if edge["to"] == target_path:
            direct_dependents.append(edge["from"])
    
    # Find transitive dependents (BFS)
    all_dependents = set(direct_dependents)
    queue = list(direct_dependents)
    
    while queue:
        current = queue.pop(0)
        for edge in graph["edges"]:
            if edge["from"] == current and edge["to"] not in all_dependents:
                all_dependents.add(edge["to"])
                queue.append(edge["to"])
    
    # Find what target depends on
    dependencies = []
    for edge in graph["edges"]:
        if edge["from"] == target_path:
            dependencies.append(edge["to"])
    
    return {
        "target": target_file,
        "direct_dependents": list(set(direct_dependents)),
        "all_dependents": list(all_dependents),
        "dependencies": dependencies,
        "impact_count": len(all_dependents),
    }


def trace_path(from_file: str, to_file: str) -> dict[str, Any]:
    """Trace dependency path from one file to another (BFS)."""
    graph = build_dependency_graph()
    
    def normalize_path(path_str: str) -> str:
        path_str = path_str.replace("\\", "/")
        return path_str.lstrip("/")
    
    from_path = normalize_path(from_file)
    to_path = normalize_path(to_file)
    
    # Build adjacency list
    adj = {}
    for edge in graph["edges"]:
        if edge["from"] not in adj:
            adj[edge["from"]] = []
        adj[edge["from"]].append(edge["to"])
    
    # BFS
    from collections import deque
    queue = deque([(from_path, [from_path])])
    visited = {from_path}
    
    while queue:
        current, path = queue.popleft()
        
        if current == to_path:
            return {
                "found": True,
                "path": path,
                "length": len(path) - 1,
            }
        
        for neighbor in adj.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    
    return {
        "found": False,
        "path": [],
        "length": 0,
    }


def find_duplicates() -> list[dict[str, Any]]:
    """Find potentially duplicated code (same function names in different files)."""
    graph = build_dependency_graph()
    
    # Group functions by name
    func_map = {}
    for node in graph["nodes"]:
        for func in node.get("functions", []):
            name = func["name"]
            if name not in func_map:
                func_map[name] = []
            func_map[name].append({
                "file": node["file"],
                "line": func["line"],
                "is_async": func.get("is_async", False),
            })
    
    # Find duplicates
    duplicates = []
    for name, locations in func_map.items():
        if len(locations) > 1:
            # Filter out common names (init, main, etc.)
            if name not in {"__init__", "main", "run", "execute", "process", "handle", "get", "set", "create", "update", "delete"}:
                duplicates.append({
                    "name": name,
                    "locations": locations,
                    "count": len(locations),
                })
    
    # Sort by count descending
    duplicates.sort(key=lambda x: x["count"], reverse=True)
    
    return duplicates[:50]  # Top 50


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CONFIT Dependency Graph Analysis (CodeGraphContext)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/tooling/dependency_graph.py --output docs/architecture/dependency-graph.json
  python3 scripts/tooling/dependency_graph.py --impact backend/app/services/tryon_service.py
  python3 scripts/tooling/dependency_graph.py --trace frontend/src/services/apiServices.ts backend/app/controllers/tryon_controller.py
  python3 scripts/tooling/dependency_graph.py --duplicates
        """
    )
    
    parser.add_argument("--output", "-o", type=Path, help="Output JSON file for full graph")
    parser.add_argument("--impact", type=str, help="Impact analysis for target file")
    parser.add_argument("--trace", nargs=2, metavar=("FROM", "TO"), help="Trace path between two files")
    parser.add_argument("--duplicates", action="store_true", help="Find potential code duplicates")
    
    args = parser.parse_args()
    
    if args.impact:
        print(f"Impact analysis for: {args.impact}")
        result = find_impact(args.impact)
        print(f"\nDirect dependents ({len(result['direct_dependents'])}):")
        for dep in sorted(result['direct_dependents']):
            print(f"  - {dep}")
        print(f"\nAll transitive dependents ({len(result['all_dependents'])}):")
        for dep in sorted(result['all_dependents']):
            print(f"  - {dep}")
        print(f"\nDependencies of target ({len(result['dependencies'])}):")
        for dep in sorted(result['dependencies']):
            print(f"  - {dep}")
        return 0
    
    if args.trace:
        from_file, to_file = args.trace
        print(f"Tracing path: {from_file} -> {to_file}")
        result = trace_path(from_file, to_file)
        if result["found"]:
            print(f"\nPath found ({result['length']} hops):")
            for i, step in enumerate(result["path"]):
                prefix = "  " * i
                arrow = " -> " if i > 0 else ""
                print(f"{prefix}{arrow}{step}")
        else:
            print("\nNo path found")
        return 0
    
    if args.duplicates:
        print("Finding potential code duplicates...")
        duplicates = find_duplicates()
        print(f"\nFound {len(duplicates)} potential duplicates:")
        for dup in duplicates:
            print(f"\n  {dup['name']} ({dup['count']} locations):")
            for loc in dup['locations']:
                print(f"    - {loc['file']}:{loc['line']} {'(async)' if loc['is_async'] else ''}")
        return 0
    
    # Full graph
    print("Building dependency graph...")
    graph = build_dependency_graph()
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(graph, indent=2))
        print(f"Graph written to {args.output}")
    else:
        print(json.dumps(graph, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())