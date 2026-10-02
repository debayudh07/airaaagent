"""Interactive CLI for the research agent.

    python main.py                     # chat
    python main.py "price of ETH"      # one-shot
    python main.py --address 0x... "balance of my wallet"
"""
import argparse
import asyncio
import logging
import sys

from airaa.agent import Web3ResearchAgent
from airaa.config import get_settings
from airaa.schemas import ResearchRequest


async def ask(agent: Web3ResearchAgent, query: str, address: str | None, time_range: str, verbose: bool) -> None:
    async def on_event(event: dict) -> None:
        kind = event["type"]
        if kind == "plan":
            print(f"  plan ({event['planner']}): {', '.join(event['tools']) or 'no tools'}", file=sys.stderr)
        elif kind == "tool_end":
            mark = "ok" if event["success"] else f"failed: {event.get('error')}"
            print(f"  {event['tool']}: {mark} ({event['duration_ms']}ms)", file=sys.stderr)
        elif kind == "token":
            print(event["text"], end="", flush=True)

    request = ResearchRequest(query=query, address=address, time_range=time_range, session_id=agent.session_id)
    result = await agent.research(request, on_event=on_event if verbose else None)
    if not verbose:
        print(result.get("result") or f"Error: {result.get('error')}")
    elif not result.get("success"):
        print(f"\nError: {result.get('error')}")
    else:
        print(f"\n\n[{result['execution_time']}s, completeness {result['data_quality_score']}%]")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="AIRAA Web3 research agent")
    parser.add_argument("query", nargs="?", help="Question to ask; omit for interactive mode")
    parser.add_argument("--address", help="Wallet address for on-chain questions")
    parser.add_argument("--range", dest="time_range", default="7d", help="1d, 7d, 30d, 90d or 1y")
    parser.add_argument("-q", "--quiet", action="store_true", help="Print only the final answer")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    settings = get_settings()
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY is not set (see .env.example)")

    agent = Web3ResearchAgent()
    verbose = not args.quiet
    if args.query:
        asyncio.run(ask(agent, args.query, args.address, args.time_range, verbose))
        return

    print(f"AIRAA research agent ({settings.synthesis_model}). Type 'exit' to quit.\n")
    while True:
        try:
            query = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if query.lower() in {"exit", "quit"}:
            break
        if query:
            asyncio.run(ask(agent, query, args.address, args.time_range, verbose))


if __name__ == "__main__":
    main()
