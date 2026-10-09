# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The on-disk envelope and its sub-structures — the canonical home for the
core data types (WORKING_AGREEMENT canonical home registry).

Frozen msgspec Structs. The envelope field set is technical spec §3.4; the public
signatures mirror technical spec §16. Frozen is load-bearing: it is how the runtime
enforces input immutability "by construction" (F-PROD-3) — mutating a frozen Struct
raises AttributeError (verified against msgspec 0.21.1).
"""

from __future__ import annotations

from typing import Any

from msgspec import Struct


class ProducerRef(Struct, frozen=True):
    """A Producer's on-the-wire identity (envelope `producer` field, technical §3.4).

    Distinct from the in-memory ProducerId {kind, instance_id, parent_id, metadata}
    (kernel Decision #2): the wire form carries only what a reader needs to identify
    and link the Producer. `parent` is the spawning Producer's instance, or None for
    topology-declared initial Producers.
    """

    kind: str
    instance: str
    parent: str | None = None


class BlobRef(Struct, frozen=True):
    """Reference to a content-addressed payload in the blob store (technical §3.7).

    Serialized in an envelope payload as {"$blob": "sha256:<hex>", "bytes": n}; this
    Struct is the typed in-memory form. `sha256` is the canonical-bytes hash; `bytes`
    is the stored length.
    """

    sha256: str
    bytes: int


class Event(Struct, frozen=True):
    """One bus event, persisted as one frame (technical §3.4).

    `seq` is the bus sequence number (identity + total order, assigned at append).
    `kind` is the event kind ("substrate." prefix reserved). `schema` is "<kind>@<ver>".
    `producer` is the emitting Producer's ref, or None for runtime-emitted events.
    `t` is a supplementary wall-clock timestamp (never used for ordering; excluded
    from the D-8 equivalence relation). `payload` is the inline payload or a blob
    reference. The `crc` field is added by the record layer at frame time (§3.3),
    not carried on the in-memory Event.
    """

    seq: int
    kind: str
    schema: str
    producer: ProducerRef | None
    t: float
    payload: Any

    @classmethod
    def from_envelope(cls, env: dict[str, Any]) -> Event:
        """The Event a stored record envelope describes (the resume fold and inspect replay
        events read back from a record; lens audit F037: two copies of this)."""
        ref = env.get("producer")
        producer = (
            ProducerRef(
                kind=str(ref.get("kind", "")),
                instance=str(ref.get("instance", "")),
                parent=ref.get("parent"),
            )
            if isinstance(ref, dict)
            else None
        )
        return cls(
            seq=int(env["seq"]),
            kind=str(env["kind"]),
            schema=str(env.get("schema", "")),
            producer=producer,
            t=float(env.get("t", 0.0)),
            payload=env.get("payload"),
        )


class Subscription(Struct, frozen=True):
    """What a Predicate / View / Route is consulted on (technical §16, §6.5).

    The writer's subscription index consults a subscriber only when an event matches
    its `kinds` and/or `producers`. Both empty is a registration error (enforced at
    topology registration, not here); "subscribe to everything" must be spelled
    explicitly. Frozensets keep the subscription immutable and hashable.
    """

    kinds: frozenset[str] = frozenset()
    producers: frozenset[str] = frozenset()

    def is_empty(self) -> bool:
        """True if neither kinds nor producers is set (a registration error)."""
        return not self.kinds and not self.producers

    def matches(self, event: Event) -> bool:
        """The one subscription rule: the event's kind is subscribed, or its Producer's kind
        or instance is (lens audit F037: the sequencer, the resume fold and inspect each kept
        a copy)."""
        if event.kind in self.kinds:
            return True
        p = event.producer
        return p is not None and (p.kind in self.producers or p.instance in self.producers)
