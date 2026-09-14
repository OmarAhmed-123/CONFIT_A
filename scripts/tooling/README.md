# CONFIT_A Engineering Tooling

This directory contains local engineering tools integrated around the CONFIT_A repository.

## Tools

| Script | Purpose | Category |
|--------|---------|----------|
| `analyze_bundlephobia.py` | Frontend dependency cost analysis | Level 2 |
| `generate_erd.py` | Database ERD from SQLAlchemy models | Level 2 |
| `validate_csv.py` | Catalog CSV diagnosis & repair | Level 2 |
| `optimize_images.py` | Image optimization (Pillow) | Level 2 |
| `optimize_svgs.py` | SVG optimization (SVGO) | Level 2 |
| `dependency_graph.py` | Code dependency/impact analysis | Level 2 |
| `generate_architecture_diagrams.py` | Mermaid architecture diagrams | Level 3 |

## Usage

```bash
# Analyze a npm package before adding
python3 scripts/tooling/analyze_bundlephobia.py lodash

# Generate ERD for documentation
python3 scripts/tooling/generate_erd.py --format mermaid --output docs/architecture/erd.mmd

# Diagnose catalog CSV
python3 scripts/tooling/validate_csv.py --diagnose catalog.csv

# Optimize images
python3 scripts/tooling/optimize_images.py --input frontend/public/images --output frontend/public/images/optimized

# Optimize SVGs
python3 scripts/tooling/optimize_svgs.py --input frontend/src/assets/icons --output frontend/src/assets/icons

# Impact analysis before refactoring
python3 scripts/tooling/dependency_graph.py --impact backend/app/services/tryon_service.py

# Generate all architecture diagrams
python3 scripts/tooling/generate_architecture_diagrams.py
```

## Security

All tools run locally. No production data or secrets are sent to external services.

See `docs/tooling/TOOL_SECURITY_POLICY.md` for details.