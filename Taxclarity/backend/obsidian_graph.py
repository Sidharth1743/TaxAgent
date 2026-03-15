from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any


VAULT_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "obsidian_vault")


@dataclass(frozen=True)
class ObsidianConcept:
    slug: str
    label: str
    node_type: str


@dataclass(frozen=True)
class TurnRecord:
    node_id: str
    label: str
    node_type: str
    role: str
    turn_id: str
    session_id: str
    text: str
    concepts: list[ObsidianConcept]


CONCEPT_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(?:us|u\.s\.|usa|united states)\b", re.I), "United States", "Jurisdiction"),
    (re.compile(r"\bindia\b", re.I), "India", "Jurisdiction"),
    (re.compile(r"\bkerala\b", re.I), "Kerala", "Jurisdiction"),
    (re.compile(r"\brnor\b", re.I), "RNOR", "Concept"),
    (re.compile(r"\bdtaa\b", re.I), "DTAA", "Concept"),
    (re.compile(r"\bltcg\b|capital gains", re.I), "Capital Gains", "Concept"),
    (re.compile(r"\bresident\b|\bresidency\b", re.I), "Residency Status", "Concept"),
    (re.compile(r"\bnri\b", re.I), "NRI Status", "Concept"),
    (re.compile(r"\bnre\b", re.I), "NRE Account", "TaxEntity"),
    (re.compile(r"\bfd\b|\bfixed deposit", re.I), "Fixed Deposits", "TaxEntity"),
    (re.compile(r"\bibkr\b|interactive brokers", re.I), "IBKR Portfolio", "TaxEntity"),
    (re.compile(r"\bmutual funds?\b", re.I), "Mutual Funds", "TaxEntity"),
    (re.compile(r"\bequit(?:y|ies)\b|\bstocks?\b", re.I), "Equity Holdings", "TaxEntity"),
    (re.compile(r"\binvest(?:ment|ments)?\b|\bportfolio\b", re.I), "Investment Portfolio", "TaxEntity"),
    (re.compile(r"\bretir(?:e|ement|ing)\b", re.I), "Retirement Plan", "Concept"),
    (re.compile(r"\bfamily\b|\bwife\b|\bspouse\b|\bson\b|\bdaughter\b|\bchild\b", re.I), "Family Relocation", "Concept"),
    (re.compile(r"\bform\s*67\b", re.I), "Form 67", "TaxForm"),
    (re.compile(r"\bitr\b", re.I), "Income Tax Return", "TaxForm"),
]


AMOUNT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b1\s*million\b|\$ ?1m\b|\$ ?1,?000,?000\b", re.I), "USD 1M Portfolio"),
    (re.compile(r"₹\s*8\s*crore|\b8\s*crore\b", re.I), "INR 8 Crore Holdings"),
]


TIMELINE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b2028\b"), "Return Timeline 2028"),
    (re.compile(r"\b10\s+years?\b", re.I), "10 Year US Stay"),
]


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:72] or "node"


def _sanitize_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _user_dir(user_id: str) -> str:
    return os.path.join(VAULT_ROOT, "users", user_id)


def _session_dir(user_id: str, session_id: str) -> str:
    return os.path.join(_user_dir(user_id), "sessions", session_id)


def _concepts_dir(user_id: str) -> str:
    return os.path.join(_user_dir(user_id), "concepts")


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _extract_concepts(text: str) -> list[ObsidianConcept]:
    concepts: dict[str, ObsidianConcept] = {}
    clean = _sanitize_text(text)
    if not clean:
        return []

    for pattern, label, node_type in CONCEPT_PATTERNS:
        if pattern.search(clean):
            slug = f"{node_type.lower()}-{_slugify(label)}"
            concepts[slug] = ObsidianConcept(slug=slug, label=label, node_type=node_type)

    for pattern, label in AMOUNT_PATTERNS:
        if pattern.search(clean):
            slug = f"taxentity-{_slugify(label)}"
            concepts[slug] = ObsidianConcept(slug=slug, label=label, node_type="TaxEntity")

    for pattern, label in TIMELINE_PATTERNS:
        if pattern.search(clean):
            slug = f"concept-{_slugify(label)}"
            concepts[slug] = ObsidianConcept(slug=slug, label=label, node_type="Concept")

    if re.search(r"\bmy wife\b|\bmy son\b|\bour son\b", clean, re.I):
        slug = "concept-family-of-three"
        concepts[slug] = ObsidianConcept(slug=slug, label="Family of Three", node_type="Concept")

    if re.search(r"\bnew to me\b|\bonly dealt with us taxes\b|\bdon't know\b|\bhonestly no\b", clean, re.I):
        slug = "ambiguity-indian-tax-familiarity-low"
        concepts[slug] = ObsidianConcept(slug=slug, label="Low Indian Tax Familiarity", node_type="Ambiguity")

    return list(concepts.values())


def _turn_label(role: str, text: str) -> str:
    clean = _sanitize_text(text)
    if not clean:
        return "Turn"
    short = clean[:72].rstrip()
    if len(clean) > 72:
        short += "…"
    return short


