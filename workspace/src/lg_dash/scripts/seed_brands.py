from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from lg_dash.models import Brand, Category
from lg_dash.storage.db import connect, migrate, transaction
from lg_dash.storage.repo import (
    count,
    list_brands,
    list_categories,
    upsert_brand,
    upsert_category,
)


def load_brands(path: Path) -> list[Brand]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Brand(**item) for item in raw["brands"]]


def load_categories(path: Path) -> list[Category]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Category(**item) for item in raw["categories"]]


def run(config_dir: Path) -> tuple[int, int]:
    conn = connect()
    try:
        applied = migrate(conn)
        if applied:
            print(f"Applied migrations: {', '.join(applied)}")

        brands = load_brands(config_dir / "brands.yaml")
        categories = load_categories(config_dir / "categories.yaml")

        with transaction(conn):
            for c in categories:
                upsert_category(conn, c)
            for b in brands:
                upsert_brand(conn, b)

        brand_count = count(conn, "brand")
        category_count = count(conn, "category")
        print(f"Seeded {brand_count} brand(s), {category_count} categorie(s).")
        for b in list_brands(conn):
            print(f"  brand:   {b.id:<10} {b.display}")
        for c in list_categories(conn):
            print(f"  category: {c.id.value:<11} {c.display}")
        return brand_count, category_count
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed brand and category master tables")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="Directory containing brands.yaml and categories.yaml",
    )
    args = parser.parse_args()
    run(args.config_dir.resolve())


if __name__ == "__main__":
    main()
