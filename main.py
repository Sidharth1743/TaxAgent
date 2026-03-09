#!/usr/bin/env python3
"""CLI entry point for TaxAgent services."""

import argparse
import subprocess
import sys
import os


def main():
    parser = argparse.ArgumentParser(description="TaxAgent CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="Start all A2A agent servers")
    sub.add_parser("graph-api", help="Start the Graph API server")

    scrape = sub.add_parser("scrape", help="Run a scraper directly")
    scrape.add_argument("scraper", choices=["caclub", "taxtmi", "turbotax", "taxkanoon", "casemine"])
    scrape.add_argument("--query", required=True)
    scrape.add_argument("--max-links", type=int, default=5)

    args = parser.parse_args()
    root = os.path.dirname(os.path.abspath(__file__))

    if args.command == "serve":
        script = os.path.join(root, "scripts", "start_servers.sh")
        sys.exit(subprocess.call(["bash", script]))

    elif args.command == "graph-api":
        sys.exit(subprocess.call([
            sys.executable, "-m", "uvicorn", "graph_api:app",
            "--port", "9000", "--reload",
        ]))

    elif args.command == "scrape":
        scripts = {
            "caclub": "agents/caclub_agent.py",
            "taxtmi": "agents/taxtmi_agent.py",
            "turbotax": "agents/turbotax_agent.py",
            "taxkanoon": "scraping/taxkanoon.py",
            "casemine": "scraping/casemine.py",
        }
        script = os.path.join(root, scripts[args.scraper])
        cmd = [sys.executable, script, "--query", args.query, "--max-links", str(args.max_links)]
        sys.exit(subprocess.call(cmd))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
