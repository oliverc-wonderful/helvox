"""Convert a verified exact-chunk bank into Helvox's input format."""

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("bank", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument(
    "--individual-chunks",
    action="store_true",
    help="Dataset takes; short chunks are not valid voice references",
)
args = parser.parse_args()
pack = json.loads(args.bank.read_text(encoding="utf-8"))
items = []
for script in pack["scripts"]:
    requests = script["controller_selected_requests"]
    chunks = [request["exact_synthesis_returned_target"] for request in requests]
    groups = [[chunk] for chunk in chunks] if args.individual_chunks else [chunks]
    for number, group in enumerate(groups, 1):
        text = " ".join(group)
        item = {
            "id": (
                script["script_id"]
                + (f"-chunk-{number:02d}" if args.individual_chunks else "")
            ),
            "de": script["proposed_source_text"],
            "tts_request_chunks": group,
            "native_approval": "pending",
            "topic": script["topic"],
        }
        for dialect in ["ag", "be", "bs", "gr", "lu", "sg", "vs", "zh"]:
            item[f"ch_{dialect}"] = text
        items.append(item)
args.output.write_text(
    json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"Exported {len(items)} Helvox readouts")
