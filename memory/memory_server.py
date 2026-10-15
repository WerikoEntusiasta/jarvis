"""
J.A.R.V.I.S. Centralized Agentic Memory Server
Serviço de Memória Agêntica Centralizada com Banco Vetorial/Grafo de Conhecimento.
Conecta: OpenClaw (VPS), Antigravity (PC do Werik), OpenCode e Agentes Locais.
"""

import os
import sys
import json
import time
import math
import random
import re
import sqlite3
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

MEMORY_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(MEMORY_DIR, "jarvis_memory.db")

app = FastAPI(
    title="J.A.R.V.I.S. Agentic Memory Core",
    description="Memória Agêntica Centralizada com Grafo de Conhecimento e Visualização 3D de Cérebro Neuronal.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def scan_and_index_md_files(cursor=None):
    """Escaneia todos os arquivos .md de agentes, skills e documentação e indexa como nós de memória no cérebro 3D."""
    close_at_end = False
    if cursor is None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        close_at_end = True

    search_dirs = [
        os.path.join(os.path.dirname(MEMORY_DIR), "docs"),
        MEMORY_DIR,
        os.path.expanduser(r"~\.gemini\antigravity\builtin\skills"),
        os.path.expanduser(r"~\.gemini\config\plugins")
    ]
    
    project_root = os.path.dirname(MEMORY_DIR)
    if os.path.exists(project_root):
        search_dirs.append(project_root)

    md_files = []
    seen_paths = set()
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            dirs[:] = [dir_name for dir_name in dirs if dir_name not in ['build_dist', 'build_', 'pack_jarvis_windows', 'venv', 'node_modules', '.git', '__pycache__', 'scratch']]
            for f in files:
                if f.endswith(".md"):
                    full_p = os.path.abspath(os.path.join(root, f))
                    if full_p not in seen_paths:
                        seen_paths.add(full_p)
                        md_files.append(full_p)

    now = time.time()
    count = 0
    for file_path in md_files:
        try:
            rel_name = os.path.basename(file_path)
            parent_name = os.path.basename(os.path.dirname(file_path))
            clean_id = "md_" + re.sub(r'[^a-zA-Z0-9_]', '_', f"{parent_name}_{rel_name}").lower()
            
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(2500)
            
            lines = content.splitlines()
            title = f"{parent_name}/{rel_name}"
            for line in lines:
                if line.startswith("# "):
                    title = line.replace("# ", "").strip()
                    break

            proj = "JARVIS"
            if "openclaw" in file_path.lower() or "openclaw" in title.lower():
                proj = "OpenClaw"
            elif "skill" in file_path.lower() or "gemini" in file_path.lower():
                proj = "Antigravity"
            elif "lucia" in file_path.lower():
                proj = "Lucia"

            cursor.execute("SELECT id FROM memories WHERE id = ?", (clean_id,))
            if not cursor.fetchone():
                tot = cursor.execute("SELECT COUNT(*) FROM memories").fetchone()[0] + 1
                x, y, z = generate_brain_coordinates(tot, tot + 10)
                cursor.execute("""
                    INSERT INTO memories (id, project, type, title, content, tags, importance, created_at, updated_at, pos_x, pos_y, pos_z)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (clean_id, proj, "agent_md", f"📄 {title}", content, f"agent_md, markdown, {rel_name.lower()}", 4, now, now, x, y, z))
                
                cursor.execute("INSERT OR IGNORE INTO memory_links (source, target, relationship) VALUES (?, ?, ?)", (clean_id, "mem_jarvis_core", "documenta"))
                count += 1
        except Exception as e:
            print(f"Error indexing {file_path}: {e}")

    if close_at_end:
        conn.commit()
        conn.close()
    return count

# Initialize Database Schema
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            type TEXT NOT NULL, -- 'project', 'code', 'rule', 'conversation', 'entity', 'agent_md'
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            importance INTEGER DEFAULT 3,
            created_at REAL,
            updated_at REAL,
            pos_x REAL,
            pos_y REAL,
            pos_z REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_links (
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            relationship TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            PRIMARY KEY (source, target)
        )
    """)
    conn.commit()

    # Seed base initial memories if empty
    cursor.execute("SELECT COUNT(*) FROM memories")
    if cursor.fetchone()[0] == 0:
        seed_initial_memories(cursor)
        conn.commit()

    # Index agent .md files
    scan_and_index_md_files(cursor)
    conn.commit()
    conn.close()

def generate_brain_coordinates(index=0, total=50):
    """Gera coordenadas 3D (x, y, z) anatômicas reais do cérebro humano (córtex esquerdo/direito, cerebelo, tronco cerebral),
    distribuídas harmoniosamente por todo o volume cerebral."""
    region_rand = random.random()
    
    if region_rand < 0.78:
        # Córtex Cerebral (Hemisférios Esquerdo e Direito separados pela fissura longitudinal)
        side = 1.0 if (index % 2 == 0) else -1.0
        u = random.uniform(0.1, math.pi * 0.95)
        v = random.uniform(-math.pi * 0.45, math.pi * 0.50)
        
        rx = 11.5 * math.sin(u) * math.cos(v)
        ry = 14.5 * math.sin(u) * math.sin(v)
        rz = 10.5 * math.cos(u)
        
        x = (rx * 0.48 + (1.3 * side)) if abs(rx) > 0.4 else (0.9 * side)
        y = ry * 0.82
        z = rz * 0.85 + 1.2
        
    elif region_rand < 0.92:
        # Cerebelo (Região posterior inferior)
        side = 1.0 if (index % 2 == 0) else -1.0
        u = random.uniform(0, math.pi)
        v = random.uniform(0, math.pi)
        x = math.sin(u) * math.cos(v) * 4.8 + (1.4 * side)
        y = -9.5 + math.sin(u) * math.sin(v) * 3.8
        z = -4.5 + math.cos(u) * 3.8
        
    else:
        # Tronco Cerebral (Haste central inferior)
        x = random.uniform(-1.0, 1.0)
        y = random.uniform(-6.5, -1.8)
        z = random.uniform(-10.5, -3.5)

    return round(x, 2), round(y, 2), round(z, 2)

def generate_face_coordinates(index=0, total=50):
    return generate_brain_coordinates(index, total)

def reposition_all_nodes_to_anatomical_brain():
    """Recalcula a posição 3D de todas as memórias salvas para formar a silhueta do cérebro anatômico 3D."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM memories")
    rows = c.fetchall()
    for idx, r in enumerate(rows):
        x, y, z = generate_brain_coordinates(idx, len(rows))
        c.execute("UPDATE memories SET pos_x = ?, pos_y = ?, pos_z = ? WHERE id = ?", (x, y, z, r[0]))
    conn.commit()
    conn.close()

def seed_initial_memories(cursor):
    now = time.time()
    initial_nodes = [
        {
            "id": "mem_jarvis_core",
            "project": "JARVIS",
            "type": "project",
            "title": "J.A.R.V.I.S. Visual OS",
            "content": "Sistema Operacional Visual do Assistente Pessoal com HUD Stark, 11 componentes dinâmicos, visão por gestos e integração OpenClaw.",
            "tags": "jarvis, visual_os, hud, python, fastapi",
            "importance": 5
        },
        {
            "id": "mem_openclaw_vps",
            "project": "OpenClaw",
            "type": "entity",
            "title": "OpenClaw VPS Core",
            "content": "Núcleo cognitivo do agente em VPS remota (https://jarvis.werikspace.xyz) com subagentes paralelos e execução de ferramentas.",
            "tags": "openclaw, vps, subagentes, llm",
            "importance": 5
        },
        {
            "id": "mem_antigravity_pc",
            "project": "Antigravity",
            "type": "entity",
            "title": "Google Antigravity IDE",
            "content": "Ambiente de desenvolvimento agêntico de elite pair-programming executado no PC local do Senhor Werik.",
            "tags": "antigravity, ide, agent, python",
            "importance": 4
        },
        {
            "id": "mem_rule_visual_priority",
            "project": "JARVIS",
            "type": "rule",
            "title": "Prioridade de Interface Visual",
            "content": "A interface visual é fundamental no JARVIS. Respostas devem gerar UI Specifications (weather, comparison, checklist, dashboard, etc) em vez de simples texto.",
            "tags": "regra, ui, visual_os, heroui",
            "importance": 5
        },
        {
            "id": "mem_zimaos_infra",
            "project": "ZimaOS",
            "type": "code",
            "title": "Servidor Local ZimaOS",
            "content": "Infraestrutura de 39 containers Docker gerenciados localmente com monitoramento de telemetria e SSH.",
            "tags": "zimaos, docker, containers, infra",
            "importance": 4
        },
        {
            "id": "mem_pluggy_finance",
            "project": "Finance",
            "type": "entity",
            "title": "Pluggy Open Finance",
            "content": "Sincronização em tempo real de extratos e cartões Banco Inter do Senhor Werik.",
            "tags": "pluggy, inter, finance, open_finance",
            "importance": 4
        }
    ]

    links = [
        ("mem_jarvis_core", "mem_openclaw_vps", "conectado_a"),
        ("mem_jarvis_core", "mem_antigravity_pc", "desenvolvido_em"),
        ("mem_jarvis_core", "mem_rule_visual_priority", "obedece_regra"),
        ("mem_jarvis_core", "mem_zimaos_infra", "monitora"),
        ("mem_jarvis_core", "mem_pluggy_finance", "integra_dados")
    ]

    for idx, node in enumerate(initial_nodes):
        x, y, z = generate_brain_coordinates(idx, len(initial_nodes))
        cursor.execute("""
            INSERT INTO memories (id, project, type, title, content, tags, importance, created_at, updated_at, pos_x, pos_y, pos_z)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (node["id"], node["project"], node["type"], node["title"], node["content"], node["tags"], node["importance"], now, now, x, y, z))

    for s, t, r in links:
        cursor.execute("INSERT INTO memory_links (source, target, relationship) VALUES (?, ?, ?)", (s, t, r))

