from pathlib import Path

from hugo.memory.store import MemoryStore


async def test_all_facts_is_empty_for_a_fresh_store(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()

    assert await store.all_facts() == []


async def test_add_fact_then_all_facts_round_trips(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()

    added = await store.add_fact("Eduard is allergic to peanuts")

    facts = await store.all_facts()
    assert len(facts) == 1
    assert facts[0].id == added.id
    assert facts[0].content == "Eduard is allergic to peanuts"
    assert facts[0].created_at == added.created_at


async def test_facts_are_returned_in_insertion_order(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()

    await store.add_fact("first")
    await store.add_fact("second")
    await store.add_fact("third")

    facts = await store.all_facts()
    assert [f.content for f in facts] == ["first", "second", "third"]


async def test_initialize_creates_parent_directories(tmp_path: Path) -> None:
    nested_path = tmp_path / "nested" / "dirs" / "memory.db"
    store = MemoryStore(nested_path)

    await store.initialize()

    assert nested_path.exists()


async def test_initialize_is_idempotent(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.add_fact("persists across re-init")

    await store.initialize()  # must not wipe existing data or raise

    facts = await store.all_facts()
    assert [f.content for f in facts] == ["persists across re-init"]


async def test_search_facts_returns_matching_facts(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.add_fact("stand-up meeting is at 9:30")
    await store.add_fact("Eduard prefers metric units")

    matches = await store.search_facts(["meeting"], limit=50)

    assert [f.content for f in matches] == ["stand-up meeting is at 9:30"]


async def test_search_facts_returns_nothing_on_a_miss(tmp_path: Path) -> None:
    """A miss is the store's answer, not a fallback — recall_facts owns the
    decision to widen, because it is the layer that knows a query is a hint."""
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.add_fact("stand-up meeting is at 9:30")

    assert await store.search_facts(["dentist"], limit=50) == []


async def test_search_facts_reads_newest_first(tmp_path: Path) -> None:
    """Descending id IS "the newest thing you said wins": the correction was
    saved as a new row, and reading order is what makes it supersede."""
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.add_fact("stand-up meeting is at 9:30")
    await store.add_fact("stand-up meeting is at 9:45")

    matches = await store.search_facts(["standup"], limit=50)

    assert [f.content for f in matches] == [
        "stand-up meeting is at 9:45",
        "stand-up meeting is at 9:30",
    ]


async def test_search_facts_with_no_terms_returns_the_newest_facts(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.add_fact("first")
    await store.add_fact("second")
    await store.add_fact("third")

    matches = await store.search_facts([], limit=50)

    assert [f.content for f in matches] == ["third", "second", "first"]


async def test_search_facts_honours_the_limit(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    for index in range(10):
        await store.add_fact(f"fact number {index}")

    matches = await store.search_facts([], limit=3)

    assert [f.content for f in matches] == ["fact number 9", "fact number 8", "fact number 7"]


async def test_search_facts_matches_generously_across_punctuation(tmp_path: Path) -> None:
    """The wording HUGO wrote down and the wording the user asks back with
    are never the same string: plain LIKE misses "stand-up" for "standup" on
    the hyphen alone, and a filter that hides a fact the user watched HUGO
    save produces "you never told me that"."""
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.add_fact("The stand-up meeting is at 9:30")

    assert await store.search_facts(["standup"], limit=50)
    assert await store.search_facts(["STAND-UP"], limit=50)
    assert await store.search_facts(["930"], limit=50)


async def test_search_facts_matches_any_term_not_all(tmp_path: Path) -> None:
    """Terms are OR-ed: a multi-word question shouldn't need every word of it
    to appear in the same fact."""
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    await store.add_fact("Eduard prefers metric units")

    matches = await store.search_facts(["dentist", "metric"], limit=50)

    assert [f.content for f in matches] == ["Eduard prefers metric units"]


async def test_reopening_the_same_db_path_sees_prior_facts(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    store_a = MemoryStore(db_path)
    await store_a.initialize()
    await store_a.add_fact("saved by the first instance")

    store_b = MemoryStore(db_path)
    await store_b.initialize()

    facts = await store_b.all_facts()
    assert [f.content for f in facts] == ["saved by the first instance"]
