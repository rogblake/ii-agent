"""Tests for TypedEntityCache — generic Pydantic-aware cache wrapper.

Uses MemoryEntityCache as the backing store so no Redis is needed.
"""

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

import pytest
from pydantic import BaseModel, ConfigDict

from ii_agent.core.redis.cache import MemoryEntityCache, TypedEntityCache


# ── Test models ──────────────────────────────────────────────────────────────


class Status(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class SimpleModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class FullModel(BaseModel):
    """Model with UUID, datetime, optional, and enum fields."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    status: Status
    created_at: datetime
    description: Optional[str] = None
    score: float = 0.0


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def memory_cache() -> MemoryEntityCache:
    return MemoryEntityCache(namespace="test")


@pytest.fixture
def typed_cache(memory_cache: MemoryEntityCache) -> TypedEntityCache[SimpleModel]:
    return TypedEntityCache(cache=memory_cache, model=SimpleModel)


@pytest.fixture
def full_typed_cache(memory_cache: MemoryEntityCache) -> TypedEntityCache[FullModel]:
    return TypedEntityCache(cache=memory_cache, model=FullModel)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def sample_model(sample_id: uuid.UUID) -> SimpleModel:
    return SimpleModel(id=sample_id, name="test-entity")


@pytest.fixture
def full_model(sample_id: uuid.UUID) -> FullModel:
    return FullModel(
        id=sample_id,
        name="full-entity",
        status=Status.ACTIVE,
        created_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        description="A test entity",
        score=42.5,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestTypedEntityCacheGet:
    @pytest.mark.asyncio
    async def test_get_returns_none_on_miss(self, typed_cache: TypedEntityCache[SimpleModel]):
        result = await typed_cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_deserializes_to_model_instance(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
        sample_model: SimpleModel,
    ):
        await typed_cache.set("key1", sample_model)
        result = await typed_cache.get("key1")

        assert result is not None
        assert isinstance(result, SimpleModel)

    @pytest.mark.asyncio
    async def test_get_returns_correct_values(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
        sample_model: SimpleModel,
        sample_id: uuid.UUID,
    ):
        await typed_cache.set("key1", sample_model)
        result = await typed_cache.get("key1")

        assert result is not None
        assert result.id == sample_id
        assert result.name == "test-entity"


class TestTypedEntityCacheSet:
    @pytest.mark.asyncio
    async def test_set_returns_true(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
        sample_model: SimpleModel,
    ):
        ok = await typed_cache.set("key1", sample_model)
        assert ok is True

    @pytest.mark.asyncio
    async def test_set_serializes_uuid_to_string(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
        sample_model: SimpleModel,
        memory_cache: MemoryEntityCache,
    ):
        """model_dump(mode='json') converts UUID to str for JSON compat."""
        await typed_cache.set("key1", sample_model)
        raw = await memory_cache.get("key1")

        assert raw is not None
        assert isinstance(raw["id"], str)
        assert raw["id"] == "12345678-1234-5678-1234-567812345678"

    @pytest.mark.asyncio
    async def test_set_with_ttl(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
        sample_model: SimpleModel,
    ):
        ok = await typed_cache.set("key1", sample_model, ttl=60)
        assert ok is True
        result = await typed_cache.get("key1")
        assert result is not None


class TestTypedEntityCacheRoundTrip:
    @pytest.mark.asyncio
    async def test_uuid_roundtrip(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
        sample_model: SimpleModel,
        sample_id: uuid.UUID,
    ):
        await typed_cache.set("key1", sample_model)
        result = await typed_cache.get("key1")

        assert result is not None
        assert isinstance(result.id, uuid.UUID)
        assert result.id == sample_id

    @pytest.mark.asyncio
    async def test_datetime_roundtrip(
        self,
        full_typed_cache: TypedEntityCache[FullModel],
        full_model: FullModel,
    ):
        await full_typed_cache.set("key1", full_model)
        result = await full_typed_cache.get("key1")

        assert result is not None
        assert isinstance(result.created_at, datetime)
        assert result.created_at == full_model.created_at

    @pytest.mark.asyncio
    async def test_enum_roundtrip(
        self,
        full_typed_cache: TypedEntityCache[FullModel],
        full_model: FullModel,
    ):
        await full_typed_cache.set("key1", full_model)
        result = await full_typed_cache.get("key1")

        assert result is not None
        assert result.status == Status.ACTIVE
        assert isinstance(result.status, Status)

    @pytest.mark.asyncio
    async def test_optional_field_with_value(
        self,
        full_typed_cache: TypedEntityCache[FullModel],
        full_model: FullModel,
    ):
        await full_typed_cache.set("key1", full_model)
        result = await full_typed_cache.get("key1")

        assert result is not None
        assert result.description == "A test entity"

    @pytest.mark.asyncio
    async def test_optional_field_none(
        self,
        full_typed_cache: TypedEntityCache[FullModel],
        sample_id: uuid.UUID,
    ):
        model = FullModel(
            id=sample_id,
            name="no-desc",
            status=Status.COMPLETED,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            description=None,
        )
        await full_typed_cache.set("key1", model)
        result = await full_typed_cache.get("key1")

        assert result is not None
        assert result.description is None

    @pytest.mark.asyncio
    async def test_float_field_roundtrip(
        self,
        full_typed_cache: TypedEntityCache[FullModel],
        full_model: FullModel,
    ):
        await full_typed_cache.set("key1", full_model)
        result = await full_typed_cache.get("key1")

        assert result is not None
        assert result.score == 42.5


class TestTypedEntityCacheDelegation:
    @pytest.mark.asyncio
    async def test_evict(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
        sample_model: SimpleModel,
    ):
        await typed_cache.set("key1", sample_model)
        assert await typed_cache.get("key1") is not None

        ok = await typed_cache.evict("key1")
        assert ok is True
        assert await typed_cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_evict_nonexistent_returns_false(
        self, typed_cache: TypedEntityCache[SimpleModel]
    ):
        ok = await typed_cache.evict("nonexistent")
        assert ok is False

    @pytest.mark.asyncio
    async def test_exists_true(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
        sample_model: SimpleModel,
    ):
        await typed_cache.set("key1", sample_model)
        assert await typed_cache.exists("key1") is True

    @pytest.mark.asyncio
    async def test_exists_false(self, typed_cache: TypedEntityCache[SimpleModel]):
        assert await typed_cache.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_multiple_keys_independent(
        self,
        typed_cache: TypedEntityCache[SimpleModel],
    ):
        m1 = SimpleModel(id=uuid.uuid4(), name="first")
        m2 = SimpleModel(id=uuid.uuid4(), name="second")

        await typed_cache.set("k1", m1)
        await typed_cache.set("k2", m2)

        r1 = await typed_cache.get("k1")
        r2 = await typed_cache.get("k2")

        assert r1 is not None and r1.name == "first"
        assert r2 is not None and r2.name == "second"

        await typed_cache.evict("k1")
        assert await typed_cache.get("k1") is None
        assert await typed_cache.get("k2") is not None
