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


async def test_reopening_the_same_db_path_sees_prior_facts(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    store_a = MemoryStore(db_path)
    await store_a.initialize()
    await store_a.add_fact("saved by the first instance")

    store_b = MemoryStore(db_path)
    await store_b.initialize()

    facts = await store_b.all_facts()
    assert [f.content for f in facts] == ["saved by the first instance"]
