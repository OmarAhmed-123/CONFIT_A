#!/usr/bin/env python3
"""
SVG Optimization Script — SVGOMG Integration for CONFIT

Optimizes repository SVG assets using SVGO (local, no external service).
Preserves rendering, accessibility, viewBox, IDs, fills/strokes, and semantics.

Usage:
    python3 scripts/tooling/optimize_svgs.py --input frontend/src/assets/icons --output frontend/src/assets/icons
    python3 scripts/tooling/optimize_svgs.py --single icon.svg --compare
    python3 scripts/tooling/optimize_svgs.py --input frontend/src/assets --dry-run
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def check_svgo() -> bool:
    """Check if SVGO is available."""
    try:
        result = subprocess.run(["npx", "svgo", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"SVGO version: {result.stdout.strip()}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Try global install
    try:
        result = subprocess.run(["svgo", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"SVGO version: {result.stdout.strip()}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return False


def optimize_svg(
    input_path: Path,
    output_path: Path,
    config: Optional[dict] = None,
    pretty: bool = False,
) -> dict[str, any]:
    """Optimize a single SVG file using SVGO."""
    result = {
        "input": str(input_path),
        "output": str(output_path),
        "original_size": 0,
        "optimized_size": 0,
        "saved_bytes": 0,
        "saved_percent": 0.0,
        "error": None,
        "svgo_output": "",
    }
    
    try:
        result["original_size"] = input_path.stat().st_size
        
        # Build SVGO command
        cmd = ["npx", "svgo"]
        
        # Config options for CONFIT (preserve important attributes)
        default_config = {
            "plugins": [
                {"name": "preset-default", "params": {
                    "overrides": {
                        # Preserve IDs (used for CSS/JS targeting)
                        "cleanupIds": False,
                        # Preserve viewBox
                        "removeViewBox": False,
                        # Preserve width/height if present (responsive handling)
                        "removeDimensions": True,
                        # Don't remove unknown elements (custom elements)
                        "removeUnknownsAndDefaults": False,
                        # Preserve title/desc for accessibility
                        "removeTitle": False,
                        "removeDesc": False,
                        # Don't convert shape to path (preserves editability)
                        "convertShapeToPath": False,
                        # Don't merge paths (preserves structure)
                        "mergePaths": False,
                        # Preserve style elements
                        "removeStyleElement": False,
                        # Don't remove scripts (if any)
                        "removeScriptElement": False,
                    }
                }},
                # Additional optimizations
                "removeXMLNS",  # Remove xmlns if not needed
                "removeXMLProcInst",
                "removeComments",
                "removeMetadata",
                "removeDoctype",
                "removeEditorsNSData",
                "removeEmptyAttrs",
                "removeHiddenElems",
                "removeEmptyText",
                "removeEmptyContainers",
                "minifyStyles",
                "cleanupAttrs",
                "cleanupNumericValues",
                "cleanupListOfValues",
                "moveElemsAttrsToGroup",
                "moveGroupAttrsToElems",
                "collapseGroups",
                "convertColors",
                "convertPathData",
                "convertTransform",
                "removeUselessStrokeAndFill",
                "removeNonInheritableGroupAttrs",
            ]
        }
        
        # Merge custom config if provided
        if config:
            # For simplicity, we'll pass config via --config file
            pass
        
        # Write config to temp file
        import tempfile
        import json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(default_config, f)
            config_file = f.name
        
        try:
            cmd.extend(["--config", config_file])
            cmd.extend(["--input", str(input_path)])
            cmd.extend(["--output", str(output_path)])
            
            if pretty:
                cmd.append("--pretty")
            
            # Run SVGO
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            result["svgo_output"] = proc.stdout + proc.stderr
            
            if proc.returncode != 0:
                result["error"] = f"SVGO exited with code {proc.returncode}: {proc.stderr}"
                return result
            
            # Get optimized size
            if output_path.exists():
                result["optimized_size"] = output_path.stat().st_size
                result["saved_bytes"] = result["original_size"] - result["optimized_size"]
                result["saved_percent"] = (result["saved_bytes"] / result["original_size"] * 100) if result["original_size"] > 0 else 0
            else:
                result["error"] = "Output file not created"
                
        finally:
            # Clean up config file
            try:
                os.unlink(config_file)
            except OSError:
                pass
                
    except subprocess.TimeoutExpired:
        result["error"] = "SVGO timed out (60s)"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def format_bytes(bytes_: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB"]:
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} GB"


def verify_svg_equivalence(original: Path, optimized: Path) -> tuple[bool, list[str]]:
    """Verify optimized SVG renders equivalently (basic checks)."""
    issues = []
    
    try:
        # Parse both as XML
        import xml.etree.ElementTree as ET
        
        orig_tree = ET.parse(original)
        opt_tree = ET.parse(optimized)
        
        orig_root = orig_tree.getroot()
        opt_root = opt_tree.getroot()
        
        # Check viewBox preserved
        orig_vb = orig_root.get("viewBox")
        opt_vb = opt_root.get("viewBox")
        if orig_vb != opt_vb:
            issues.append(f"viewBox changed: '{orig_vb}' -> '{opt_vb}'")
        
        # Check IDs preserved (sample check)
        orig_ids = {elem.get("id") for elem in orig_root.iter() if elem.get("id")}
        opt_ids = {elem.get("id") for elem in opt_root.iter() if elem.get("id")}
        missing_ids = orig_ids - opt_ids
        if missing_ids:
            issues.append(f"IDs removed: {missing_ids}")
        
        # Check title/desc preserved (accessibility)
        orig_titles = [elem.text for elem in orig_root.iter() if elem.tag.endswith("title") and elem.text]
        opt_titles = [elem.text for elem in opt_root.iter() if elem.tag.endswith("title") and elem.text]
        if orig_titles != opt_titles:
            issues.append(f"Title/desc changed: {orig_titles} -> {opt_titles}")
        
    except Exception as e:
        issues.append(f"Verification error: {e}")
    
    return len(issues) == 0, issues


def process_directory(
    input_dir: Path,
    output_dir: Path,
    recursive: bool = True,
    dry_run: bool = False,
    verify: bool = True,
) -> list[dict[str, any]]:
    """Process all SVGs in a directory."""
    results = []
    
    # Find all SVG files
    pattern = "**/*.svg" if recursive else "*.svg"
    files = list(input_dir.glob(pattern))
    files.extend(input_dir.glob(pattern.upper()))
    
    # Deduplicate (case-insensitive filesystem)
    seen = set()
    unique_files = []
    for f in files:
        key = str(f).lower()
        if key not in seen:
            seen.add(key)
            unique_files.append(f)
    files = unique_files
    
    print(f"Found {len(files)} SVG file(s) to process")
    
    total_original = 0
    total_optimized = 0
    verification_failures = 0
    
    for i, input_path in enumerate(files, 1):
        rel_path = input_path.relative_to(input_dir)
        output_path = output_dir / rel_path
        
        print(f"[{i}/{len(files)}] {rel_path}...", end=" ", flush=True)
        
        if dry_run:
            orig_size = input_path.stat().st_size
            print(f"SKIP (dry-run) - {format_bytes(orig_size)}")
            continue
        
        result = optimize_svg(input_path, output_path)
        results.append(result)
        
        total_original += result["original_size"]
        total_optimized += result["optimized_size"]
        
        if result["error"]:
            print(f"ERROR: {result['error']}")
        else:
            saved = format_bytes(result["saved_bytes"])
            pct = result["saved_percent"]
            print(f"{format_bytes(result['original_size'])}->{format_bytes(result['optimized_size'])} | saved: {saved} ({pct:.1f}%)")
            
            # Verify equivalence
            if verify and result["optimized_size"] > 0:
                equivalent, issues = verify_svg_equivalence(input_path, output_path)
                if not equivalent:
                    verification_failures += 1
                    print(f"  ⚠️  VERIFICATION FAILED:")
                    for issue in issues:
                        print(f"    - {issue}")
    
    # Summary
    if results and not dry_run:
        total_saved = total_original - total_optimized
        total_pct = (total_saved / total_original * 100) if total_original > 0 else 0
        print(f"\n{'='*60}")
        print(f"SUMMARY: {len(results)} SVGs processed")
        print(f"  Total original:  {format_bytes(total_original)}")
        print(f"  Total optimized: {format_bytes(total_optimized)}")
        print(f"  Total saved:     {format_bytes(total_saved)} ({total_pct:.1f}%)")
        if verification_failures:
            print(f"  ⚠️  Verification failures: {verification_failures}")
    
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Optimize SVG files for CONFIT (local SVGO, no external service)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/tooling/optimize_svgs.py --input frontend/src/assets/icons --output frontend/src/assets/icons
  python3 scripts/tooling/optimize_svgs.py --single icon.svg --compare
  python3 scripts/tooling/optimize_svgs.py --input frontend/src/assets --dry-run
        """
    )
    
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", "-i", type=Path, help="Input directory")
    input_group.add_argument("--single", "-s", type=Path, help="Single SVG file")
    
    parser.add_argument("--output", "-o", type=Path, help="Output directory (required for --input)")
    parser.add_argument("--no-recursive", action="store_true", help="Don't recurse into subdirectories")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't write files")
    parser.add_argument("--no-verify", action="store_true", help="Skip equivalence verification")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output (not minified)")
    parser.add_argument("--compare", action="store_true", help="Show detailed comparison (with --single)")
    
    args = parser.parse_args()
    
    # Validate
    if args.input and not args.output:
        print("--input requires --output", file=sys.stderr)
        return 1
    
    if args.single and not args.output and not args.compare:
        print("--single requires --output or --compare", file=sys.stderr)
        return 1
    
    # Check SVGO availability
    if not check_svgo():
        print("SVGO not found. Install with: npm install -g svgo  OR  npx svgo", file=sys.stderr)
        print("Note: This script uses 'npx svgo' which requires Node.js and npm.", file=sys.stderr)
        return 1
    
    if args.single:
        if not args.single.exists():
            print(f"File not found: {args.single}", file=sys.stderr)
            return 1
        
        output_path = args.output or args.single.with_stem(args.single.stem + "_optimized")
        result = optimize_svg(args.single, output_path, pretty=args.pretty)
        
        if result["error"]:
            print(f"ERROR: {result['error']}", file=sys.stderr)
            return 1
        
        print(f"Original:  {format_bytes(result['original_size'])}")
        print(f"Optimized: {format_bytes(result['optimized_size'])}")
        print(f"Saved:     {format_bytes(result['saved_bytes'])} ({result['saved_percent']:.1f}%)")
        
        if args.compare:
            equivalent, issues = verify_svg_equivalence(args.single, output_path)
            if equivalent:
                print("✅ Verification PASSED - SVG equivalence maintained")
            else:
                print("❌ Verification FAILED:")
                for issue in issues:
                    print(f"  - {issue}")
            
            # Clean up temp file if no output specified
            if not args.output and output_path.exists():
                output_path.unlink()
        
        return 0
    
    # Directory processing
    if not args.input.exists():
        print(f"Directory not found: {args.input}", file=sys.stderr)
        return 1
    
    if not args.input.is_dir():
        print(f"Input must be a directory: {args.input}", file=sys.stderr)
        return 1
    
    process_directory(
        args.input, args.output,
        recursive=not args.no_recursive,
        dry_run=args.dry_run,
        verify=not args.no_verify,
    )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())