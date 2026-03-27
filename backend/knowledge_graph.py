import os
import re
import logging
from typing import List, Dict, Optional
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",  "bolt://neo4j:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    raise EnvironmentError(
        "NEO4J_PASSWORD environment variable is not set. "
        "Add it to your k8s secret: documind-secrets"
    )

# ── Cypher templates ──────────────────────────────────────────────────────────

NODE_UPSERT = """
MERGE (n:{node_type} {{name: $name}})
ON CREATE SET n.id = $id, n.created_at = timestamp(),
              n.document_id = $document_id, n.chunk_id = $chunk_id
ON MATCH SET  n.updated_at = timestamp()
SET n += $properties
"""

EDGE_UPSERT = """
MATCH (a {{name: $source_name}})
MATCH (b {{name: $target_name}})
MERGE (a)-[r:{edge_type}]->(b)
ON CREATE SET r.created_at = timestamp(),
              r.document_id = $document_id, r.chunk_id = $chunk_id
"""

# Safe list-merge for aliases — never overwrites existing aliases from prior ingests.
# Only runs for ALIAS_ENABLED_TYPES (Person, Organization).
# Pure Cypher list comprehension — no APOC dependency required.
ALIAS_UPSERT = """
MATCH (n {name: $name})
SET n.aliases =
  CASE
    WHEN n.aliases IS NULL THEN $aliases
    ELSE n.aliases + [x IN $aliases WHERE NOT x IN n.aliases]
  END
"""

# Merge provenance edge — written when a node is absorbed into a canonical.
# method:     how the merge was decided (nameparser_guard / topology / rapidfuzz / llm)
# confidence: blocked / uncertain / confirmed
MERGED_INTO_UPSERT = """
MATCH (a {name: $absorbed_name})
MATCH (b {name: $canonical_name})
MERGE (a)-[m:MERGED_INTO]->(b)
SET m.method     = $method,
    m.score      = $score,
    m.evidence   = $evidence,
    m.timestamp  = datetime(),
    m.confidence = $confidence
"""


