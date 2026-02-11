"""HUGO — Voice-first personal assistant entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import structlog


def configure_logging(verbose: bool = False) -> None:
    """Configure structured logging."""
    log_level = logging.DEBUG if verbose else logging.INFO

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    logging.basicConfig(level=log_level, format="%(message)s", stream=sys.stdout)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="hugo",
        description="HUGO — Voice-first personal assistant for Reachy Mini",
    )
    parser.add_argument(
        "--sim",
        action="store_true",
        default=os.getenv("HUGO_SIMULATION_MODE", "false").lower() == "true",
        help="Run in simulation mode (no robot hardware required)",
    )
    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Disable voice pipeline (text-only mode)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("REACHY_HOST", "localhost"),
        help="Reachy Mini robot host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("REACHY_PORT", "50051")),
        help="Reachy Mini robot port",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    """Run the HUGO assistant."""
    from src.flows.assistant_flow import AssistantFlow

    voice_enabled = not args.no_voice and os.getenv("HUGO_VOICE_ENABLED", "true").lower() == "true"

    flow = AssistantFlow(
        sim=args.sim,
        voice_enabled=voice_enabled,
        robot_host=args.host,
        robot_port=args.port,
    )

    try:
        await flow.kickoff_async()
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
    finally:
        await flow.shutdown()


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    configure_logging(verbose=args.verbose)

    logger = logging.getLogger(__name__)
    logger.info("Starting HUGO (sim=%s, voice=%s)", args.sim, not args.no_voice)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
