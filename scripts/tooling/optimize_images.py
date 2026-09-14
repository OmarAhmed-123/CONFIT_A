#!/usr/bin/env python3
"""
Image Optimization Script — Tiny Image Integration for CONFIT

Optimizes catalog images, thumbnails, marketing imagery, and static assets.
Uses Pillow for local processing (no external service for production images).

Features:
- Lossless optimization for PNG
- Quality-controlled JPEG/WebP compression
- Resize to max dimensions
- Format conversion (to WebP for web delivery)
- Before/after size comparison

Usage:
    python3 scripts/tooling/optimize_images.py --input frontend/public/images --output frontend/public/images/optimized
    python3 scripts/tooling/optimize_images.py --input uploads/catalog --max-width 1920 --quality 85 --format webp
    python3 scripts/tooling/optimize_images.py --single image.jpg --compare
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except ImportError:
    print("Pillow not installed. Install with: pip install Pillow", file=sys.stderr)
    sys.exit(1)


SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
OUTPUT_FORMATS = {"jpeg", "png", "webp"}


def optimize_image(
    input_path: Path,
    output_path: Path,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    quality: int = 85,
    output_format: Optional[str] = None,
    lossless: bool = False,
) -> dict[str, Any]:
    """Optimize a single image file."""
    result = {
        "input": str(input_path),
        "output": str(output_path),
        "original_size": 0,
        "optimized_size": 0,
        "original_dimensions": (0, 0),
        "optimized_dimensions": (0, 0),
        "format": "",
        "saved_bytes": 0,
        "saved_percent": 0.0,
        "error": None,
    }
    
    try:
        # Get original size
        result["original_size"] = input_path.stat().st_size
        
        with Image.open(input_path) as img:
            # Handle EXIF orientation
            img = ImageOps.exif_transpose(img) if hasattr(ImageOps, 'exif_transpose') else img
            
            result["original_dimensions"] = img.size
            original_mode = img.mode
            
            # Convert to RGB if necessary (for JPEG/WebP)
            if output_format in ("jpeg", "jpg", "webp") and img.mode in ("RGBA", "LA", "P"):
                # Create white background for transparency
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                if img.mode in ("RGBA", "LA"):
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert("RGB")
            elif img.mode == "P":
                img = img.convert("RGBA")
            
            # Resize if needed
            if max_width or max_height:
                img.thumbnail((max_width or img.width, max_height or img.height), Image.Resampling.LANCZOS)
            
            result["optimized_dimensions"] = img.size
            
            # Determine output format
            if output_format:
                fmt = output_format.lower()
                if fmt == "jpg":
                    fmt = "jpeg"
            else:
                # Keep original format, but prefer WebP for web
                suffix = input_path.suffix.lower()
                if suffix in (".jpg", ".jpeg"):
                    fmt = "jpeg"
                elif suffix == ".png":
                    fmt = "png"
                elif suffix == ".webp":
                    fmt = "webp"
                else:
                    fmt = "webp"  # Default to WebP for unknown formats
            
            result["format"] = fmt
            
            # Save optimized
            save_kwargs = {"optimize": True}
            if fmt == "jpeg":
                save_kwargs["quality"] = quality
                save_kwargs["progressive"] = True
            elif fmt == "webp":
                save_kwargs["quality"] = quality
                save_kwargs["method"] = 6  # Best compression
                save_kwargs["lossless"] = lossless
            elif fmt == "png":
                save_kwargs["compress_level"] = 9
                save_kwargs["optimize"] = True
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            img.save(output_path, format=fmt.upper(), **save_kwargs)
            
            # Get optimized size
            result["optimized_size"] = output_path.stat().st_size
            result["saved_bytes"] = result["original_size"] - result["optimized_size"]
            result["saved_percent"] = (result["saved_bytes"] / result["original_size"] * 100) if result["original_size"] > 0 else 0
            
    except Exception as e:
        result["error"] = str(e)
    
    return result


def format_bytes(bytes_: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} TB"


def process_directory(
    input_dir: Path,
    output_dir: Path,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    quality: int = 85,
    output_format: Optional[str] = None,
    lossless: bool = False,
    recursive: bool = True,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Process all images in a directory."""
    results = []
    
    # Find all image files
    pattern = "**/*" if recursive else "*"
    files = []
    for ext in SUPPORTED_FORMATS:
        files.extend(input_dir.glob(f"{pattern}{ext}"))
        files.extend(input_dir.glob(f"{pattern}{ext.upper()}"))
    
    print(f"Found {len(files)} image(s) to process")
    
    total_original = 0
    total_optimized = 0
    
    for i, input_path in enumerate(files, 1):
        # Determine output path
        rel_path = input_path.relative_to(input_dir)
        if output_format:
            rel_path = rel_path.with_suffix(f".{output_format.lower()}")
        output_path = output_dir / rel_path
        
        print(f"[{i}/{len(files)}] {rel_path}...", end=" ", flush=True)
        
        if dry_run:
            # Just analyze
            with Image.open(input_path) as img:
                orig_size = input_path.stat().st_size
                print(f"SKIP (dry-run) - {img.size} - {format_bytes(orig_size)}")
            continue
        
        result = optimize_image(
            input_path, output_path,
            max_width=max_width,
            max_height=max_height,
            quality=quality,
            output_format=output_format,
            lossless=lossless,
        )
        results.append(result)
        
        total_original += result["original_size"]
        total_optimized += result["optimized_size"]
        
        if result["error"]:
            print(f"ERROR: {result['error']}")
        else:
            saved = format_bytes(result["saved_bytes"])
            pct = result["saved_percent"]
            print(f"{result['original_dimensions']}->{result['optimized_dimensions']} "
                  f"| {format_bytes(result['original_size'])}->{format_bytes(result['optimized_size'])} "
                  f"| saved: {saved} ({pct:.1f}%)")
    
    # Summary
    if results and not dry_run:
        total_saved = total_original - total_optimized
        total_pct = (total_saved / total_original * 100) if total_original > 0 else 0
        print(f"\n{'='*60}")
        print(f"SUMMARY: {len(results)} images processed")
        print(f"  Total original:  {format_bytes(total_original)}")
        print(f"  Total optimized: {format_bytes(total_optimized)}")
        print(f"  Total saved:     {format_bytes(total_saved)} ({total_pct:.1f}%)")
    
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Optimize images for CONFIT (local, no external service)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/tooling/optimize_images.py --input frontend/public/images --output frontend/public/images/optimized
  python3 scripts/tooling/optimize_images.py --input uploads/catalog --max-width 1920 --quality 85 --format webp
  python3 scripts/tooling/optimize_images.py --single image.jpg --compare
        """
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", "-i", type=Path, help="Input directory")
    input_group.add_argument("--single", "-s", type=Path, help="Single image file")
    
    parser.add_argument("--output", "-o", type=Path, help="Output directory (required for --input)")
    parser.add_argument("--max-width", type=int, help="Maximum width (maintains aspect ratio)")
    parser.add_argument("--max-height", type=int, help="Maximum height (maintains aspect ratio)")
    parser.add_argument("--quality", "-q", type=int, default=85, help="Quality 1-100 (default: 85)")
    parser.add_argument("--format", "-f", choices=["jpeg", "png", "webp"], help="Output format")
    parser.add_argument("--lossless", action="store_true", help="Lossless WebP compression")
    parser.add_argument("--no-recursive", action="store_true", help="Don't recurse into subdirectories")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't write files")
    parser.add_argument("--compare", action="store_true", help="Show detailed comparison (with --single)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.input and not args.output:
        print("--input requires --output", file=sys.stderr)
        return 1
    
    if args.single and not args.output and not args.compare:
        print("--single requires --output or --compare", file=sys.stderr)
        return 1
    
    if args.quality < 1 or args.quality > 100:
        print("Quality must be 1-100", file=sys.stderr)
        return 1
    
    # Import ImageOps here to avoid issues if not available
    global ImageOps
    from PIL import ImageOps
    
    if args.single:
        if not args.single.exists():
            print(f"File not found: {args.single}", file=sys.stderr)
            return 1
        
        output_path = args.output or args.single.with_stem(args.single.stem + "_optimized")
        result = optimize_image(
            args.single, output_path,
            max_width=args.max_width,
            max_height=args.max_height,
            quality=args.quality,
            output_format=args.format,
            lossless=args.lossless,
        )
        
        if result["error"]:
            print(f"ERROR: {result['error']}", file=sys.stderr)
            return 1
        
        print(f"Original:  {result['original_dimensions']} - {format_bytes(result['original_size'])}")
        print(f"Optimized: {result['optimized_dimensions']} - {format_bytes(result['optimized_size'])}")
        print(f"Saved:     {format_bytes(result['saved_bytes'])} ({result['saved_percent']:.1f}%)")
        print(f"Format:    {result['format'].upper()}")
        
        if args.compare and not args.output:
            # Clean up temp file
            if output_path.exists():
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
        max_width=args.max_width,
        max_height=args.max_height,
        quality=args.quality,
        output_format=args.format,
        lossless=args.lossless,
        recursive=not args.no_recursive,
        dry_run=args.dry_run,
    )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())