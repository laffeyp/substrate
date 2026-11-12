import asyncio, json, sys, tempfile
from pathlib import Path
from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder as D
from substrate.reference.r1_ensemble import ensemble_topology
import r1_value
from tv import Topology, Producer

def mk():
    return {f"m{i}": D(seed=i, menu=["Paris", "Lyon", "Nice"]) for i in range(5)}, D(seed=99, menu=["m0", "m1", "m2"])

async def main():
    td = Path(tempfile.mkdtemp())
    m, j = mk()
    r_old = await Runtime(td/"old").run(ensemble_topology("Capital of France?", members=m, adjudicator=j, quorum=3, deterministic=True))
    m, j = mk()
    value = r1_value.ensemble("Capital of France?", members=m, judge=j, quorum=3)
    r_new = await Runtime(td/"new").run(value)
    print("status", r_old.status, r_new.status)
    old, new = list(read_record(td/"old")), list(read_record(td/"new"))
    print("events", len(old), len(new))
    def ids(evs):
        m = {}
        for e in evs:
            p = e.get("payload") or {}
            for x in ([p.get("instance")] if isinstance(p, dict) else []):
                if x and x not in m: m[x] = f"I{len(m)}"
        return m
    def norm(evs):
        m = ids(evs); s = json.dumps(evs, sort_keys=True)
        for k, v in m.items(): s = s.replace(k, v)
        return json.loads(s)
    old, new = norm(old), norm(new)
    def rename(evs):
        s = json.dumps(evs, sort_keys=True)
        s = s.replace('"adjudicate-on-candidate"', '"adjudicate"')
        for i in range(5):
            s = s.replace(f"answer-m{i}", f"member-m{i}")
        s = s.replace('"factory": "adjudicate"', '"factory": "adjudicator"').replace('"kind": "adjudicate"', '"kind": "adjudicator"')
        return json.loads(s)
    new = rename(new)
    def strip(e):
        e = {k: v for k, v in e.items() if k not in ("t", "crc")}
        return e
    diffs = 0
    for i, (a, b) in enumerate(zip(old, new)):
        a, b = strip(a), strip(b)
        if a["kind"] == "substrate.RunStarted":
            ta, tb = a["payload"]["topology"], b["payload"]["topology"]
            for k in ta:
                if ta[k] != tb.get(k):
                    if k == "producer_kinds":
                        for x, y in zip(ta[k], tb[k]):
                            for f in x:
                                if x[f] != y[f]:
                                    print("RunStarted.producer_kinds differs", x["kind"], f)
                    else:
                        print("RunStarted differs", k, ta[k], tb.get(k))
            continue
        if a["kind"] == "substrate.RunFinalised": a["payload"].pop("run_id", None); b["payload"].pop("run_id", None)
        if a != b:
            diffs += 1
            if diffs < 6:
                print("DIFF", i, json.dumps(a, sort_keys=True)[:400]); print("    ", json.dumps(b, sort_keys=True)[:400])
    print("non-RunStarted diffs", diffs)
    # static questions asked of the value without running
    print("producers", [p.kind for p in value.producers])
    print("edges", [(t.on.__name__, t.id, t.start.kind) for t in value.triggers])
    try:
        Topology(producers=value.producers[:-1], views=value.views, triggers=value.triggers, initial=value.initial, termination=value.termination)
    except ValueError as e:
        print("constructor refused:", e)
    t = value.triggers[0]
    try:
        Topology(producers=value.producers, views=value.views, triggers=(t, t), initial=value.initial, termination=value.termination)
    except ValueError as e:
        print("duplicate id refused:", str(e)[:70])
    # frozen
    try:
        value.producers = ()
    except Exception as e:
        print("frozen:", type(e).__name__)
asyncio.run(main())
