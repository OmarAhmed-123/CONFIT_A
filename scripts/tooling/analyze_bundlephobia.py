#!/usr/bin/env python3
"""
Bundlephobia Analysis Script — Frontend Dependency Cost Analysis

Evaluates package size, dependency tree impact, and maintenance implications
before adding frontend dependencies to CONFIT.

Usage:
    python3 scripts/tooling/analyze_bundlephobia.py <package-name> [--compare <package2>]
    python3 scripts/tooling/analyze_bundlephobia.py --from-package-json frontend/package.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

BUNDLEPHOBIA_API = "https://bundlephobia.com/api/size"


@dataclass
class PackageAnalysis:
    name: str
    version: str
    gzip_size: int
    minified_size: int
    dependency_count: int
    dependency_names: list[str]
    has_types: bool
    repository_url: Optional[str]
    license: Optional[str]
    publish_date: Optional[str]


def fetch_package_info(package_spec: str) -> Optional[PackageAnalysis]:
    """Fetch package analysis from Bundlephobia API."""
    url = f"{BUNDLEPHOBIA_API}?package={package_spec}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CONFIT-Tooling/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
        
        return PackageAnalysis(
            name=data.get("name", package_spec),
            version=data.get("version", "unknown"),
            gzip_size=data.get("gzip", 0),
            minified_size=data.get("minified", 0),
            dependency_count=data.get("dependencyCount", 0),
            dependency_names=data.get("dependencies", []),
            has_types=data.get("hasTypes", False),
            repository_url=data.get("repository"),
            license=data.get("license"),
            publish_date=data.get("publishDate"),
        )
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Package not found: {package_spec}", file=sys.stderr)
        else:
            print(f"API error ({e.code}): {e.reason}", file=sys.stderr)
    except Exception as e:
        print(f"Error fetching {package_spec}: {e}", file=sys.stderr)
    return None


def format_size(bytes_: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB"]:
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} GB"


def print_analysis(analysis: PackageAnalysis) -> None:
    """Print formatted package analysis."""
    print(f"\n{'='*60}")
    print(f"Package: {analysis.name}@{analysis.version}")
    print(f"{'='*60}")
    print(f"  Minified size:  {format_size(analysis.minified_size)} ({analysis.minified_size:,} bytes)")
    print(f"  Gzipped size:   {format_size(analysis.gzip_size)} ({analysis.gzip_size:,} bytes)")
    print(f"  Dependencies:   {analysis.dependency_count}")
    print(f"  Has TypeScript: {'Yes' if analysis.has_types else 'No'}")
    print(f"  License:        {analysis.license or 'Unknown'}")
    print(f"  Repository:     {analysis.repository_url or 'Unknown'}")
    print(f"  Published:      {analysis.publish_date or 'Unknown'}")
    
    if analysis.dependency_names:
        print(f"\n  Direct dependencies:")
        for dep in analysis.dependency_names[:20]:
            print(f"    - {dep}")
        if len(analysis.dependency_names) > 20:
            print(f"    ... and {len(analysis.dependency_names) - 20} more")


def compare_packages(pkg1: PackageAnalysis, pkg2: PackageAnalysis) -> None:
    """Print comparison between two packages."""
    print(f"\n{'='*60}")
    print(f"COMPARISON: {pkg1.name} vs {pkg2.name}")
    print(f"{'='*60}")
    print(f"  Minified:  {format_size(pkg1.minified_size)} vs {format_size(pkg2.minified_size)} "
          f"({format_size(abs(pkg1.minified_size - pkg2.minified_size))} diff)")
    print(f"  Gzipped:   {format_size(pkg1.gzip_size)} vs {format_size(pkg2.gzip_size)} "
          f"({format_size(abs(pkg1.gzip_size - pkg2.gzip_size))} diff)")
    print(f"  Deps:      {pkg1.dependency_count} vs {pkg2.dependency_count}")
    print(f"  TS Types:  {'Yes' if pkg1.has_types else 'No'} vs {'Yes' if pkg2.has_types else 'No'}")


def analyze_from_package_json(package_json_path: Path) -> None:
    """Analyze all dependencies from package.json."""
    with open(package_json_path) as f:
        pkg = json.load(f)
    
    all_deps = {}
    all_deps.update(pkg.get("dependencies", {}))
    all_deps.update(pkg.get("devDependencies", {}))
    
    print(f"Analyzing {len(all_deps)} packages from {package_json_path}...")
    print("This may take a while (rate limited to ~1 req/sec)...\n")
    
    results = {}
    for name, version in all_deps.items():
        # Clean version specifier
        clean_version = version.lstrip("^~>=")
        spec = f"{name}@{clean_version}"
        print(f"  Fetching {spec}...", end=" ", flush=True)
        analysis = fetch_package_info(spec)
        if analysis:
            results[name] = analysis
            print(f"OK ({format_size(analysis.gzip_size)} gzipped)")
        else:
            print("FAILED")
        # Be nice to the API
        import time
        time.sleep(1.1)
    
    # Summary
    total_gzip = sum(a.gzip_size for a in results.values())
    total_minified = sum(a.minified_size for a in results.values())
    
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(results)} packages analyzed")
    print(f"{'='*60}")
    print(f"  Total minified: {format_size(total_minified)} ({total_minified:,} bytes)")
    print(f"  Total gzipped:  {format_size(total_gzip)} ({total_gzip:,} bytes)")
    
    # Top 10 by size
    sorted_by_gzip = sorted(results.values(), key=lambda x: x.gzip_size, reverse=True)
    print(f"\n  Top 10 by gzipped size:")
    for i, a in enumerate(sorted_by_gzip[:10], 1):
        pct = (a.gzip_size / total_gzip * 100) if total_gzip else 0
        print(f"    {i:2d}. {a.name:<30} {format_size(a.gzip_size):>8} ({pct:.1f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze npm package sizes via Bundlephobia",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/tooling/analyze_bundlephobia.py lodash
  python3 scripts/tooling/analyze_bundlephobia.py react@18.2.0 --compare preact@10.19.0
  python3 scripts/tooling/analyze_bundlephobia.py --from-package-json frontend/package.json
        """
    )
    parser.add_argument("package", nargs="?", help="Package name (e.g., lodash or lodash@4.17.21)")
    parser.add_argument("--compare", help="Package to compare against")
    parser.add_argument("--from-package-json", type=Path, help="Analyze all deps from package.json")
    
    args = parser.parse_args()
    
    if args.from_package_json:
        if not args.from_package_json.exists():
            print(f"File not found: {args.from_package_json}", file=sys.stderr)
            return 1
        analyze_from_package_json(args.from_package_json)
        return 0
    
    if not args.package:
        parser.print_help()
        return 1
    
    # Analyze primary package
    analysis = fetch_package_info(args.package)
    if not analysis:
        return 1
    
    print_analysis(analysis)
    
    # Compare if requested
    if args.compare:
        comparison = fetch_package_info(args.compare)
        if comparison:
            compare_packages(analysis, comparison)
        else:
            return 1
    
    # CONFIT-specific guidance
    print(f"\n{'='*60}")
    print("CONFIT GUIDANCE")
    print(f"{'='*60}")
    if analysis.gzip_size > 50 * 1024:  # > 50KB gzipped
        print("  WARNING: Package is LARGE (>50KB gzipped). Consider:")
        print("     - Lighter alternatives")
        print("     - Whether the functionality already exists in the repo")
        print("     - Tree-shaking effectiveness in Vite build")
    elif analysis.gzip_size > 10 * 1024:  # > 10KB gzipped
        print("  WARNING: Package is MODERATE (>10KB gzipped). Verify:")
        print("     - No existing utility provides the same functionality")
        print("     - Dependency tree doesn't pull in heavy sub-dependencies")
    else:
        print("  OK: Package size is reasonable for consideration")
    
    if analysis.dependency_count > 10:
        print(f"  WARNING: High dependency count ({analysis.dependency_count}). Audit transitive deps.")
    
    if not analysis.has_types and not analysis.name.startswith("@types/"):
        print("  WARNING: No TypeScript types. May need @types/ package or manual declarations.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())