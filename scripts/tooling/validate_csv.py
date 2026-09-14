#!/usr/bin/env python3
"""
CSV Validation & Repair Script — Group 6 Catalog Import Diagnostics

Diagnoses and optionally repairs common CSV issues in CONFIT catalog imports:
- Malformed CSV (broken delimiters, inconsistent quoting)
- Inconsistent columns (missing/extra columns per row)
- Broken rows (wrong field count)
- Encoding issues (UTF-8, BOM, etc.)
- Problematic data (null bytes, control characters)

Server-side validation remains authoritative for:
- File size, schema, CSV injection protection
- Required columns, SKU uniqueness, ownership
- Tenant isolation, transactional correctness
- Idempotency, database constraints

Usage:
    python3 scripts/tooling/validate_csv.py --diagnose catalog.csv
    python3 scripts/tooling/validate_csv.py --repair catalog.csv --output fixed.csv
    python3 scripts/tooling/validate_csv.py --schema-check catalog.csv --schema backend/app/schemas/catalog.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

# Expected catalog columns (from CONFIT schema)
EXPECTED_CATALOG_COLUMNS = [
    "sku", "name", "description", "category", "subcategory",
    "brand", "color", "size", "gender", "season",
    "price", "currency", "cost_price", "tax_rate",
    "stock_quantity", "low_stock_threshold", "track_inventory",
    "image_url", "image_alt", "tags", "attributes",
    "is_active", "is_featured", "meta_title", "meta_description",
]

REQUIRED_COLUMNS = ["sku", "name", "category", "price", "currency"]


class CSVDiagnostic:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.issues: list[dict[str, Any]] = []
        self.rows_analyzed = 0
        self.encoding_used = "utf-8"
        self.delimiter_used = ","
        self.header: list[str] = []
    
    def detect_encoding(self) -> str:
        """Detect file encoding (basic)."""
        import codecs
        try:
            with open(self.filepath, "rb") as f:
                raw = f.read(4096)
            
            # Check for BOM
            if raw.startswith(codecs.BOM_UTF8):
                return "utf-8-sig"
            if raw.startswith(codecs.BOM_UTF16_LE):
                return "utf-16-le"
            if raw.startswith(codecs.BOM_UTF16_BE):
                return "utf-16-be"
            
            # Try common encodings
            for enc in ["utf-8", "latin-1", "cp1252", "utf-16"]:
                try:
                    raw.decode(enc)
                    return enc
                except UnicodeDecodeError:
                    continue
        except Exception:
            pass
        return "utf-8"
    
    def detect_delimiter(self, sample: str) -> str:
        """Detect CSV delimiter."""
        for delim in [",", ";", "\t", "|"]:
            if delim in sample:
                # Check consistency
                lines = sample.strip().split("\n")[:5]
                counts = [line.count(delim) for line in lines if line.strip()]
                if counts and len(set(counts)) == 1:
                    return delim
        return ","
    
    def diagnose(self) -> dict[str, Any]:
        """Run full diagnostic on CSV file."""
        self.encoding_used = self.detect_encoding()
        print(f"Detected encoding: {self.encoding_used}")
        
        # Read sample for delimiter detection
        with open(self.filepath, "r", encoding=self.encoding_used, errors="replace") as f:
            sample = f.read(8192)
        
        self.delimiter_used = self.detect_delimiter(sample)
        print(f"Detected delimiter: '{self.delimiter_used}' (repr: {repr(self.delimiter_used)})")
        
        # Full parse
        with open(self.filepath, "r", encoding=self.encoding_used, errors="replace") as f:
            # Reset and use csv module
            f.seek(0)
            reader = csv.reader(f, delimiter=self.delimiter_used)
            
            try:
                self.header = next(reader)
            except StopIteration:
                self.issues.append({
                    "type": "empty_file",
                    "severity": "error",
                    "message": "File is empty or has no header row",
                    "row": 0,
                })
                return self.get_report()
            
            print(f"Header columns ({len(self.header)}): {self.header}")
            
            # Check header
            self._check_header()
            
            # Check each row
            for row_num, row in enumerate(reader, start=2):  # 1-indexed, header is row 1
                self.rows_analyzed += 1
                self._check_row(row_num, row)
                
                # Progress for large files
                if self.rows_analyzed % 10000 == 0:
                    print(f"  Analyzed {self.rows_analyzed} rows...")
        
        return self.get_report()
    
    def _check_header(self) -> None:
        """Validate header row."""
        # Check for empty column names
        for i, col in enumerate(self.header):
            if not col or not col.strip():
                self.issues.append({
                    "type": "empty_column_name",
                    "severity": "error",
                    "message": f"Column {i} has empty name",
                    "row": 1,
                    "column": i,
                })
        
        # Check for duplicate column names
        seen = {}
        for i, col in enumerate(self.header):
            if col in seen:
                self.issues.append({
                    "type": "duplicate_column",
                    "severity": "warning",
                    "message": f"Duplicate column name: '{col}' (first at index {seen[col]}, also at {i})",
                    "row": 1,
                    "column": i,
                })
            else:
                seen[col] = i
        
        # Check required columns
        missing_required = set(REQUIRED_COLUMNS) - set(self.header)
        for col in missing_required:
            self.issues.append({
                "type": "missing_required_column",
                "severity": "error",
                "message": f"Required column missing: '{col}'",
                "row": 1,
            })
        
        # Check for unexpected columns
        unexpected = set(self.header) - set(EXPECTED_CATALOG_COLUMNS)
        for col in unexpected:
            self.issues.append({
                "type": "unexpected_column",
                "severity": "info",
                "message": f"Unexpected column (not in schema): '{col}'",
                "row": 1,
            })
    
    def _check_row(self, row_num: int, row: list[str]) -> None:
        """Validate a single data row."""
        expected_cols = len(self.header)
        actual_cols = len(row)
        
        if actual_cols != expected_cols:
            self.issues.append({
                "type": "column_count_mismatch",
                "severity": "error" if actual_cols < expected_cols else "warning",
                "message": f"Row has {actual_cols} columns, expected {expected_cols} (diff: {actual_cols - expected_cols:+d})",
                "row": row_num,
                "expected_columns": expected_cols,
                "actual_columns": actual_cols,
            })
            # Pad or truncate for further checks
            if actual_cols < expected_cols:
                row = row + [""] * (expected_cols - actual_cols)
            else:
                row = row[:expected_cols]
        
        # Check each cell
        for col_idx, (col_name, value) in enumerate(zip(self.header, row)):
            # Null bytes
            if "\x00" in value:
                self.issues.append({
                    "type": "null_byte",
                    "severity": "error",
                    "message": f"Null byte in column '{col_name}'",
                    "row": row_num,
                    "column": col_idx,
                })
            
            # Control characters (except tab, newline, carriage return)
            for ch in value:
                if ord(ch) < 32 and ch not in "\t\n\r":
                    self.issues.append({
                        "type": "control_character",
                        "severity": "warning",
                        "message": f"Control character U+{ord(ch):04X} in column '{col_name}'",
                        "row": row_num,
                        "column": col_idx,
                    })
                    break  # Only report first per cell
            
            # CSV injection risk (formula injection)
            if value and value[0] in "=+-@":
                self.issues.append({
                    "type": "csv_injection_risk",
                    "severity": "warning",
                    "message": f"Potential CSV injection in column '{col_name}': starts with '{value[0]}'",
                    "row": row_num,
                    "column": col_idx,
                })
            
            # Required field empty
            if col_name in REQUIRED_COLUMNS and not value.strip():
                self.issues.append({
                    "type": "required_field_empty",
                    "severity": "error",
                    "message": f"Required field '{col_name}' is empty",
                    "row": row_num,
                    "column": col_idx,
                })
            
            # SKU format check
            if col_name == "sku" and value:
                if not value.replace("-", "").replace("_", "").isalnum():
                    self.issues.append({
                        "type": "sku_format",
                        "severity": "warning",
                        "message": f"SKU '{value}' contains non-alphanumeric chars (allowed: - _)",
                        "row": row_num,
                        "column": col_idx,
                    })
            
            # Price format check
            if col_name in ("price", "cost_price") and value:
                try:
                    float(value)
                except ValueError:
                    self.issues.append({
                        "type": "price_format",
                        "severity": "error",
                        "message": f"Invalid price format: '{value}'",
                        "row": row_num,
                        "column": col_idx,
                    })
            
            # Quantity format check
            if col_name in ("stock_quantity", "low_stock_threshold") and value:
                try:
                    int(value)
                except ValueError:
                    self.issues.append({
                        "type": "quantity_format",
                        "severity": "error",
                        "message": f"Invalid integer quantity: '{value}'",
                        "row": row_num,
                        "column": col_idx,
                    })
    
    def get_report(self) -> dict[str, Any]:
        """Get diagnostic report."""
        errors = sum(1 for i in self.issues if i["severity"] == "error")
        warnings = sum(1 for i in self.issues if i["severity"] == "warning")
        info = sum(1 for i in self.issues if i["severity"] == "info")
        
        return {
            "file": str(self.filepath),
            "encoding": self.encoding_used,
            "delimiter": self.delimiter_used,
            "header": self.header,
            "rows_analyzed": self.rows_analyzed,
            "issues": self.issues,
            "summary": {
                "errors": errors,
                "warnings": warnings,
                "info": info,
                "total": len(self.issues),
            },
        }
    
    def print_report(self, report: dict[str, Any]) -> None:
        """Print formatted diagnostic report."""
        print(f"\n{'='*60}")
        print(f"CSV DIAGNOSTIC REPORT: {report['file']}")
        print(f"{'='*60}")
        print(f"Encoding:      {report['encoding']}")
        print(f"Delimiter:     '{report['delimiter']}'")
        print(f"Header cols:   {len(report['header'])}")
        print(f"Rows analyzed: {report['rows_analyzed']}")
        print(f"\nIssues found:  {report['summary']['total']} "
              f"(errors: {report['summary']['errors']}, "
              f"warnings: {report['summary']['warnings']}, "
              f"info: {report['summary']['info']})")
        
        if report["issues"]:
            print(f"\n--- ISSUES ---")
            for issue in report["issues"]:
                sev_marker = {"error": "[X]", "warning": "[!]", "info": "[i]"}[issue["severity"]]
                loc = f"row {issue.get('row', '?')}"
                if "column" in issue:
                    loc += f", col {issue['column']} ({self.header[issue['column']] if issue['column'] < len(self.header) else '?'})"
                print(f"  {sev_marker} [{issue['severity'].upper()}] {issue['type']}: {issue['message']} ({loc})")
        else:
            print("\n[OK] No issues found")


def repair_csv(input_path: Path, output_path: Path, report: dict[str, Any]) -> int:
    """Attempt to repair CSV based on diagnostic report."""
    print(f"\nAttempting repair: {input_path} -> {output_path}")
    
    encoding = report["encoding"]
    delimiter = report["delimiter"]
    header = report["header"]
    expected_cols = len(header)
    
    repaired_rows = 0
    skipped_rows = 0
    
    with open(input_path, "r", encoding=encoding, errors="replace") as infile:
        reader = csv.reader(infile, delimiter=delimiter)
        header_read = next(reader)  # Skip original header
        
        with open(output_path, "w", encoding="utf-8", newline="") as outfile:
            writer = csv.writer(outfile, delimiter=",", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(header)  # Write clean header
            
            for row_num, row in enumerate(reader, start=2):
                # Fix column count
                if len(row) < expected_cols:
                    row = row + [""] * (expected_cols - len(row))
                elif len(row) > expected_cols:
                    row = row[:expected_cols]
                
                # Sanitize cells
                clean_row = []
                for value in row:
                    # Remove null bytes
                    value = value.replace("\x00", "")
                    # Remove control chars except whitespace
                    value = "".join(ch for ch in value if ord(ch) >= 32 or ch in "\t\n\r")
                    # Escape CSV injection
                    if value and value[0] in "=+-@":
                        value = "'" + value  # Prefix with apostrophe to neutralize
                    clean_row.append(value)
                
                writer.writerow(clean_row)
                repaired_rows += 1
    
    print(f"Repaired {repaired_rows} rows, skipped {skipped_rows} rows")
    print(f"Output written to {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose and repair CSV files for CONFIT catalog imports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/tooling/validate_csv.py --diagnose catalog.csv
  python3 scripts/tooling/validate_csv.py --repair catalog.csv --output fixed.csv
  python3 scripts/tooling/validate_csv.py --schema-check catalog.csv
        """
    )
    parser.add_argument("file", nargs="?", type=Path, help="CSV file to analyze")
    parser.add_argument("--diagnose", action="store_true", help="Run diagnostic only")
    parser.add_argument("--repair", action="store_true", help="Attempt repair (requires --output)")
    parser.add_argument("--output", "-o", type=Path, help="Output file for repair")
    parser.add_argument("--schema-check", action="store_true", help="Validate against expected schema")
    
    args = parser.parse_args()
    
    if not args.file:
        parser.print_help()
        return 1
    
    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 1
    
    if args.repair and not args.output:
        print("--repair requires --output", file=sys.stderr)
        return 1
    
    # Run diagnostic
    diagnostic = CSVDiagnostic(args.file)
    report = diagnostic.diagnose()
    diagnostic.print_report(report)
    
    if args.repair:
        if report["summary"]["errors"] == 0:
            print("\nNo errors to repair; file appears clean.")
            return 0
        return repair_csv(args.file, args.output, report)
    
    # Exit code based on errors
    return 1 if report["summary"]["errors"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())