init_db()

# Models
class MemoryCreate(BaseModel):
    project: str = "JARVIS"
    type: str = "conversation" # 'project', 'code', 'rule', 'conversation', 'entity'
    title: str
    content: str
    tags: Optional[str] = ""
    importance: Optional[int] = 3

class MemoryLinkCreate(BaseModel):
    source: str
    target: str
    relationship: str = "relacionado_a"

# API Endpoints
@app.get("/api/memory/status")
def get_status():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM memories")
    count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memory_links")
    link_count = c.fetchone()[0]
    conn.close()
    return {
        "status": "ONLINE",
        "system": "J.A.R.V.I.S. Centralized Agentic Memory",
        "total_memories": count,
        "total_links": link_count,
        "database": DB_PATH
    }

@app.post("/api/memory/sync_md")
def sync_agent_md_files():
    new_indexed = scan_and_index_md_files()
    return {"status": "success", "indexed_new_md_files": new_indexed}

def run_sleep_consolidation():
    """Ciclo de Sono da Memória Agêntica (Memory Sleep Consolidation).
    Analisa os nós cadastrados, identifica agrupamentos por projeto/tags, gera novas pontes sinápticas e sintetiza o conhecimento."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id, project, type, title, tags, content FROM memories")
    memories = c.fetchall()
    
    created_links = 0
    for i in range(len(memories)):
        m1_id, m1_proj, m1_type, m1_title, m1_tags, m1_content = memories[i]
        tags1 = set([t.strip().lower() for t in (m1_tags or "").split(",") if t.strip()])
        
        for j in range(i + 1, len(memories)):
            m2_id, m2_proj, m2_type, m2_title, m2_tags, m2_content = memories[j]
            tags2 = set([t.strip().lower() for t in (m2_tags or "").split(",") if t.strip()])
            
            shared = tags1.intersection(tags2)
            if len(shared) >= 2 or (m1_proj == m2_proj and len(shared) >= 1):
                rel = f"sinapse_{list(shared)[0]}" if shared else "mesmo_projeto"
                c.execute("INSERT OR IGNORE INTO memory_links (source, target, relationship, weight) VALUES (?, ?, ?, ?)", (m1_id, m2_id, rel, 1.5))
                created_links += 1

    now = time.time()
    consolidation_id = f"mem_sleep_{int(now)}"
    tot = len(memories) + 1
    x, y, z = generate_brain_coordinates(tot, tot + 10)
    
    summary_title = f"🧠 Consolidação Sináptica Nocturna ({time.strftime('%Y-%m-%d')})"
    summary_content = f"Ciclo de sono agêntico executado. Analisados {len(memories)} nós de conhecimento e estabelecidas {created_links} novas conexões sinápticas de alta afinidade."
    
    c.execute("""
        INSERT OR REPLACE INTO memories (id, project, type, title, content, tags, importance, created_at, updated_at, pos_x, pos_y, pos_z)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (consolidation_id, "JARVIS", "rule", summary_title, summary_content, "sleep_consolidation, memoria, sinapse", 5, now, now, x, y, z))
    
    conn.commit()
    conn.close()
    return {"total_analyzed": len(memories), "new_synapses": created_links, "consolidation_node": consolidation_id}

