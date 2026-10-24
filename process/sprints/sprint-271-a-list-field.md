# Sprint 271 — A list field in a process Producer's schema file

```yaml
---
id: 271
status: done
phase: 1
pass_kind: functional
asked: 2026-10-24 (w2m, on branch w2m; w2m Sprint 126, the vocabulary generator)
---
```

## why

w2m generates its schema file from its vocabulary, and eleven of the vocabulary's harness-plane fields are lists:
`list<id>`, `list<contract_id>`, `list<u64>`, `list<enum:lifecycle_step>` (w2m `signals/0.9.json`, for example
HYPOTHESIS_RESOLVED.deciding_evidence_ids, DISTRIBUTION_RESOLVED.depot_ids). The schema file of K270 has no list type,
so those eleven tags could not be declared.

## scope

`schemas_from_file` takes `{"type": "list", "items": {spec}}`. The items' spec is any field spec but an optional one,
read by the same function, so an item has the same constraints a field has. The field becomes `tuple[item, ...]`;
`min_length` on the list bounds its length (msgspec `Meta` applies it to sequences). A list without an `items` spec,
or with optional items, is refused when the file is read.

## checks

- A list field reaches the record item for item, an empty list included.
- A value that is not a list, an item too short, an item outside its enum, an item below `ge`, and a list below its
  `min_length` each fail the Producer at its line, the failure naming the field or the item's index.
- A list with no `items`, with `items` not a spec, or with optional items is refused by `schemas_from_file`.
- `scripts/ci_local.sh` exits 0, but for K270's two named failures on the clean HEAD.

## result

- `schemas_from_file` takes `{"type": "list", "items": {spec}}`; the items' spec is read by the same function, so an
  item carries a field's constraints; the field is `types.GenericAlias(tuple, (item, ...))` (mypy refuses
  `tuple[...]` subscripted with a value). `min_length` on the list bounds its length.
- 9 tests added (`tests/test_process_producer.py`, 25 in all): a list reaching the record item for item, an empty one
  included; five bad lists failing the Producer at line 2, naming `evidence_ids`, `evidence_ids[1]`, `steps[0]`,
  `depot_ids[0]`, `depot_ids`; three lists without an items spec refused when the file is read.
- `scripts/ci_local.sh`: py3.12 and py3.13 fail on the same two tests as K270 and the clean HEAD 3c0542ac
  (`test_the_committed_api_page_is_current`, `test_realmodel_background_bash_103`), nothing else; conformance 15
  passed, 0 failed, on each.
- w2m's use (its Sprint 126): the schema file generated from its vocabulary, 52 kinds, eleven with list fields; every
  kind at sample values on a record that replays at Level 2.
