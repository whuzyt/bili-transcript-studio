from __future__ import annotations

import argparse
import time

from .jobs import store


def main() -> None:
    parser = argparse.ArgumentParser(description="Bilibili video to local transcript")
    parser.add_argument("url")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--max-parts", type=int)
    args = parser.parse_args()

    job = store.create(
        url=args.url,
        model=args.model,
        language=args.language,
        device=args.device,
        compute_type=args.compute_type,
        max_parts=args.max_parts,
    )
    print(f"job_id={job.id}", flush=True)
    print(f"output_dir={job.output_dir}", flush=True)
    while True:
        current = store.get(job.id)
        assert current is not None
        print(f"[{current.status}] {current.progress:.0%} {current.message}", flush=True)
        if current.status in {"done", "failed", "cancelled"}:
            if current.error:
                print(current.error)
            else:
                print(current.result_files)
            return
        time.sleep(5)


if __name__ == "__main__":
    main()
