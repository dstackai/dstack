"""Test receiver/CLI: SQLite commit precedes any Gateway ACK."""

import argparse
import asyncio
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from dstack._internal.proxy.lib.schemas.usage import UsageAckResponse, UsageBatchPage

COUNTERS = (
    "prompt_tokens",
    "cached_prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "unknown_usage_attempts",
)


@dataclass
class ReceiptReport:
    fetched_ids: list[str]
    committed_ids: list[str]
    replayed_ids: list[str]
    acked_ids: list[str] = field(default_factory=list)
    has_more: bool = False


class MockReceiver:
    def __init__(self, url: str, ledger: Path, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(base_url=url, timeout=10)
        self._owns_client = client is None
        self.db = sqlite3.connect(ledger)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (collector_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS receipts (
              collector_id TEXT, batch_id TEXT, content TEXT NOT NULL,
              PRIMARY KEY (collector_id,batch_id));
            CREATE TABLE IF NOT EXISTS entries (
              collector_id TEXT, batch_id TEXT, subject TEXT, service TEXT,
              prompt_tokens INTEGER, cached_prompt_tokens INTEGER,
              completion_tokens INTEGER, total_tokens INTEGER, unknown_usage_attempts INTEGER,
              PRIMARY KEY (collector_id,batch_id,subject,service));
        """)

    async def collect_once(self, limit: int = 100, acknowledge: bool = True) -> ReceiptReport:
        response = await self.client.get("/api/usage/batches", params={"limit": limit})
        response.raise_for_status()
        page = UsageBatchPage.model_validate(response.json())
        new, replay = self.commit_page(page)
        ids = [batch.batch_id for batch in page.batches]
        report = ReceiptReport(ids, new, replay, has_more=page.has_more)
        if ids and acknowledge:
            report.acked_ids = (await self.acknowledge_committed(ids)).acknowledged_batch_ids
        return report

    def commit_page(self, page: UsageBatchPage) -> tuple[list[str], list[str]]:
        new, replay = [], []
        with self.db:
            bound = self.db.execute("SELECT collector_id FROM metadata").fetchone()
            if bound and bound[0] != page.collector_id:
                raise ValueError("Collector identity changed; reconcile")
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES (?)", (page.collector_id,))
            for batch in page.batches:
                content = json.dumps(
                    batch.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                )
                existing = self.db.execute(
                    "SELECT content FROM receipts WHERE collector_id=? AND batch_id=?",
                    (page.collector_id, batch.batch_id),
                ).fetchone()
                if existing:
                    if existing[0] != content:
                        raise ValueError("Same batch ID has conflicting content")
                    replay.append(batch.batch_id)
                    continue
                self.db.execute(
                    "INSERT INTO receipts VALUES (?,?,?)",
                    (page.collector_id, batch.batch_id, content),
                )
                for entry in batch.entries:
                    self.db.execute(
                        "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            page.collector_id,
                            batch.batch_id,
                            entry.consumer_subject_id,
                            entry.service_id,
                            *(getattr(entry, name) for name in COUNTERS),
                        ),
                    )
                new.append(batch.batch_id)
        return new, replay

    async def acknowledge_committed(self, batch_ids: list[str]) -> UsageAckResponse:
        committed = set(self.receipt_ids())
        if not set(batch_ids) <= committed:
            raise ValueError("Cannot ACK a batch that has not committed")
        response = await self.client.post("/api/usage/batches/ack", json={"batch_ids": batch_ids})
        response.raise_for_status()
        return UsageAckResponse.model_validate(response.json())

    def receipt_ids(self) -> list[str]:
        return [
            row[0] for row in self.db.execute("SELECT batch_id FROM receipts ORDER BY batch_id")
        ]

    def totals(self) -> dict[tuple[str, str], dict[str, int]]:
        rows = self.db.execute(
            "SELECT subject,service,"
            + ",".join(f"SUM({name})" for name in COUNTERS)
            + " FROM entries GROUP BY subject,service"
        ).fetchall()
        return {(row[0], row[1]): dict(zip(COUNTERS, row[2:])) for row in rows}

    async def close(self) -> None:
        self.db.close()
        if self._owns_client:
            await self.client.aclose()


async def _run(args) -> None:
    receiver = MockReceiver(args.url, Path(args.ledger))
    try:
        while True:
            report = await receiver.collect_once(args.limit, acknowledge=not args.no_ack)
            print(json.dumps(asdict(report)), flush=True)
            if not args.watch:
                break
            await asyncio.sleep(args.interval)
    finally:
        await receiver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", required=True, help="Private Gateway management URL / local SSH forward"
    )
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--no-ack", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=15)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
