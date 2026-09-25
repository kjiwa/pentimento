---
name: Skip list range query
overview: Add a half-open range query on SkipList that returns keys in [lo, hi) in ascending order, implemented by a logarithmic search then a level-0 walk, plus JUnit coverage for bounds and empty cases.
isProject: false
todos:
  - id: add-range-method
    content: Add SkipList.range(K lo, K hi) with NPE, empty [lo,hi), search + level-0 walk
    status: pending
  - id: add-range-tests
    content: Add SkipListTest cases for bounds, missing keys, empty/null, order, optional TreeMap check
    status: pending
---

# Skip list range query

## API

Add a public method on [`SkipList.java`](app/src/main/java/SkipList.java) (not on `Map`, so tests construct `SkipList` rather than `Map` for this method):

```java
public List<K> range(K lo, K hi)
```

Contract, matching the rest of this class:

- Half-open interval **[lo, hi)**: include keys `>= lo` and `< hi`.
- Return a **snapshot** `ArrayList` of keys in ascending order (not a live view).
- Null `lo` or `hi` throws `NullPointerException` (same as `get`/`put`/`remove`).
- If `lo.compareTo(hi) >= 0`, return an empty list (empty interval, no exception).
- Empty map or a range that misses all keys returns an empty list.

Do not update [`README.md`](README.md); it does not document individual methods.

## Implementation

Reuse the existing downward search used by `put` / `remove` / `findNode`: after walking from `level - 1` to `0` with `compareTo(lo) < 0`, `cur.forward.get(0)` is the first node with key `>= lo` (or `tail`).

Then walk **level 0 only** until `tail` or `key.compareTo(hi) >= 0`, collecting keys into an `ArrayList`. Expected time is O(log n + k).

Keep the search local to `range` (or a small private helper used only by `range`). Do not refactor `put`/`remove`/`findNode` unless it is a trivial extract; those methods already work.

```mermaid
flowchart LR
  start[head] --> search["search for first key >= lo"]
  search --> walk["walk level 0 while key < hi"]
  walk --> keys["List of keys"]
```

## Tests

Add tests in [`SkipListTest.java`](app/src/test/java/SkipListTest.java), same style (`skipListRange...`, JUnit 5, `assertEquals` / `assertThrows`).

Cover:

- Inclusive `lo`, exclusive `hi` (e.g. keys `1..5`, `range(2, 5)` → `[2, 3, 4]`).
- `lo` / `hi` not present (e.g. keys `1, 3, 5`, `range(2, 5)` → `[3]`).
- Full span, empty map, range entirely below or above all keys.
- Empty interval: `lo.equals(hi)` and `lo > hi`.
- Insertion order does not affect result order.
- Null `lo` or `hi` throws `NPE`.
- Optional: after random inserts, `range(lo, hi)` matches `new ArrayList<>(new TreeMap<>(map).subMap(lo, hi).keySet())` when `lo < hi`.

No Gradle/build changes; run existing tests plus the new ones.