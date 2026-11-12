import asyncio, tempfile
from pathlib import Path
from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder as D
import r1_value
m = {f"m{i}": D(seed=i, menu=["Paris"]) for i in range(4)}
v = r1_value.ensemble("q", members=m, judge=D(seed=9, menu=["m0"]), quorum=3)
async def main():
    td = Path(tempfile.mkdtemp())
    for name in ("a", "b"):
        r = await Runtime(td/name).run(v)
        k = [e["kind"] for e in read_record(td/name)]
        print(name, r.status, "fired adjudicate:", sum(1 for e in read_record(td/name) if e["kind"]=="substrate.TriggerFired" and e["payload"]["trigger_id"]=="adjudicate-on-candidate"), "Verdicts:", k.count("Verdict"))
asyncio.run(main())