def persist_turn_to_obsidian(*, user_id: str, session_id: str, role: str, text: str, turn_id: str) -> None:
    clean = _sanitize_text(text)
    if not clean:
        return

    os.makedirs(_session_dir(user_id, session_id), exist_ok=True)
    os.makedirs(_concepts_dir(user_id), exist_ok=True)

    user_note = os.path.join(_user_dir(user_id), "user.md")
    session_note = os.path.join(_session_dir(user_id, session_id), "session.md")

    _write_file(
        user_note,
        "\n".join(
            [
                "---",
                "type: User",
                f"user_id: {user_id}",
                "---",
                "",
                "# You",
                "",
            ]
        ),
    )

    _write_file(
        session_note,
        "\n".join(
            [
                "---",
                "type: Session",
                f"user_id: {user_id}",
                f"session_id: {session_id}",
                "---",
                "",
                f"# Session {session_id}",
                "",
            ]
        ),
    )

    concepts = _extract_concepts(clean)
    for concept in concepts:
        concept_path = os.path.join(_concepts_dir(user_id), f"{concept.slug}.md")
        _write_file(
            concept_path,
            "\n".join(
                [
                    "---",
                    f"type: {concept.node_type}",
                    f"user_id: {user_id}",
                    f"slug: {concept.slug}",
                    "---",
                    "",
                    f"# {concept.label}",
                    "",
                ]
            ),
        )

    turn_slug = f"{role}-{turn_id}"
    role_type = "Query" if role == "user" else "Resolution"
    links = [f"[[user-{user_id}|You]]"]
    links.extend(f"[[{concept.slug}|{concept.label}]]" for concept in concepts)

    turn_path = os.path.join(_session_dir(user_id, session_id), f"{turn_slug}.md")
    _write_file(
        turn_path,
        "\n".join(
            [
                "---",
                f"type: {role_type}",
                f"role: {role}",
                f"user_id: {user_id}",
                f"session_id: {session_id}",
                f"turn_id: {turn_id}",
                "---",
                "",
                f"# {_turn_label(role, clean)}",
                "",
                clean,
                "",
                "## Links",
                *links,
                "",
            ]
        ),
    )


def _read_frontmatter(text: str) -> dict[str, str]:
    match = re.search(r"^---\n(.*?)\n---", text, flags=re.S)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def _read_markdown_body(text: str) -> str:
    stripped = re.sub(r"^---\n.*?\n---\n?", "", text, flags=re.S).strip()
    stripped = re.sub(r"^#\s+.+$", "", stripped, flags=re.M).strip()
    stripped = re.split(r"\n##\s+Links\b", stripped, maxsplit=1)[0].strip()
    return _sanitize_text(stripped)


def _load_turn_records(user_id: str, session_id: str | None) -> list[TurnRecord]:
    records: list[TurnRecord] = []
    sessions_root = os.path.join(_user_dir(user_id), "sessions")
    if not os.path.isdir(sessions_root):
        return records

    for current_root, _, files in os.walk(sessions_root):
        for name in sorted(files):
            if not name.endswith(".md") or name == "session.md":
                continue
            path = os.path.join(current_root, name)
            text = open(path, "r", encoding="utf-8").read()
            meta = _read_frontmatter(text)
            if not meta.get("turn_id") or not meta.get("role"):
                continue
            if session_id and meta.get("session_id") != session_id:
                continue
            role = meta["role"]
            node_type = meta.get("type", "Query" if role == "user" else "Resolution")
            body = _read_markdown_body(text)
            if not body:
                continue
            turn_id = meta["turn_id"]
            records.append(
                TurnRecord(
                    node_id=f"{node_type.lower()}:{turn_id}",
                    label=_turn_label(role, body),
                    node_type=node_type,
                    role=role,
                    turn_id=turn_id,
                    session_id=meta.get("session_id", ""),
                    text=body,
                    concepts=_extract_concepts(body),
                )
            )

    records.sort(key=lambda item: item.turn_id)
    return records


def build_obsidian_graph(user_id: str, session_id: str | None = None) -> dict[str, Any]:
    root = _user_dir(user_id)
    if not os.path.isdir(root):
        return {"nodes": [], "edges": []}

    nodes: dict[str, dict[str, str]] = {}
    edges: set[tuple[str, str, str]] = set()
    user_node = f"user:{user_id}"

    def ensure_node(node_id: str, label: str, node_type: str) -> None:
        nodes[node_id] = {"id": node_id, "label": label, "type": node_type, "color": ""}

    ensure_node(user_node, "You", "User")

    turn_records = _load_turn_records(user_id, session_id)
    if not turn_records:
        return {"nodes": [], "edges": []}

    previous_turn: TurnRecord | None = None
    last_query_node_id: str | None = None

    for record in turn_records:
        ensure_node(record.node_id, record.label, record.node_type)

        if record.role == "user":
            edges.add((user_node, record.node_id, "ASKED"))
            last_query_node_id = record.node_id
        else:
            if last_query_node_id:
                edges.add((last_query_node_id, record.node_id, "ANSWERED_BY"))
            else:
                edges.add((user_node, record.node_id, "RECEIVED"))

        if previous_turn:
            edges.add((previous_turn.node_id, record.node_id, "NEXT"))

        for concept in record.concepts:
            concept_node_id = f"{concept.node_type.lower()}:{concept.slug}"
            ensure_node(concept_node_id, concept.label, concept.node_type)
            edge_type = "MENTIONS" if record.role == "user" else "EXPLAINS"
            edges.add((record.node_id, concept_node_id, edge_type))

            if concept.node_type == "Jurisdiction" and record.role == "user":
                edges.add((user_node, concept_node_id, "LOCATED_IN"))
            if concept.label == "Family Relocation" and record.role == "user":
                edges.add((user_node, concept_node_id, "HAS_CONTEXT"))
            if concept.label in {"Retirement Plan", "Return Timeline 2028", "10 Year US Stay"} and record.role == "user":
                edges.add((user_node, concept_node_id, "PLANS"))
            if concept.node_type == "TaxEntity" and record.role == "user":
                edges.add((user_node, concept_node_id, "HOLDS"))

        previous_turn = record

    return {
        "nodes": list(nodes.values()),
        "edges": [{"from": src, "to": dst, "type": edge_type} for src, dst, edge_type in sorted(edges)],
    }
