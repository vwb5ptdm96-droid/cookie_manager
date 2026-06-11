"""Run the web UI and the fixed-interval scheduler."""

import os
import threading

from dotenv import load_dotenv

load_dotenv()

from scheduler.engine import run_forever  # noqa: E402
from web.app import create_app  # noqa: E402


def start_scheduler() -> None:
    interval_hours = float(os.getenv("PROBE_INTERVAL_HOURS", "2"))
    thread = threading.Thread(
        target=run_forever,
        args=(interval_hours,),
        name="cookie-scheduler",
        daemon=True,
    )
    thread.start()


def main() -> None:
    if os.getenv("SCHEDULER_ENABLED", "true").lower() == "true":
        start_scheduler()

    app = create_app()
    app.run(
        host=os.getenv("WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("WEB_PORT", "5000")),
        debug=os.getenv("WEB_DEBUG", "false").lower() == "true",
        use_reloader=False,
    )


if __name__ == "__main__":
    main()

