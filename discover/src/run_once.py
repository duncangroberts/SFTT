"""CLI entry point for the simplified Discover pipeline."""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from typing import Sequence
from datetime import datetime, timedelta, timezone

from . import embed_index
from . import hn_fetch
from . import microtrends
from . import util
from llm_client import LlamaCppClient

LOGGER = logging.getLogger(__name__)


@dataclass
class RunConfig:
    since_arg: str
    since_days: int
    embed_model: str





def run(config: RunConfig) -> dict[str, dict[str, int] | None]:
    conn = util.get_db()
    try:
        util.ensure_schema(conn)
        util.ensure_views(conn)

        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        since_date = yesterday - timedelta(days=config.since_days - 1) # -1 because yesterday is 1 day
        since_unix = int(datetime(since_date.year, since_date.month, since_date.day, tzinfo=timezone.utc).timestamp())
        results: dict[str, dict[str, int] | None] = {}
        summary_bits: list[str] = []

        llm_client_instance = LlamaCppClient()
        microtrends_instance = microtrends.Microtrends(util.DB_PATH, llm_client_instance)

        with util.run_logger(conn, since_arg=config.since_arg, embed_model=config.embed_model) as run_id:
            hn_state = util.get_source_state(conn, 'hn')
            with util.stage_logger(conn, run_id, 'hn_fetch') as stage:
                hn_result, hn_cursor = hn_fetch.fetch_and_upsert(
                    conn,
                    since_unix,
                    hn_state,
                    progress_cb=stage.set_detail,
                )
                util.save_source_state(conn, 'hn', hn_cursor)
                stage.set_detail(
                    f"stories={hn_result['stories']}, comments={hn_result['comments']}"
                )
            results['hn'] = hn_result
            summary_bits.append(f"stories={hn_result['stories']}")

            with util.stage_logger(conn, run_id, 'embedding_build') as stage:
                embed_stats = embed_index.build(conn, config.embed_model)
                results['embeddings'] = embed_stats or {'embeddings': 0, 'terms': 0}
                if embed_stats:
                    stage.set_detail(
                        f"embeddings={embed_stats['embeddings']}, terms={embed_stats['terms']}"
                    )
                    summary_bits.append(f"embeddings={embed_stats['embeddings']}")
                else:
                    stage.set_detail('skipped')

            with util.stage_logger(conn, run_id, 'trend_signals') as stage:
                trend_stats = microtrends_instance.build_components(
                    conn,
                    run_id,
                    since_unix,
                    window_days=config.since_days,
                    progress_cb=stage.set_detail,
                )
                results['trend_signals'] = trend_stats
                stage.set_detail(
                    f"trends={trend_stats['trends']}, new={trend_stats['new_trends']}"
                )
                summary_bits.append(f"trends={trend_stats['trends']}")

            with util.stage_logger(conn, run_id, 'refresh_views'):
                util.ensure_views(conn)

            util.update_run(conn, run_id, message='; '.join(summary_bits))
        return results
    finally:
        conn.close()


def parse_args(argv: Sequence[str] | None = None) -> RunConfig:
    parser = argparse.ArgumentParser(description='Run the Discover pipeline once (HN only).')
    parser.add_argument('--embed-model', default='C:/Users/dunca/Desktop/SFTT/models/all-MiniLM-L6-v2', help='Sentence transformer name or "none"')

    args = parser.parse_args(argv)

    return RunConfig(
        since_arg='30d',
        since_days=30,
        embed_model=args.embed_model,
    )


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    config = parse_args(argv)
    run(config)


if __name__ == '__main__':
    main()
