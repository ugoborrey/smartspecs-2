"""
Utility script to empty PKH tables (product_documents, products_canonical).
Use with caution – this deletes all evidence and canonical rows.

Usage:
    python pkh/clear_pkh.py
Requires:
    - DATABASE_URL in environment (or .env)
"""

import os

from dotenv import load_dotenv
import psycopg

load_dotenv()


def main() -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (check your .env)")

    confirm = input(
        "WARNING: This will TRUNCATE product_documents and products_canonical. Continue? (yes/no): "
    )
    if confirm.lower() != "yes":
        print("Aborted.")
        return

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE product_documents RESTART IDENTITY CASCADE;")
        cur.execute("TRUNCATE TABLE products_canonical RESTART IDENTITY CASCADE;")
        conn.commit()
        print("Tables truncated.")


if __name__ == "__main__":
    main()
