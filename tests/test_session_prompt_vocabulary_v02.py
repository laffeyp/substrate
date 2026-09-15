# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session-vocabulary v0.2 lock — PromptFragment + PromptComposed + PromptSource StrEnum.

Locks the Struct field shape, msgspec round-trip, and the kind-name/enum
integrity. The composer at `session/composer.py` emits PromptComposed;
the six fragment producers under `session/*_producer.py` emit PromptFragment.
"""

from __future__ import annotations

import msgspec

from substrate.topologies.session import PromptComposed, PromptFragment
from substrate.topologies.session.vocabulary import (
    PROMPT_COMPOSED,
    PROMPT_FRAGMENT,
    PROMPT_SOURCES,
    SESSION_KINDS,
    SESSION_OPEN_SOURCES,
    TURN_SCOPED_SOURCES,
    PromptSource,
    is_prompt_source,
    is_session_kind,
)


def test_prompt_fragment_round_trips_through_msgspec() -> None:
    """A PromptFragment survives msgspec.to_builtins + msgspec.convert with
    every field intact. Provenance carries arbitrary jsonable dicts. A
    StrEnum member in the `source` field serialises as its string value."""
    f = PromptFragment(
        source=PromptSource.ROLE,
        text="You are a code reviewer.",
        precedence=0,
        provenance={"role_name": "reviewer", "resolved_from": "/tmp/prompts/reviewer.md"},
    )
    raw = msgspec.to_builtins(f)
    assert raw == {
        "source": "role",
        "text": "You are a code reviewer.",
        "precedence": 0,
        "provenance": {"role_name": "reviewer", "resolved_from": "/tmp/prompts/reviewer.md"},
    }
    rebuilt = msgspec.convert(raw, PromptFragment)
    assert rebuilt == f


def test_prompt_composed_round_trips_through_msgspec() -> None:
    """A PromptComposed survives msgspec.to_builtins + msgspec.convert.
    msgspec preserves the tuple in the builtins form; JSON encoding
    (msgspec.json.encode) lands it as an array; convert reads either
    shape back to a tuple. Round-trip via encode/decode keeps every
    field intact."""
    c = PromptComposed(
        text="alpha\n\nbravo\n\ncharlie",
        fragment_seqs=(3, 7, 12),
        total_tokens=6,
        strategy="precedence_join",
    )
    encoded = msgspec.json.encode(c)
    rebuilt = msgspec.json.decode(encoded, type=PromptComposed)
    assert rebuilt == c
    # to_builtins keeps the tuple; convert accepts tuple or list.
    raw = msgspec.to_builtins(c)
    assert raw["text"] == "alpha\n\nbravo\n\ncharlie"
    assert tuple(raw["fragment_seqs"]) == (3, 7, 12)
    assert raw["total_tokens"] == 6
    assert raw["strategy"] == "precedence_join"


def test_prompt_composed_empty_cohort_shape() -> None:
    """An empty cohort composes to empty text and empty fragment_seqs.
    The composer emits this rather than skipping — the record shows the
    turn had no fragments (see sprint 059's observation contract)."""
    c = PromptComposed(text="", fragment_seqs=(), total_tokens=0, strategy="precedence_join")
    raw = msgspec.to_builtins(c)
    assert tuple(raw["fragment_seqs"]) == ()
    assert raw["text"] == ""
    assert raw["total_tokens"] == 0
    # JSON round-trip lands empty list; decode restores empty tuple.
    encoded = msgspec.json.encode(c)
    rebuilt = msgspec.json.decode(encoded, type=PromptComposed)
    assert rebuilt.fragment_seqs == ()


def test_kind_name_constants_match_struct_qualnames() -> None:
    """PROMPT_FRAGMENT and PROMPT_COMPOSED constants match the msgspec
    Struct class names. A drift here would let the topology declare a
    subscription filter on one string and the Struct emit under a different
    name — the exact silent-typo class this constants module exists to
    catch (see the vocabulary.py module docstring)."""
    assert PROMPT_FRAGMENT == PromptFragment.__name__
    assert PROMPT_COMPOSED == PromptComposed.__name__


def test_session_kinds_frozenset_includes_the_two_v02_names() -> None:
    """SESSION_KINDS is the union of every kind the session vocabulary
    covers. Post-v0.2 that is ten names: the eight from v0.1 plus the two
    from v0.2. is_session_kind returns True for each."""
    assert PROMPT_FRAGMENT in SESSION_KINDS
    assert PROMPT_COMPOSED in SESSION_KINDS
    assert is_session_kind(PROMPT_FRAGMENT)
    assert is_session_kind(PROMPT_COMPOSED)
    assert "SessionStarted" in SESSION_KINDS
    assert "UserMessage" in SESSION_KINDS


def test_prompt_source_enum_has_all_v02_plus_interrupt_values() -> None:
    """PromptSource is the StrEnum. Every v0.2 source name plus the
    Phase-8 interrupt member is present; is_prompt_source returns True
    for each; a bogus name returns False."""
    expected = {
        PromptSource.PER_TURN,
        PromptSource.ROLE,
        PromptSource.BUNDLE_METHODOLOGY,
        PromptSource.BUNDLE_PERSONALITY,
        PromptSource.PARENT_CONTEXT,
        PromptSource.TOOLS_SUITE,
        PromptSource.USER_MESSAGE,
        PromptSource.INTERRUPT,
    }
    assert PROMPT_SOURCES == expected
    for source in expected:
        assert is_prompt_source(source)
    assert not is_prompt_source("bogus_source_name")
    assert not is_prompt_source("")


def test_prompt_source_string_values_are_the_documented_values() -> None:
    """The wire representation of a PromptSource member is the string,
    not an enum ordinal. Session-vocabulary.md § I documents each
    string; a drift here would silently rename the source on the wire
    and break every downstream reader keying on the value."""
    assert PromptSource.PER_TURN == "per_turn"
    assert PromptSource.ROLE == "role"
    assert PromptSource.BUNDLE_METHODOLOGY == "bundle_methodology"
    assert PromptSource.BUNDLE_PERSONALITY == "bundle_personality"
    assert PromptSource.PARENT_CONTEXT == "parent_context"
    assert PromptSource.TOOLS_SUITE == "tools_suite"
    assert PromptSource.USER_MESSAGE == "user_message"


def test_session_open_and_turn_scoped_partition_prompt_sources() -> None:
    """SESSION_OPEN_SOURCES and TURN_SCOPED_SOURCES together cover every
    PromptSource member exactly once — the split FragmentCohort enforces.
    role, bundle_methodology, bundle_personality, tools_suite,
    parent_context fire once at RunStarted and appear in every turn's
    PromptComposed. per_turn and user_message fire per turn and appear
    only in that turn's PromptComposed."""
    assert SESSION_OPEN_SOURCES == {
        PromptSource.ROLE,
        PromptSource.BUNDLE_METHODOLOGY,
        PromptSource.BUNDLE_PERSONALITY,
        PromptSource.TOOLS_SUITE,
        PromptSource.PARENT_CONTEXT,
    }
    assert TURN_SCOPED_SOURCES == {
        PromptSource.PER_TURN,
        PromptSource.USER_MESSAGE,
        PromptSource.INTERRUPT,
    }
    assert SESSION_OPEN_SOURCES.isdisjoint(TURN_SCOPED_SOURCES)
    assert SESSION_OPEN_SOURCES | TURN_SCOPED_SOURCES == PROMPT_SOURCES
