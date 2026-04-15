"""Run the manager-layer agent cycle."""

from __future__ import annotations

import argparse
import sys

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, "..")

from agents import MonitorAgent, OrchestratorAgent, QCAgent, RecoveryAgent
from core.db import get_session
from core.logging import get_logger

logger = get_logger("scripts.run_orchestrator")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Orchestrator/QC/Recovery/Monitor cycle")
    parser.add_argument("--telegram-token", help="Telegram bot token for monitor alerts")
    parser.add_argument("--telegram-chat-id", help="Telegram chat ID for monitor alerts")
    args = parser.parse_args()

    with get_session() as session:
        logger.info("Running agent cycle")

        orchestrator = OrchestratorAgent(session)
        dispatched = orchestrator.run()
        logger.info("Orchestrator cycle complete", extra_data={"dispatched": dispatched})

        qc_count = QCAgent(session).run()
        logger.info("QC cycle complete", extra_data={"scored": qc_count})

        recovered = RecoveryAgent(session).run()
        logger.info("Recovery cycle complete", extra_data={"recovered": recovered})

        monitor = MonitorAgent(
            session,
            telegram_bot_token=args.telegram_token,
            telegram_chat_id=args.telegram_chat_id,
        )
        report = monitor.run()
        logger.info("Monitor cycle complete", extra_data={"report": report})


if __name__ == "__main__":
    main()
