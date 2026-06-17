"""US addon data parser — ingests US Code and state terms from data/ directory.

Convention: put raw data under addons/us/data/ (same format as _usc/uscode).
On addon registration, parse() is called automatically to update blueprint.
"""
import json, os, re, logging
from pathlib import Path

logger = logging.getLogger(__name__)


def parse() -> list:
    """Parse US legal data from addons/us/data/ directory.

    Expected structure:
      data/uscode/          — US Code titles (same format as _usc/uscode)
      data/courts.yaml      — court hierarchy (from juriscraper)
      data/state_terms.json — structured state terms

    Returns list of {type, count, entries} dicts for each data source.
    """
    base = Path(__file__).resolve().parent / "data"
    results = []

    # 1. US Code titles
    uscode_dir = base / "uscode"
    if uscode_dir.exists():
        titles = []
        for td in sorted(uscode_dir.iterdir()):
            if td.is_dir() and td.name.startswith("title-"):
                m = re.match(r"title-(\d+)-(.+)", td.name)
                if m:
                    titles.append({"num": m.group(1), "name": m.group(2).replace("-", " ").title()})
        if titles:
            results.append({"type": "us_code_titles", "count": len(titles), "entries": titles})

    # 2. Court hierarchy
    courts_file = base / "courts.yaml"
    if courts_file.exists():
        import yaml
        with open(courts_file, "r", encoding="utf-8") as f:
            courts = yaml.safe_load(f)
        if courts:
            results.append({"type": "us_courts", "count": len(courts) if isinstance(courts, list) else 1, "entries": courts})

    # 3. State terms
    state_file = base / "state_terms.json"
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            state_terms = json.load(f)
        if state_terms:
            results.append({"type": "state_terms", "count": len(state_terms), "entries": state_terms})

    return results


def update_blueprint(parsed: list):
    """Merge parsed results into the addon's blueprint.json."""
    bp_path = Path(__file__).resolve().parent / "blueprint.json"
    bp = {}
    if bp_path.exists():
        with open(bp_path, "r", encoding="utf-8") as f:
            bp = json.load(f)

    for item in parsed:
        key = item["type"]
        bp.setdefault("domain_assets", {})[key] = {
            "source": "addon parser: " + str(Path(__file__).resolve()),
            "count": item["count"],
            "entries": item["entries"],
        }

    with open(bp_path, "w", encoding="utf-8") as f:
        json.dump(bp, f, ensure_ascii=False, indent=2)
    logger.info("US addon: blueprint updated with %d data sources", len(parsed))