@app.post("/api/memory/reposition")
def trigger_anatomical_reposition():
    reposition_all_nodes_to_anatomical_brain()
    return {"status": "success", "message": "Todas as memórias foram reposicionadas na malha do cérebro anatômico 3D."}

@app.post("/api/memory/sleep_consolidation")
def trigger_sleep_consolidation():
    res = run_sleep_consolidation()
    return {"status": "success", "message": "Ciclo de sono de memória agêntica concluído.", "result": res}

@app.post("/api/memory/remember")
def remember(mem: MemoryCreate):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    mem_id = f"mem_{int(time.time()*1000)}_{random.randint(100,999)}"
    now = time.time()
    
    c.execute("SELECT COUNT(*) FROM memories")
    tot = c.fetchone()[0] + 1
    x, y, z = generate_brain_coordinates(tot, tot + 10)

    c.execute("""
        INSERT INTO memories (id, project, type, title, content, tags, importance, created_at, updated_at, pos_x, pos_y, pos_z)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (mem_id, mem.project, mem.type, mem.title, mem.content, mem.tags, mem.importance, now, now, x, y, z))
    
    # Auto-link to same project nodes
    c.execute("SELECT id FROM memories WHERE project = ? AND id != ? LIMIT 3", (mem.project, mem_id))
    rows = c.fetchall()
    for r in rows:
        c.execute("INSERT OR IGNORE INTO memory_links (source, target, relationship) VALUES (?, ?, ?)", (mem_id, r[0], "mesmo_projeto"))
    
    conn.commit()
    conn.close()
    return {"status": "success", "id": mem_id, "message": "Memória registrada com sucesso no Cérebro Central."}

@app.get("/api/memory/recall")
def recall(query: str = Query(..., min_length=1), project: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if project:
        c.execute("""
            SELECT id, project, type, title, content, tags, importance, updated_at, pos_x, pos_y, pos_z
            FROM memories
            WHERE project = ?
        """, (project,))
    else:
        c.execute("""
            SELECT id, project, type, title, content, tags, importance, updated_at, pos_x, pos_y, pos_z
            FROM memories
        """)
        
    rows = c.fetchall()
    conn.close()

    keywords = [k.strip().lower() for k in query.lower().split() if len(k.strip()) > 1]
    if not keywords:
        keywords = [query.lower().strip()]

    scored_results = []
    for r in rows:
        title_lower = (r[3] or "").lower()
        content_lower = (r[4] or "").lower()
        tags_lower = (r[5] or "").lower()
        importance = r[6] or 3

        score = 0.0
        for kw in keywords:
            if kw in title_lower:
                score += 15.0
            if kw in tags_lower:
                score += 8.0
            if kw in content_lower:
                score += 3.0 + content_lower.count(kw) * 0.5
        
        if score > 0:
            total_score = score * (1 + (importance * 0.2))
            scored_results.append((total_score, {
                "id": r[0], "project": r[1], "type": r[2], "title": r[3],
                "content": r[4], "tags": r[5], "importance": r[6], "updated_at": r[7],
                "score": round(total_score, 2),
                "position": {"x": r[8], "y": r[9], "z": r[10]}
            }))

    scored_results.sort(key=lambda x: (x[0], x[1]["updated_at"]), reverse=True)
    final_memories = [item[1] for item in scored_results[:15]]

    return {"query": query, "total_found": len(final_memories), "memories": final_memories}

@app.get("/api/memory/graph")
def get_brain_graph():
    """Retorna o grafo 3D completo de nós e pontes sinápticas para o visualizador WebGL Three.js."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id, project, type, title, content, tags, importance, pos_x, pos_y, pos_z FROM memories")
    nodes_raw = c.fetchall()
    
    c.execute("SELECT source, target, relationship, weight FROM memory_links")
    links_raw = c.fetchall()
    conn.close()
    
    nodes = []
    for r in nodes_raw:
        nodes.append({
            "id": r[0],
            "project": r[1],
            "type": r[2],
            "title": r[3],
            "content": r[4],
            "tags": r[5],
            "importance": r[6],
            "x": r[7],
            "y": r[8],
            "z": r[9]
        })
        
    links = []
    for r in links_raw:
        links.append({
            "source": r[0],
            "target": r[1],
            "relationship": r[2],
            "weight": r[3]
        })
        
    return {"nodes": nodes, "links": links}

@app.delete("/api/memory/{memory_id}")
def delete_memory(memory_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    c.execute("DELETE FROM memory_links WHERE source = ? OR target = ?", (memory_id, memory_id))
    conn.commit()
    conn.close()
    return {"status": "success", "deleted_id": memory_id}

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    dashboard_path = os.path.join(MEMORY_DIR, "brain_dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>J.A.R.V.I.S. Memory Server Running</h1>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
