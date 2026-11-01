"""
J.A.R.V.I.S. Unified Memory System (PostgreSQL 17 + Redis 7)
Camada Híbrida de Memória Cognitiva:
 - L1 (Quente/Ultra Rápida): Redis para buffer de diálogo (<2ms) e estado do ecossistema.
 - L2 (Durável/Semântica): PostgreSQL + pgvector + pg_trgm para fatos permanentes, tarefas e histórico perpétuo.
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

try:
    import asyncpg
except ImportError:
    asyncpg = None

logger = logging.getLogger("JARVIS-MEMORY")

def _detect_hosts():
    """Detecta automaticamente o IP do PostgreSQL e Redis dependendo do modo de rede do container."""
    if "PG_HOST" in os.environ and "REDIS_HOST" in os.environ:
        return os.environ["PG_HOST"], os.environ["REDIS_HOST"]
    import socket
    candidates = [
        ("127.0.0.1", "127.0.0.1"),
        ("172.17.0.11", "172.17.0.10"),
        ("192.168.3.6", "192.168.3.6")
    ]
    for pg_c, r_c in candidates:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.4)
            s.connect((pg_c, 5432))
            s.close()
            return pg_c, r_c
        except Exception:
            pass
    return "127.0.0.1", "127.0.0.1"

_pg_h, _r_h = _detect_hosts()
REDIS_HOST = os.environ.get("REDIS_HOST", _r_h)
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "Casaos")

PG_HOST = os.environ.get("PG_HOST", _pg_h)
PG_PORT = int(os.environ.get("PG_PORT", 5432))
PG_USER = os.environ.get("PG_USER", "casaos")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "Casaos_Db_Sec2026!")
PG_DATABASE = os.environ.get("PG_DATABASE", "jarvis_memory")


class UnifiedMemoryManager:
    _instance = None

    def __init__(self):
        self.redis: Optional[Any] = None
        self.pg_pool: Optional[Any] = None
        self.initialized = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = UnifiedMemoryManager()
        return cls._instance

    async def initialize(self):
        """Inicializa pools de conexão assíncronos com Redis e PostgreSQL."""
        if self.initialized:
            return

        # 1. Conexão Redis
        if aioredis:
            try:
                self.redis = aioredis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    password=REDIS_PASSWORD,
                    decode_responses=True,
                    socket_timeout=3.0
                )
                await self.redis.ping()
                logger.info("[REDIS] Pool L1 conectado com sucesso em %s:%d", REDIS_HOST, REDIS_PORT)
            except Exception as e:
                logger.error("[REDIS] Falha na inicialização L1: %s", e)
                self.redis = None

        # 2. Conexão PostgreSQL
        if asyncpg:
            try:
                self.pg_pool = await asyncpg.create_pool(
                    host=PG_HOST,
                    port=PG_PORT,
                    user=PG_USER,
                    password=PG_PASSWORD,
                    database=PG_DATABASE,
                    min_size=2,
                    max_size=10,
                    timeout=5.0
                )
                logger.info("[POSTGRES] Pool L2 conectado com sucesso em %s:%d/%s", PG_HOST, PG_PORT, PG_DATABASE)
            except Exception as e:
                logger.error("[POSTGRES] Falha na inicialização L2: %s", e)
                self.pg_pool = None

        self.initialized = True

    # =========================================================================
    # L1: BUFFER DE DIÁLOGO (REDIS < 1ms com persistência no Postgres)
    # =========================================================================

    async def add_dialogue(self, session_id: str, source: str, role: str, content: str, metadata: dict = None):
        """Registra turno de conversa no cache L1 Redis e insere em background no PostgreSQL."""
        if not self.initialized:
            await self.initialize()

        item = {
            "session_id": session_id,
            "source": source,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "ts": time.time()
        }
        item_json = json.dumps(item, ensure_ascii=False)

        # 1. Salvar no Redis (últimos 20 turnos)
        if self.redis:
            try:
                key = f"jarvis:session:{session_id}:dialogues"
                await self.redis.rpush(key, item_json)
                await self.redis.ltrim(key, -20, -1)
                await self.redis.expire(key, 86400 * 7)  # TTL de 7 dias na sessão ativa
            except Exception as e:
                logger.warning("[REDIS-DIALOGUE] Erro ao gravar L1: %s", e)

        # 2. Persistir no PostgreSQL de forma durável
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO jarvis_dialogues (session_id, source, role, content, metadata)
                        VALUES ($1, $2, $3, $4, $5::jsonb)
                        """,
                        session_id, source, role, content, json.dumps(metadata or {})
                    )
            except Exception as e:
                logger.error("[POSTGRES-DIALOGUE] Erro ao gravar L2: %s", e)

    async def get_recent_dialogues(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Recupera os turnos mais recentes. Tenta Redis (<1ms), fallback para Postgres."""
        if not self.initialized:
            await self.initialize()

        # 1. Tentar L1 (Redis)
        if self.redis:
            try:
                key = f"jarvis:session:{session_id}:dialogues"
                raw_items = await self.redis.lrange(key, -limit, -1)
                if raw_items:
                    return [json.loads(x) for x in raw_items]
            except Exception as e:
                logger.warning("[REDIS-GET] Falha ao ler L1: %s", e)

        # 2. Fallback L2 (PostgreSQL)
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT session_id, source, role, content, metadata, 
                               EXTRACT(EPOCH FROM created_at) AS ts
                        FROM jarvis_dialogues
                        WHERE session_id = $1
                        ORDER BY id DESC
                        LIMIT $2
                        """,
                        session_id, limit
                    )
                    dialogues = [dict(r) for r in reversed(rows)]
                    return dialogues
            except Exception as e:
                logger.error("[POSTGRES-GET] Falha ao ler L2: %s", e)

        return []

    # =========================================================================
    # L2: FATOS E PREFERÊNCIAS COGNITIVAS (PostgreSQL)
    # =========================================================================

    async def get_relevant_facts(self, query: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Recupera os fatos mais relevantes para a consulta atual."""
        if not self.initialized:
            await self.initialize()

        facts = []
        if not self.pg_pool:
            return facts

        try:
            async with self.pg_pool.acquire() as conn:
                if query and len(query.strip()) > 2:
                    # Busca por similaridade de trigrama (pg_trgm) + fatos de perfil essenciais
                    rows = await conn.fetch(
                        """
                        SELECT id, category, subject, predicate, fact, confidence,
                               similarity(fact, $1) AS score
                        FROM jarvis_facts
                        WHERE category = 'perfil' OR similarity(fact, $1) > 0.15
                        ORDER BY (category = 'perfil') DESC, score DESC
                        LIMIT $2
                        """,
                        query, limit
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, category, subject, predicate, fact, confidence, 1.0 AS score
                        FROM jarvis_facts
                        ORDER BY (category = 'perfil') DESC, updated_at DESC
                        LIMIT $1
                        """,
                        limit
                    )
                facts = [dict(r) for r in rows]
        except Exception as e:
            logger.error("[POSTGRES-FACTS] Erro ao recuperar fatos: %s", e)

        return facts

    async def add_fact(self, category: str, subject: str, predicate: str, fact: str, confidence: float = 1.0):
        """Armazena um novo fato permanente ou atualiza um existente."""
        if not self.initialized:
            await self.initialize()

        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO jarvis_facts (category, subject, predicate, fact, confidence, updated_at)
                        VALUES ($1, $2, $3, $4, $5, NOW())
                        ON CONFLICT (id) DO UPDATE
                        SET fact = EXCLUDED.fact, confidence = EXCLUDED.confidence, updated_at = NOW()
                        """,
                        category, subject, predicate, fact, confidence
                    )
                    logger.info("[POSTGRES-FACTS] Fato salvo: [%s] %s -> %s", category, subject, fact[:40])
            except Exception as e:
                logger.error("[POSTGRES-FACTS] Erro ao salvar fato: %s", e)

    # =========================================================================
    # L1 + L2: ESTADO DO ECOSSISTEMA (Hardware, Sensores, Conectividade)
    # =========================================================================

    async def set_state(self, key: str, value: Any, ttl: Optional[int] = None):
        """Define um estado compartilhado no Redis e replica no PostgreSQL."""
        if not self.initialized:
            await self.initialize()

        val_json = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value

        if self.redis:
            try:
                r_key = f"jarvis:state:{key}"
                if ttl:
                    await self.redis.setex(r_key, ttl, val_json)
                else:
                    await self.redis.set(r_key, val_json)
            except Exception as e:
                logger.warning("[REDIS-STATE] Falha ao salvar estado: %s", e)

        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO jarvis_shared_state (key, value, updated_at)
                        VALUES ($1, $2::jsonb, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value, updated_at = NOW()
                        """,
                        key, val_json if val_json.startswith('{') or val_json.startswith('[') else json.dumps(val_json)
                    )
            except Exception as e:
                logger.error("[POSTGRES-STATE] Falha ao salvar estado: %s", e)

    async def get_state(self, key: str, default: Any = None) -> Any:
        """Obtém estado compartilhado do Redis (<1ms), fallback Postgres."""
        if not self.initialized:
            await self.initialize()

        if self.redis:
            try:
                raw = await self.redis.get(f"jarvis:state:{key}")
                if raw is not None:
                    try:
                        return json.loads(raw)
                    except Exception:
                        return raw
            except Exception as e:
                logger.warning("[REDIS-GETSTATE] Falha: %s", e)

        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT value FROM jarvis_shared_state WHERE key = $1", key)
                    if row:
                        val = row["value"]
                        return json.loads(val) if isinstance(val, str) else val
            except Exception as e:
                logger.error("[POSTGRES-GETSTATE] Falha: %s", e)

        return default

    # =========================================================================
    # TAREFAS E LEMBRETES (PostgreSQL)
    # =========================================================================

    async def add_task(self, title: str, description: str = None, due_at: Optional[str] = None):
        """Cria uma tarefa ou lembrete cognitivo."""
        if not self.initialized:
            await self.initialize()

        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO jarvis_tasks_reminders (title, description, due_at)
                        VALUES ($1, $2, $3::timestamptz)
                        """,
                        title, description, due_at
                    )
                    logger.info("[POSTGRES-TASKS] Nova tarefa: %s", title)
            except Exception as e:
                logger.error("[POSTGRES-TASKS] Erro ao criar tarefa: %s", e)

    async def get_pending_tasks(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Lista tarefas e lembretes pendentes."""
        if not self.initialized:
            await self.initialize()

        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, title, description, due_at, created_at
                        FROM jarvis_tasks_reminders
                        WHERE status = 'pending'
                        ORDER BY due_at ASC NULLS LAST, id ASC
                        LIMIT $1
                        """,
                        limit
                    )
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error("[POSTGRES-TASKS] Erro ao buscar tarefas: %s", e)

        return []

    # =========================================================================
    # CONSTRUTOR DE CONTEXTO COGNITIVO PARA O PROMPT DE SISTEMA DA IA
    # =========================================================================

    async def build_context_prompt(self, session_id: str = "default", query: str = None) -> str:
        """Gera o bloco consolidado de memória cognitiva para injeção no prompt da IA."""
        facts = await self.get_relevant_facts(query=query, limit=4)
        tasks = await self.get_pending_tasks(limit=3)

        context_lines = ["\n[MEMÓRIA COGNITIVA CENTRAL DO J.A.R.V.I.S. (Postgres + Redis)]:"]

        if facts:
            context_lines.append("• Fatos e Preferências do Senhor Werik:")
            for f in facts:
                context_lines.append(f"  - [{f.get('subject', 'Geral')}]: {f.get('fact')}")

        if tasks:
            context_lines.append("• Lembretes e Tarefas Ativas:")
            for t in tasks:
                context_lines.append(f"  - #{t.get('id')}: {t.get('title')}")

        context_lines.append("Utilize as memórias acima de forma natural, demonstrando continuidade absoluta e conhecimento da rotina do Senhor Werik.\n")
        return "\n".join(context_lines)


# Instância global singleton
memory_mgr = UnifiedMemoryManager.get_instance()


def build_context_prompt_sync(session_id: str = "default", query: str = None) -> str:
    """Helper síncrono ultra-rápido para injeção no prompt de threads síncronas do CoreBrain."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            dbname=PG_DATABASE,
            connect_timeout=2
        )
        cur = conn.cursor()
        if query and len(query.strip()) > 2:
            cur.execute(
                """
                SELECT id, category, subject, predicate, fact, confidence,
                       similarity(fact, %s) AS score
                FROM jarvis_facts
                WHERE category = 'perfil' OR similarity(fact, %s) > 0.10
                ORDER BY (category = 'perfil') DESC, score DESC
                LIMIT 5;
                """,
                (query, query)
            )
        else:
            cur.execute(
                """
                SELECT id, category, subject, predicate, fact, confidence, 1.0 AS score
                FROM jarvis_facts
                ORDER BY (category = 'perfil') DESC, updated_at DESC
                LIMIT 5;
                """
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        context_lines = ["\n[MEMÓRIA COGNITIVA CENTRAL DO J.A.R.V.I.S. (Postgres + Redis)]:"]
        if rows:
            context_lines.append("• Fatos e Preferências Registrados:")
            for r in rows:
                context_lines.append(f"  - [{r[2]}]: {r[4]}")
        context_lines.append("Utilize as memórias acima com naturalidade, demonstrando continuidade absoluta e conhecimento da rotina do Senhor Werik.\n")
        return "\n".join(context_lines)
    except Exception as e:
        logger.warning("[SYNC-CONTEXT-FALLBACK] %s", e)
        return ""


def add_dialogue_sync(session_id: str, source: str, role: str, content: str, metadata: dict = None):
    """Gravação síncrona/background em L1 Redis e L2 Postgres sem conflitos de loop."""
    import threading
    def _worker():
        # 1. Gravar no Redis
        try:
            import redis
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True, socket_timeout=1.5)
            item_json = json.dumps({
                "session_id": session_id,
                "source": source,
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "ts": time.time()
            }, ensure_ascii=False)
            key = f"jarvis:session:{session_id}:dialogues"
            r.rpush(key, item_json)
            r.ltrim(key, -20, -1)
            r.expire(key, 86400 * 7)
            r.close()
        except Exception as ex_r:
            logger.warning("[SYNC-REDIS] %s", ex_r)

        # 2. Gravar no PostgreSQL
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DATABASE, connect_timeout=2
            )
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO jarvis_dialogues (session_id, source, role, content, metadata)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (session_id, source, role, content, json.dumps(metadata or {}))
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as ex_pg:
            logger.warning("[SYNC-POSTGRES] %s", ex_pg)

    threading.Thread(target=_worker, daemon=True).start()

