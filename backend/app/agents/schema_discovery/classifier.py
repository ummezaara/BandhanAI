"""Heuristic table and column classification for CRM-like schemas."""

from __future__ import annotations

from collections import Counter


ENTITY_TYPES = ("customer", "order", "order_item", "product", "category")

TABLE_HINTS = {
    "customer": {"customer", "customers", "client", "clients", "user", "users", "account", "accounts"},
    "order": {"order", "orders", "sale", "sales", "invoice", "invoices", "purchase", "purchases"},
    "order_item": {"order_item", "order_items", "line_item", "line_items", "sale_line", "sale_lines", "items"},
    "product": {"product", "products", "sku", "skus", "inventory", "catalog"},
    "category": {"category", "categories", "collection", "collections", "department", "departments"},
}

COLUMN_HINTS = {
    "customer": {"email", "phone", "customer_id", "client_id", "user_id", "first_name", "last_name"},
    "order": {"order_id", "customer_id", "user_id", "total", "amount", "order_date", "purchased_at"},
    "order_item": {"order_id", "product_id", "sku_id", "quantity", "qty", "unit_price", "line_total"},
    "product": {"product_id", "sku", "price", "brand", "category_id", "product_name"},
    "category": {"category_id", "category_name", "parent_id"},
}

CANONICAL_COLUMN_HINTS = {
    "email": {"email", "email_address", "customer_email"},
    "phone": {"phone", "phone_number", "mobile", "mobile_number"},
    "customer_id": {"customer_id", "client_id", "user_id", "account_id"},
    "order_id": {"order_id", "sale_id", "invoice_id", "purchase_id"},
    "product_id": {"product_id", "sku_id", "inventory_id", "item_id"},
    "name": {"name", "full_name", "customer_name", "product_name", "title"},
    "quantity": {"quantity", "qty", "units"},
    "price": {"price", "unit_price", "selling_price", "amount"},
    "total": {"total", "grand_total", "subtotal", "total_amount", "revenue"},
    "created_at": {"created_at", "created", "inserted_at"},
    "ordered_at": {"ordered_at", "order_date", "purchased_at", "sale_date", "date"},
}


def classify_tables(tables: list[dict], columns: list[dict], foreign_keys: list[dict]) -> tuple[dict[str, str], float]:
    """Classify discovered tables into business entities."""
    columns_by_table: dict[str, list[dict]] = {}
    for col in columns:
        columns_by_table.setdefault(col["table"], []).append(col)

    scores: dict[str, Counter] = {}
    for table in tables:
        table_key = table["table"]
        normalized_table = _normalize(table_key.split(".")[-1])
        scores[table_key] = Counter()

        for entity, hints in TABLE_HINTS.items():
            if normalized_table in hints or any(hint in normalized_table for hint in hints):
                scores[table_key][entity] += 3

        for col in columns_by_table.get(table_key, []):
            normalized_col = _normalize(col["column"])
            for entity, hints in COLUMN_HINTS.items():
                if normalized_col in hints or any(hint in normalized_col for hint in hints):
                    scores[table_key][entity] += 1

    _boost_relationship_roles(scores, foreign_keys)

    entity_map: dict[str, str] = {}
    used_tables: set[str] = set()
    for entity in ENTITY_TYPES:
        best_table = None
        best_score = 0
        for table_key, table_scores in scores.items():
            score = table_scores[entity]
            if table_key not in used_tables and score > best_score:
                best_score = score
                best_table = table_key
        if best_table and best_score >= 2:
            entity_map[entity] = best_table
            used_tables.add(best_table)

    confidence = _confidence_from_scores(entity_map, scores)
    return entity_map, confidence


def canonical_column_name(column_name: str) -> str | None:
    normalized = _normalize(column_name)
    for canonical, hints in CANONICAL_COLUMN_HINTS.items():
        if normalized in hints or any(hint in normalized for hint in hints):
            return canonical
    return None


def _boost_relationship_roles(scores: dict[str, Counter], foreign_keys: list[dict]) -> None:
    outgoing_counts = Counter(fk["from_table"] for fk in foreign_keys)
    incoming_counts = Counter(fk["to_table"] for fk in foreign_keys)

    for table_key, count in outgoing_counts.items():
        if count >= 2:
            scores.setdefault(table_key, Counter())["order_item"] += 2
        elif count == 1:
            scores.setdefault(table_key, Counter())["order"] += 1

    for table_key, count in incoming_counts.items():
        if count >= 1:
            scores.setdefault(table_key, Counter())["customer"] += 1
            scores.setdefault(table_key, Counter())["product"] += 1


def _confidence_from_scores(entity_map: dict[str, str], scores: dict[str, Counter]) -> float:
    if not entity_map:
        return 0.0
    found = len(entity_map) / len(ENTITY_TYPES)
    strength = 0.0
    for entity, table_key in entity_map.items():
        strength += min(scores[table_key][entity] / 6, 1.0)
    return round((found * 0.45) + ((strength / len(entity_map)) * 0.55), 2)


def _normalize(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
