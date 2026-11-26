"""Generate a scoped MCP client key: prints the raw key ONCE and the MCP_CLIENTS JSON snippet."""

import argparse
import hashlib
import json
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an MCP client key.")
    parser.add_argument("name")
    parser.add_argument("--tools", default="*", help="comma-separated tool names, or * for all")
    args = parser.parse_args()

    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    tools = ["*"] if args.tools == "*" else [t.strip() for t in args.tools.split(",") if t.strip()]
    snippet = [{"name": args.name, "key_sha256": digest, "tools": tools}]
    print(f"RAW KEY (store it now, it will not be shown again): {raw}")
    print("\nAdd to MCP_CLIENTS in .env:")
    print(f"MCP_CLIENTS={json.dumps(snippet)}")


if __name__ == "__main__":
    main()