class KnowledgeBase:
    def __init__(self):
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                max_connection_pool_size=10,
                connection_acquisition_timeout=30
            )
            self.driver.verify_connectivity()
            print("✅ Connected to Neo4j Graph Database")
            self._initialize_schema()
        except Exception as e:
            print(f"❌ Neo4j Connection Failed: {e}")

    def close(self):
        if self.driver:
            self.driver.close()

    def _initialize_schema(self):
        constraints = [
            "CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
            "CREATE CONSTRAINT org_name IF NOT EXISTS FOR (o:Organization) REQUIRE o.name IS UNIQUE",
            "CREATE CONSTRAINT location_name IF NOT EXISTS FOR (l:Location) REQUIRE l.name IS UNIQUE",
            "CREATE CONSTRAINT concept_name IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
        ]
        fulltext_indexes = [
            """CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
               FOR (n:Person|Organization|Location|Technology|Product|Event|Concept|Document|Law|Date|Amount)
               ON EACH [n.name]""",
        ]
        with self.driver.session() as session:
            for stmt in constraints + fulltext_indexes:
                try:
                    session.run(stmt)
                except Exception as e:
                    err = str(e).lower()
                    if "already exists" in err or "equivalent" in err:
                        pass
                    else:
                        raise RuntimeError(f"Schema init failed: {e}") from e

    def ingest_graph(self, graphs: List[Dict], document_id: str) -> None:
        """
        Bulk Neo4j write for all chunk graphs from one document.
        graphs: list of {nodes, edges} dicts returned by extract_relationships().
        Nodes written before edges. One session for the entire document.
        chunk_id is read per-node from its own properties — no hoisting.
        """
        if not self.driver or not graphs:
            return

        with self.driver.session() as session:
            for graph in graphs:
                # Nodes first — chunk_id comes from each node's own properties
                for node in graph.get("nodes", []):
                    try:
                        # Strip aliases from properties before NODE_UPSERT.
                        # aliases must never flow through SET n += $properties
                        # because that overwrites existing alias lists.
                        # _ingest_aliases() handles alias persistence safely.
                        props = {k: v for k, v in
                                 node.get("properties", {}).items()
                                 if k != "aliases"}
                        session.run(
                            NODE_UPSERT.format(node_type=node["type"]),
                            name=node["name"],
                            id=node["id"],
                            document_id=document_id,
                            chunk_id=node.get("properties", {}).get("chunk_id", ""),
                            properties=props
                        )
                    except Exception as e:
                        logger.warning("Node upsert failed %s: %s", node.get("name"), e)

                # Edges after all nodes in this chunk exist
                id_to_name = {n["id"]: n["name"] for n in graph.get("nodes", [])}
                for edge in graph.get("edges", []):
                    source_name = id_to_name.get(edge["source_id"])
                    target_name = id_to_name.get(edge["target_id"])
                    if not source_name or not target_name:
                        continue
                    try:
                        session.run(
                            EDGE_UPSERT.format(edge_type=edge["type"]),
                            source_name=source_name,
                            target_name=target_name,
                            document_id=document_id,
                            chunk_id=edge.get("properties", {}).get("chunk_id", "")
                        )
                    except Exception as e:
                        logger.warning("Edge upsert failed %s->%s: %s",
                                       source_name, target_name, e)

        total_nodes = sum(len(g.get("nodes", [])) for g in graphs)
        total_edges = sum(len(g.get("edges", [])) for g in graphs)
        print(f"   -> Graph stored {total_nodes} nodes, {total_edges} edges for {document_id}")

        # Write aliases for identity-bearing nodes (Person, Organization only)
        self._ingest_aliases(graphs)

    def _ingest_aliases(self, graphs: List[Dict]) -> None:
        """
        Persist aliases list to Neo4j for all nodes that have one.
        Uses safe list-merge Cypher — never overwrites aliases from prior ingests.
        Called after all nodes are guaranteed to exist in Neo4j.
        """
        if not self.driver:
            return

        alias_count = 0
        with self.driver.session() as session:
            for graph in graphs:
                for node in graph.get("nodes", []):
                    aliases = node.get("properties", {}).get("aliases")
                    if not aliases:
                        continue
                    try:
                        session.run(
                            ALIAS_UPSERT,
                            name=node["name"],
                            aliases=aliases
                        )
                        alias_count += len(aliases)
                    except Exception as e:
                        logger.warning("Alias upsert failed for %s: %s",
                                       node.get("name"), e)

        if alias_count:
            print(f"   -> Alias merge: {alias_count} alias(es) persisted")

    def ingest_merged_into(
        self,
        absorbed_name: str,
        canonical_name: str,
        method: str,
        score: float,
        evidence: List[str],
        confidence: str
    ) -> None:
        """
        Write a MERGED_INTO provenance edge between an absorbed node and its canonical.
        Called by graph_agent.py or ingest.py when a confirmed merge is recorded.

        method:     'nameparser_guard' | 'topology' | 'rapidfuzz' | 'llm'
        confidence: 'blocked' | 'uncertain' | 'confirmed'
        evidence:   list of strings describing why the merge was made/blocked
                    e.g. ['first_name_conflict'] or ['EMPLOYED_AT:Vantage Systems, Inc.']
        """
        if not self.driver:
            return
        try:
            with self.driver.session() as session:
                session.run(
                    MERGED_INTO_UPSERT,
                    absorbed_name=absorbed_name,
                    canonical_name=canonical_name,
                    method=method,
                    score=score,
                    evidence=evidence,
                    confidence=confidence
                )
        except Exception as e:
            logger.warning("MERGED_INTO upsert failed %s→%s: %s",
                           absorbed_name, canonical_name, e)

    def query_subgraph(self, keywords: List[str], source_filter: List[str] = None) -> str:
        if not self.driver or not keywords:
            return ""

        keyword_query = " OR ".join(f'"{kw}"' for kw in keywords if kw.strip())
        doc_filter_clause = "AND node.document_id IN $doc_ids" if source_filter else ""
        query = f"""
        CALL db.index.fulltext.queryNodes('entity_fulltext', $keyword_query)
        YIELD node, score
        WHERE score > 0.3 {doc_filter_clause}

        WITH node, max(score) AS score
        ORDER BY score DESC

        WITH DISTINCT node, score

        MATCH (node)-[r1]-(m)

        OPTIONAL MATCH (m)-[r2]-(leaf)
        WHERE type(r2) IN ['RELATED_TO', 'MENTIONS']

        RETURN DISTINCT
            node.name AS n_name,
            node.aliases AS n_aliases,
            type(r1) AS rel,
            m.name AS m_name,
            type(r2) AS rel2,
            leaf.name AS leaf_node
        LIMIT 50
        """
        try:
            with self.driver.session() as session:
                results = []
                query_params = {"keyword_query": keyword_query}
                if source_filter:
                    query_params["doc_ids"] = source_filter
                for r in session.run(query, **query_params):
                    node_label = r['n_name']
                    aliases = r.get('n_aliases')
                    if aliases:
                        node_label += f" (aka: {', '.join(aliases)})"
                    base = f"({node_label}) -[{r['rel']}]-> ({r['m_name']})"
                    if r['rel2'] and r['leaf_node']:
                        base += f"\n  └─> [{r['rel2']}] --> ({r['leaf_node']})"
                    results.append(base)
            return "\n".join(results) if results else ""
        except Exception as e:
            print(f"Graph query error: {e}")
            return ""

    def get_visualization_data(self, limit: int = 1000):
        if not self.driver:
            return {"nodes": [], "links": [], "total": 0}

        limit = min(max(limit, 1), 5000)

        query = """
        MATCH (s)-[r]->(o)
        WITH s, r, o, COUNT { MATCH ()-[]->() } AS total
        RETURN
            s.name AS source,
            labels(s)[0] AS source_type,
            type(r) AS relation,
            o.name AS target,
            labels(o)[0] AS target_type,
            total
        LIMIT $limit
        """

        nodes = {}
        links = []
        total = 0

        with self.driver.session() as session:
            for rec in session.run(query, limit=limit):
                total = rec["total"]
                nodes[rec["source"]] = {"id": rec["source"], "group": rec["source_type"]}
                nodes[rec["target"]] = {"id": rec["target"], "group": rec["target_type"]}
                links.append({
                    "source": rec["source"],
                    "target": rec["target"],
                    "label":  rec["relation"]
                })

        return {"nodes": list(nodes.values()), "links": links, "total": total}

    def get_graph_statistics(self):
        if not self.driver:
            return "Graph DB Disconnected."
        try:
            with self.driver.session() as session:
                # Bug 2 fix — count via nodes, more reliable than edge provenance
                total = session.run(
                    "MATCH (n) WHERE n.document_id IS NOT NULL "
                    "RETURN count(DISTINCT n.document_id) as c"
                ).single()["c"]
                top = session.run(
                    "MATCH (n) RETURN n.name as name, "
                    "size((n)--()) as d ORDER BY d DESC LIMIT 5"
                )
                stats = [f"TOTAL DOCS: {total}", "TOP ENTITIES:"] + \
                        [f"- {r['name']}: {r['d']}" for r in top]
                return "\n".join(stats)
        except Exception as e:
            print(f"⚠️ Graph stats error: {e}")
            return "Stats unavailable"

    def delete_document(self, filename: str) -> None:
        if not self.driver:
            return

        def _delete_tx(tx, f):
            # Delete all edges belonging to this document
            tx.run("MATCH ()-[r]->() WHERE r.document_id = $f DELETE r", f=f)

            # Bug 3 fix — only delete nodes exclusively owned by this document
            # that are now disconnected. Shared nodes survive untouched.
            tx.run("""
                MATCH (n)
                WHERE n.document_id = $f
                AND NOT (n)--()
                DELETE n
            """, f=f)

        with self.driver.session() as session:
            try:
                session.execute_write(_delete_tx, filename)
                print(f"✅ Successfully purged graph data for: {filename}")
            except Exception as e:
                print(f"❌ Graph deletion transaction failed for {filename}: {e}")