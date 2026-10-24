"""Repositorios y storage en memoria con la misma interfaz que los reales."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.db.supabase import NotFound, child_row


@dataclass
class MemoryProducts:
    rows: dict[str, dict] = field(default_factory=dict)

    def add(self, **row) -> dict:
        row = {
            "id": str(uuid4()),
            "status": "outline_ready",
            "tone": None,
            "audience_override": None,
            **row,
        }
        self.rows[row["id"]] = row
        return row

    async def get(self, product_id: UUID, user_id: UUID | None = None) -> dict:
        row = self.rows.get(str(product_id))
        if not row or (user_id and row["user_id"] != str(user_id)):
            raise NotFound(str(product_id))
        return row

    async def update(self, product_id: UUID, **values) -> None:
        self.rows[str(product_id)].update(values)

    async def create_child(self, parent: dict, **overrides) -> dict:
        return self.add(**child_row(parent, **overrides))


@dataclass
class MemoryItems:
    rows: dict[str, dict] = field(default_factory=dict)

    async def replace_from_outline(self, product_id, user_id, outline) -> list[dict]:
        self.rows = {k: v for k, v in self.rows.items() if v["product_id"] != str(product_id)}
        created = []
        for role, items in (
            ("main", [outline.main]),
            ("order_bump", outline.order_bumps),
            ("bonus", outline.bonuses),
        ):
            for order, item in enumerate(items):
                row = {
                    "id": str(uuid4()),
                    "product_id": str(product_id),
                    "role": role,
                    "format": item.format.value,
                    "title": item.title,
                    "order": order,
                    "status": "pending",
                }
                self.rows[row["id"]] = row
                created.append(row)
        return created

    async def list_for_product(self, product_id) -> list[dict]:
        rows = [r for r in self.rows.values() if r["product_id"] == str(product_id)]
        return sorted(rows, key=lambda r: (r["role"], r["order"]))

    async def insert_many(self, rows: list[dict]) -> list[dict]:
        created = []
        for row in rows:
            row = {"id": str(uuid4()), "status": "pending", **row}
            self.rows[row["id"]] = row
            created.append(row)
        return created

    async def update(self, item_id, **values) -> None:
        self.rows[str(item_id)].update(values)


@dataclass
class MemoryFiles:
    rows: dict[str, dict] = field(default_factory=dict)

    async def add(self, *, item_id, **row) -> dict:
        row = {
            "id": str(uuid4()),
            "product_item_id": item_id,  # mismo nombre de columna que en Postgres
            "remote_status": "pending",
            "upload_attempts": 0,
            "remote_id": None,
            "remote_url": None,
            **{k: str(v) if isinstance(v, UUID) else v for k, v in row.items()},
        }
        self.rows[row["id"]] = row
        return row

    async def delete_for_product(self, product_id) -> None:
        self.rows = {k: v for k, v in self.rows.items() if v["product_id"] != str(product_id)}

    async def list_for_product(self, product_id) -> list[dict]:
        return [r for r in self.rows.values() if r["product_id"] == str(product_id)]

    async def update(self, file_id, **values) -> None:
        self.rows[str(file_id)].update(values)

    async def unsynced(self, max_attempts: int, user_id=None) -> list[dict]:
        return [
            {"product_id": r["product_id"], "user_id": r["user_id"]}
            for r in self.rows.values()
            if r["remote_status"] in ("pending", "failed")
            and r["upload_attempts"] < max_attempts
            and r["file_type"] != "zip"
            and (user_id is None or r["user_id"] == str(user_id))
        ]

    async def delete_ids(self, ids: list[str]) -> None:
        for file_id in ids:
            self.rows.pop(file_id, None)

    async def get(self, file_id, user_id) -> dict:
        row = self.rows.get(str(file_id))
        if not row or row["user_id"] != str(user_id):
            raise NotFound(str(file_id))
        return row


@dataclass
class MemoryJobs:
    rows: dict[str, dict] = field(default_factory=dict)

    async def enqueue(self, *, user_id, kind, payload, product_id=None, batch_id=None) -> dict:
        row = {
            "id": str(uuid4()),
            "product_id": str(product_id) if product_id else None,
            "batch_id": str(batch_id) if batch_id else None,
            "user_id": str(user_id),
            "kind": kind,
            "payload": payload,
            "status": "queued",
            "progress": {},
        }
        self.rows[row["id"]] = row
        return row

    async def claim(self) -> dict | None:
        for row in self.rows.values():
            if row["status"] == "queued":
                row["status"] = "running"
                return row
        return None

    async def update(self, job_id, **values) -> None:
        self.rows[str(job_id)].update(values)

    async def active_for_product(self, product_id, kind: str | None = None) -> list[dict]:
        return [
            r
            for r in self.rows.values()
            if r["product_id"] == str(product_id)
            and r["status"] in ("queued", "running")
            and (kind is None or r["kind"] == kind)
        ]

    async def active_for_batch(self, batch_id, kind: str | None = None) -> list[dict]:
        return [
            r
            for r in self.rows.values()
            if r.get("batch_id") == str(batch_id)
            and r["status"] in ("queued", "running")
            and (kind is None or r["kind"] == kind)
        ]


@dataclass
class MemoryAdBatches:
    rows: dict[str, dict] = field(default_factory=dict)

    async def create(self, row: dict) -> dict:
        row = {"id": str(uuid4()), "created_at": "2026-01-01T00:00:00Z", **row}
        self.rows[row["id"]] = row
        return row

    async def get(self, batch_id, user_id=None) -> dict:
        row = self.rows.get(str(batch_id))
        if not row or (user_id and row["user_id"] != str(user_id)):
            raise NotFound(str(batch_id))
        return row

    async def update(self, batch_id, **values) -> None:
        self.rows[str(batch_id)].update(values)

    async def list_for_user(self, user_id, limit: int = 50) -> list[dict]:
        return [r for r in self.rows.values() if r["user_id"] == str(user_id)][:limit]

    async def list_published(self, limit: int = 200) -> list[dict]:
        return [
            r
            for r in self.rows.values()
            if (r.get("meta") or {}).get("status") in ("done", "partial")
        ][:limit]


@dataclass
class MemoryAdCreatives:
    rows: dict[str, dict] = field(default_factory=dict)

    async def insert_many(self, rows: list[dict]) -> list[dict]:
        created = []
        for row in rows:
            row = {
                "id": str(uuid4()),
                "status": "planned",
                "storage_path": None,
                "created_at": "2026-01-01T00:00:00Z",
                **row,
            }
            self.rows[row["id"]] = row
            created.append(row)
        return created

    async def list_for_batch(self, batch_id) -> list[dict]:
        return [r for r in self.rows.values() if r["batch_id"] == str(batch_id)]

    async def get(self, creative_id, user_id) -> dict:
        row = self.rows.get(str(creative_id))
        if not row or row["user_id"] != str(user_id):
            raise NotFound(str(creative_id))
        return row

    async def update(self, creative_id, **values) -> None:
        self.rows[str(creative_id)].update(values)

    async def delete_for_batch(self, batch_id) -> None:
        self.rows = {k: v for k, v in self.rows.items() if v["batch_id"] != str(batch_id)}

    async def list_for_user(self, user_id, limit: int = 5000) -> list[dict]:
        return [r for r in self.rows.values() if r["user_id"] == str(user_id)][:limit]


@dataclass
class MemoryAdProofs:
    rows: dict[str, dict] = field(default_factory=dict)

    async def list(self, user_id, product_id=None) -> list[dict]:
        return [
            r
            for r in self.rows.values()
            if r["user_id"] == str(user_id)
            and (r["product_id"] is None or r["product_id"] == str(product_id))
        ]

    async def add(self, row: dict) -> dict:
        row = {"id": str(uuid4()), **row}
        self.rows[row["id"]] = row
        return row

    async def delete(self, proof_id, user_id) -> None:
        row = self.rows.get(str(proof_id))
        if row and row["user_id"] == str(user_id):
            del self.rows[str(proof_id)]


@dataclass
class MemoryStorage:
    name = "memory"
    objects: dict[str, bytes] = field(default_factory=dict)

    async def upload(self, path: str, data: bytes, mime: str) -> str:
        self.objects[path] = data
        return path

    async def signed_url(self, path: str, expires_in: int) -> str:
        return f"https://storage.test/{path}?ttl={expires_in}"

    async def download(self, path: str) -> bytes:
        return self.objects[path]

    async def delete(self, paths: list[str]) -> None:
        for path in paths:
            self.objects.pop(path, None)


@dataclass
class MemoryConnections:
    """Misma interfaz que ConnectionRepo; guarda los tokens tal cual los recibe (cifrados)."""

    rows: dict[tuple[str, str], dict] = field(default_factory=dict)

    async def get(self, user_id, provider: str) -> dict | None:
        return self.rows.get((str(user_id), provider))

    async def save(
        self, *, user_id, provider, account_label, access_token_enc, refresh_token_enc, expires_at
    ) -> None:
        self.rows[(str(user_id), provider)] = {
            "user_id": str(user_id),
            "provider": provider,
            "account_label": account_label,
            "access_token_enc": access_token_enc,
            "refresh_token_enc": refresh_token_enc,
            "expires_at": expires_at,
        }

    async def delete(self, user_id, provider: str) -> None:
        self.rows.pop((str(user_id), provider), None)


@dataclass
class MemoryImageCache:
    rows: dict[str, dict] = field(default_factory=dict)

    async def get(self, scene_hash: str) -> dict | None:
        return self.rows.get(scene_hash)

    async def put(self, row: dict) -> None:
        self.rows[row["scene_hash"]] = row


@dataclass
class MemoryProviderUsage:
    rows: dict[tuple[str, str], dict] = field(default_factory=dict)

    async def get(self, provider: str, day) -> dict | None:
        return self.rows.get((provider, str(day)))

    async def add(self, provider: str, day, *, requests: int, cost_usd: float) -> None:
        row = self.rows.setdefault(
            (provider, str(day)), {"requests": 0, "cost_usd": 0.0, "exhausted": False}
        )
        row["requests"] += requests
        row["cost_usd"] += cost_usd

    async def mark_exhausted(self, provider: str, day) -> None:
        row = self.rows.setdefault(
            (provider, str(day)), {"requests": 0, "cost_usd": 0.0, "exhausted": False}
        )
        row["exhausted"] = True


@dataclass
class MemoryAdResults:
    rows: dict[tuple[str, str], dict] = field(default_factory=dict)

    async def upsert_many(self, rows: list[dict]) -> int:
        for row in rows:
            key = (row["creative_id"], str(row["day"]))
            self.rows[key] = {"id": str(uuid4()), **self.rows.get(key, {}), **row}
        return len(rows)

    async def list_for_user(self, user_id, limit: int = 20000) -> list[dict]:
        return [r for r in self.rows.values() if r["user_id"] == str(user_id)][:limit]

    async def list_for_creative(self, creative_id, user_id) -> list[dict]:
        return [
            r
            for r in self.rows.values()
            if r["creative_id"] == str(creative_id) and r["user_id"] == str(user_id)
        ]

    async def get(self, result_id, user_id) -> dict:
        for r in self.rows.values():
            if r["id"] == str(result_id) and r["user_id"] == str(user_id):
                return r
        raise NotFound(str(result_id))

    async def delete(self, result_id, user_id) -> None:
        self.rows = {k: v for k, v in self.rows.items() if v["id"] != str(result_id)}
