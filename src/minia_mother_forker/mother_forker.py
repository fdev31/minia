"""Mother forker — orchestrates startup of minia services in dependency order.

Startup sequence:
1. Start minia-server and minia-tts in parallel (create cmd + event sockets)
2. Wait for all sockets to be available
3. Start minia-chatloop (or minia-web with --web flag)
4. Monitor all processes
"""

from __future__ import annotations

import asyncio
import signal
import sys
import argparse
import os

from minia_utils.logging import configure_logging, get_logger
from minia_config import config

logger = get_logger(__name__)


class MotherForker:
    """Manages the lifecycle of all minia services."""

    def __init__(self, web: bool = False) -> None:
        self._web = web
        self._server_proc: asyncio.subprocess.Process | None = None
        self._tts_proc: asyncio.subprocess.Process | None = None
        self._relay_proc: asyncio.subprocess.Process | None = None
        self._shutdown = False

    async def _wait_for_socket(self, path: str, timeout: float = 30.0) -> bool:
        """Wait until a Unix socket file appears and is connectable."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if self._shutdown:
                return False
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(path), timeout=1.0
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                logger.info("Socket ready: %s", path)
                return True
            except (OSError, ConnectionRefusedError, TimeoutError):
                pass
            await asyncio.sleep(0.5)
        logger.error("Timeout waiting for socket: %s", path)
        return False

    async def _start_service(
        self,
        name: str,
        cmd: list[str],
        cwd: str | None = None,
        extra_env: dict | None = None,
    ) -> asyncio.subprocess.Process:
        """Start a subprocess and return it."""
        logger.info("Starting %s: %s", name, " ".join(cmd))

        # Inherit current environment and add custom env vars
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        logger.info("%s started with PID %s", name, proc.pid)
        return proc

    async def _read_stream(self, stream, name: str) -> list[str]:
        """Read a stream line-by-line and return captured lines."""
        lines: list[str] = []
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip("\n")
            lines.append(decoded)
            if stream.name == 2:
                logger.warning("[%s] %s", name, decoded)
            else:
                logger.info("[%s] %s", name, decoded)
        return lines

    async def _monitor_process(
        self, proc: asyncio.subprocess.Process, name: str
    ) -> None:
        """Monitor a process, log its output, and handle unexpected exits."""
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        reader_stdout = asyncio.create_task(self._read_stream(proc.stdout, name))
        reader_stderr = asyncio.create_task(self._read_stream(proc.stderr, name))

        await proc.wait()
        stdout_lines, stderr_lines = await asyncio.gather(reader_stdout, reader_stderr)

        if not self._shutdown:
            logger.error(
                "%s (PID %s) exited unexpectedly with code %s",
                name,
                proc.pid,
                proc.returncode,
            )
            if stdout_lines or stderr_lines:
                logger.error("=== %s stdout ===", name)
                for line in stdout_lines:
                    logger.error("  %s", line)
                logger.error("=== %s stderr ===", name)
                for line in stderr_lines:
                    logger.error("  %s", line)
                logger.error("=== end of %s output ===", name)
            await self.shutdown()

    async def run(self, args: argparse.Namespace) -> None:
        """Start all services in dependency order."""
        self._shutdown = False

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            s = sig  # capture for lambda
            loop.add_signal_handler(
                sig, lambda: asyncio.create_task(self._handle_signal(s))
            )

        # 1. Start minia-server and minia-tts in parallel
        server_socket = config.default.cmd_socket_path
        event_socket = config.default.event_socket_path
        tts_socket = config.tts.cmd_socket_path
        tts_audio_socket = config.tts.audio_socket_path

        self._server_proc = await self._start_service(
            "minia-server",
            ["minia-server"],
            extra_env={"MINIA_LOG_LEVEL": args.log_level},
        )
        self._tts_proc = await self._start_service(
            "minia-tts",
            ["minia-tts"],
            extra_env={"MINIA_LOG_LEVEL": args.log_level},
        )

        # 2. Wait for all sockets
        logger.info("Waiting for minia-server and minia-tts sockets...")
        cmd_ready = await self._wait_for_socket(server_socket)
        event_ready = await self._wait_for_socket(event_socket)
        tts_cmd_ready = await self._wait_for_socket(tts_socket)
        tts_audio_ready = await self._wait_for_socket(tts_audio_socket)

        if not cmd_ready or not event_ready:
            logger.error("minia-server failed to start properly")
            await self.shutdown()
            return

        if not tts_cmd_ready or not tts_audio_ready:
            logger.error("minia-tts failed to start properly")
            await self.shutdown()
            return

        # 3. Start minia-chatloop or minia-web
        if self._web:
            logger.info("Starting minia-web...")
            self._relay_proc = await self._start_service(
                "minia-web",
                ["minia-web"],
                extra_env={"MINIA_LOG_LEVEL": args.log_level},
            )
        else:
            logger.info("Starting minia-chatloop...")
            self._relay_proc = await self._start_service(
                "minia-chatloop",
                ["minia-chatloop"],
                extra_env={"MINIA_LOG_LEVEL": args.log_level},
            )

        # 4. Monitor all processes
        tasks = [
            asyncio.create_task(
                self._monitor_process(self._server_proc, "minia-server")
            ),
            asyncio.create_task(self._monitor_process(self._tts_proc, "minia-tts")),
            asyncio.create_task(
                self._monitor_process(
                    self._relay_proc, "minia-web" if self._web else "minia-chatloop"
                )
            ),
        ]

        logger.info("All services running. Press Ctrl+C to stop.")

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

        await self.shutdown()

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle shutdown signals."""
        logger.info("Received signal %s, shutting down...", sig.name)
        self._shutdown = True
        asyncio.create_task(self._shutdown_all())

    async def _shutdown_all(self) -> None:
        """Terminate all subprocesses and wait for them to exit."""
        service_name = "minia-web" if self._web else "minia-chatloop"
        for name, proc in [
            ("minia-server", self._server_proc),
            ("minia-tts", self._tts_proc),
            (service_name, self._relay_proc),
        ]:
            if proc and proc.returncode is None:
                logger.info("Terminating %s (PID %s)...", name, proc.pid)
                proc.terminate()
        for name, proc in [
            ("minia-server", self._server_proc),
            ("minia-tts", self._tts_proc),
            (service_name, self._relay_proc),
        ]:
            if proc and proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except TimeoutError:
                    logger.warning("%s didn't terminate gracefully, killing", name)
                    proc.kill()
                    await proc.wait()

        logger.info("All services stopped.")

    async def shutdown(self) -> None:
        """Gracefully shut down all services."""
        if self._shutdown:
            return
        self._shutdown = True
        logger.info("Shutting down all services...")
        await self._shutdown_all()


def main() -> None:
    """CLI entry point for the mother forker."""
    parser = argparse.ArgumentParser(
        description="Mother forker — orchestrates minia services"
    )
    parser.add_argument(
        "--web", action="store_true", help="Start minia-web instead of minia-chatloop"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=config.default.log_level or "INFO",
        help="Logging level (also propagated to subprocesses)",
    )
    args = parser.parse_args()

    configure_logging(log_level=args.log_level, add_console=True)

    forker = MotherForker(web=args.web)
    try:
        asyncio.run(forker.run(args))
    except KeyboardInterrupt:
        asyncio.run(forker.shutdown())
        sys.exit(0)
