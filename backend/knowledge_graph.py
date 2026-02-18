import os
from typing import List, Dict, Optional
from datetime import datetime
from neo4j import GraphDatabase

# --- CONFIGURATION ---
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

class KnowledgeBase:
    def __init__(self):
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self.driver.verify_connectivity()
            print("✅ Connected to Neo4j Graph Database")
            
            # 🚀 NEW: Apply Constraints on Startup
            self._initialize_schema()
            
        except Exception as e:
            print(f"❌ Neo4j Connection Failed: {e}")

    def close(self):
        if self.driver:
            self.driver.close()

    def _initialize_schema(self):
        """
        Creates constraints to ensure data integrity and speed up lookups.
        Production App Requirement: Never allow duplicate nodes.
        """
        constraints = [
            "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
            "CREATE CONSTRAINT statute_name IF NOT EXISTS FOR (s:Statute) REQUIRE s.name IS UNIQUE",
            "CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
            "CREATE CONSTRAINT org_name IF NOT EXISTS FOR (o:Organization) REQUIRE o.name IS UNIQUE",
            "CREATE INDEX relation_source IF NOT EXISTS FOR ()-[r:RELATION]-() ON (r.source)"
        ]
        
        with self.driver.session() as session:
            for c in constraints:
                try:
                    session.run(c)
                except Exception as e:
                    print(f"⚠️ Schema Warning: {e}")

    def _classify_entity(self, name: str) -> str:
        """
        Simple heuristic to classify nodes. 
        In a full enterprise app, an LLM would do this, but this regex is fast and effective.
        """
        lower = name.lower()
        if any(x in lower for x in ['section', 'article', 'act', 'code', 'regulation']):
            return "Statute"
        if any(x in lower for x in ['inc', 'ltd', 'corp', 'company', 'organization']):
            return "Organization"
        if any(x in lower for x in ['mr.', 'mrs.', 'ms.', 'dr.', 'judge']):
            return "Person"
        return "Entity" # Fallback

    def add_relations(self, relations: List[Dict], source_file: str, page_number: int = 1):
        """
        Inserts nodes with TYPES and NEW EDGE WEIGHTS (Corroboration + Time).
        """
        if not self.driver:
            return

        # FIX: Stable entity typing and corroboration accumulation
        simple_query = """
        UNWIND $batch AS row
        
        // STABLE TYPING: Only set type if the node is brand new
        MERGE (s:Entity {name: row.subject})
        ON CREATE SET s.type = row.subject_type
        
        MERGE (o:Entity {name: row.object})
        ON CREATE SET o.type = row.object_type
        
        // EDGE CREATION: Scoped to the source document
        MERGE (s)-[r:RELATION {type: row.predicate, source: row.source}]->(o)
        ON CREATE SET 
            r.page = row.page,
            r.confidence = 0.95,
            r.created_at = datetime(),
            r.corroboration_strength = row.corroboration,
            r.temporal_version = row.period,
            r.mentions = 1
        // CORROBORATION: Accumulate mentions if found again in the same doc
        ON MATCH SET
            r.mentions = r.mentions + 1
        """

        batch_data = []
        for r in relations:
            subj = r.get("subject")
            obj = r.get("object")
            pred = r.get("predicate")
            
            if subj and obj and pred:
                # We classify entities just like before
                batch_data.append({
                    "subject": subj,
                    "subject_type": self._classify_entity(subj),
                    "object": obj,
                    "object_type": self._classify_entity(obj),
                    "predicate": pred.upper().replace(" ", "_"), 
                    "source": source_file,
                    "page": page_number,
                    "confidence": 0.95,
                    # NEW: Default to 'MEDIUM' if LLM didn't find explicit link
                    "corroboration": r.get("corroboration", "MEDIUM"),
                    # NEW: Default to 'UNKNOWN' if no date found
                    "period": r.get("period", "UNKNOWN")
                })

        if not batch_data:
            return

        with self.driver.session() as session:
            try:
                session.run(simple_query, batch=batch_data)
                print(f"   -> Graph+ stored {len(batch_data)} relations (Page {page_number})")
            except Exception as e:
                print(f"   ⚠️ Neo4j Write Error: {e}")
    def get_visualization_data(self, limit: int = 1000):
        if not self.driver: 
            return {"nodes": [], "links": [], "total": 0}
        
        # Cap limit server-side
        limit = min(max(limit, 1), 5000)
        
        query = """
        MATCH (s)-[r]->(o)
        RETURN s.name AS source, 
            COALESCE(s.type, 'Entity') as source_type, 
            r.type AS relation, 
            o.name AS target, 
            COALESCE(o.type, 'Entity') as target_type
        LIMIT $limit
        """
        
        nodes = {}
        links = []
        
        with self.driver.session() as session:
            # Get total count
            total = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            
            for rec in session.run(query, limit=limit):
                nodes[rec["source"]] = {"id": rec["source"], "group": rec["source_type"]}
                nodes[rec["target"]] = {"id": rec["target"], "group": rec["target_type"]}
                links.append({"source": rec["source"], "target": rec["target"], "label": rec["relation"]})
        
        return {"nodes": list(nodes.values()), "links": links, "total": total}



    def get_graph_statistics(self):
        """Fetches statistics using Cypher queries."""
        if not self.driver: return "Graph DB Disconnected."
        try:
            with self.driver.session() as session:
                total = session.run("MATCH ()-[r]->() RETURN count(DISTINCT r.source) as c").single()["c"]
                top = session.run("MATCH (n:Entity) RETURN n.name as name, size((n)--()) as d ORDER BY d DESC LIMIT 5")
                stats = [f"TOTAL DOCS: {total}", "TOP ENTITIES:"] + [f"- {r['name']}: {r['d']}" for r in top]
                return "\n".join(stats)
        except: return "Stats unavailable"

    # [FILE: knowledge_graph.py]
    # Find the 'query_subgraph' method and REPLACE the entire method with this version.
    # CHANGES: Cypher query now looks for 2nd-hop adversarial edges.
    # PRESERVES: Output format (returns a string representation of the subgraph).

    def query_subgraph(self, keywords: List[str]) -> str:
        """
        Query with PRIORITY for HIGH corroboration edges + ADVERSARIAL TRAVERSAL.
        """
        if not self.driver or not keywords: return ""
        
        # New Query: Bidirectional adversarial hop + Explicit Aliases
        query = """
        UNWIND $keywords AS keyword
        MATCH (n:Entity) WHERE toLower(n.name) CONTAINS toLower(keyword)
        
        // 1. Standard 1-Hop Traversal (EXCLUDING ADVERSARIAL EDGES)
        MATCH (n)-[r1:RELATION]-(m)
        WHERE NOT r1.type IN ['CONTRADICTS', 'REVISES', 'SUPERSEDES', 'NEGATES']
        
        // 2. Bidirectional Adversarial Look-Ahead
        OPTIONAL MATCH (m)-[r2:RELATION]-(leaf)
        WHERE r2.type IN ['CONTRADICTS', 'REVISES', 'SUPERSEDES', 'NEGATES']
        
        // EXPLICIT ALIASES
        RETURN n.name AS n_name, 
               r1.type AS rel, 
               m.name AS m_name,
               r1.corroboration_strength AS strength,
               r1.temporal_version AS period,
               r2.type AS rel2,
               leaf.name AS leaf_node
        ORDER BY 
            CASE r1.corroboration_strength 
                WHEN 'HIGH' THEN 1 
                WHEN 'MEDIUM' THEN 2 
                ELSE 3 
            END,
            r1.created_at DESC
        LIMIT 50
        """
        try:
            with self.driver.session() as session:
                results = []
                for r in session.run(query, keywords=keywords):
                    # SECURE KVP ACCESS
                    base = f"({r['n_name']}) -[{r['rel']} | {r['strength']} | {r['period']}]-> ({r['m_name']})"
                    
                    if r['rel2'] and r['leaf_node']:
                        full_path = (f"{base}\n"
                                    f"  └─> [ALSO_SEE: {r['rel2']}] --> "
                                    f"(ALTERNATIVE_VALUE: {r['leaf_node']})")
                        full_path += "\n      [Note: Multiple values present - check source for context]"
                    else:
                        full_path = base
                    
                    results.append(full_path)
                        
            return "\n".join(results) if results else ""
        except Exception as e:
            print(f"Graph query error: {e}")
            return ""
        
    def delete_document(self, filename: str):
        if not self.driver: 
            return
            
        # Define the atomic transaction
        def _delete_tx(tx, f):
            # 1. Delete all relationships originating from this file
            tx.run("MATCH ()-[r:RELATION]-() WHERE r.source = $f DELETE r", f=f)
            # 2. Clean up any nodes that are now completely orphaned
            tx.run("MATCH (n:Entity) WHERE NOT (n)--() DELETE n")
            
        with self.driver.session() as session:
            try:
                # execute_write guarantees both succeed, or both roll back
                session.execute_write(_delete_tx, filename)
                print(f"✅ Successfully purged graph data for: {filename}")
            except Exception as e:
                print(f"❌ Graph deletion transaction failed for {filename}: {e}")