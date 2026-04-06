from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import sqlparse
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from db.connection import get_engine, get_schema_description


# ── DTOs ─────────────────────────────────────────────────────

@dataclass
class QueryResult:
    """Resultado completo de uma query Text-to-SQL."""
    question: str
    sql: str
    df: pd.DataFrame
    answer: str
    execution_time_ms: int
    cached: bool = False
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class ValidationResult:
    valid: bool
    error: str | None = None
    cleaned_sql: str | None = None


# ── Cache simples em memória ──────────────────────────────────

class _QueryCache:
    """LRU-like cache para evitar chamadas repetidas ao LLM."""

    def __init__(self, max_size: int = 100):
        self._store: dict[str, tuple[str, float]] = {}
        self._max = max_size

    def _key(self, question: str) -> str:
        return hashlib.sha256(question.strip().lower().encode()).hexdigest()[:16]

    def get(self, question: str) -> str | None:
        settings = get_settings()
        key = self._key(question)
        if key in self._store:
            sql, ts = self._store[key]
            if time.time() - ts < settings.cache_ttl_seconds:
                return sql
            del self._store[key]
        return None

    def set(self, question: str, sql: str) -> None:
        if len(self._store) >= self._max:
            # Remove o mais antigo
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]
        self._store[self._key(question)] = (sql, time.time())


_cache = _QueryCache()


# ── Prompt Engineering ────────────────────────────────────────

def _build_system_prompt() -> str:
    schema = get_schema_description()
    return f"""Você é um especialista em SQL para PostgreSQL. Sua única função é converter perguntas em português para SQL válido e seguro.

{schema}

REGRAS ABSOLUTAS:
1. Retorne APENAS o SQL puro — sem markdown, sem ```sql, sem explicações
2. Use APENAS SELECT — jamais escreva DDL ou DML (DROP, DELETE, UPDATE, INSERT, ALTER, CREATE)
3. Sempre inclua LIMIT {get_settings().sql_max_rows} no final da query
4. Use aliases descritivos em português: total_receita, qtd_pedidos, nome_produto
5. Para datas, use DATE_TRUNC, EXTRACT ou TO_CHAR conforme o contexto
6. Prefira JOINs explícitos (INNER JOIN, LEFT JOIN) ao invés de subqueries quando possível
7. Se a pergunta for ambígua, faça a interpretação mais útil para análise de negócio
8. Nunca inclua dados sensíveis como emails completos — use SUBSTRING ou mascare

EXEMPLOS:
Pergunta: "Qual o total de vendas por mês em 2024?"
SQL:
SELECT
  TO_CHAR(o.order_date, 'YYYY-MM') AS mes,
  COUNT(o.id)                       AS qtd_pedidos,
  SUM(o.total_amount)               AS total_receita
FROM orders o
WHERE o.order_date BETWEEN '2024-01-01' AND '2024-12-31'
  AND o.status = 'delivered'
GROUP BY 1
ORDER BY 1
LIMIT 500

Pergunta: "Top 5 produtos mais vendidos?"
SQL:
SELECT
  p.name                  AS produto,
  c.name                  AS categoria,
  SUM(oi.quantity)        AS unidades_vendidas,
  SUM(oi.subtotal)        AS receita_total
FROM order_items oi
JOIN products p  ON oi.product_id = p.id
JOIN categories c ON p.category_id = c.id
JOIN orders o    ON oi.order_id = o.id
WHERE o.status = 'delivered'
GROUP BY p.id, p.name, c.name
ORDER BY unidades_vendidas DESC
LIMIT 5"""


def _build_answer_prompt(question: str, sql: str, df: pd.DataFrame) -> str:
    """Prompt para o LLM transformar o resultado em linguagem natural."""
    sample = df.head(10).to_string(index=False) if not df.empty else "(nenhum resultado)"
    n_rows = len(df)
    return f"""O usuário perguntou: "{question}"

O SQL gerado foi:
{sql}

Os primeiros resultados ({min(n_rows, 10)} de {n_rows} linhas):
{sample}

Responda a pergunta do usuário em português, de forma clara e direta, citando os números mais importantes.
Use formatação com R$ para valores monetários brasileiros. Seja conciso (máx 3 parágrafos).
Se o resultado estiver vazio, diga isso claramente."""


# ── Validação de Segurança ────────────────────────────────────

def validate_sql(sql: str) -> ValidationResult:
    """
    Validação em duas camadas:
    1. Blacklist de palavras-chave proibidas
    2. Verificação sintática com sqlparse
    """
    settings = get_settings()

    # Normaliza: remove comentários e whitespace excessivo
    cleaned = sqlparse.format(
        sql.strip(),
        strip_comments=True,
        reindent=True,
        keyword_case="upper",
    ).strip()

    if not cleaned:
        return ValidationResult(valid=False, error="SQL vazio gerado pelo LLM")

    # Garante que é um SELECT
    parsed = sqlparse.parse(cleaned)
    if not parsed:
        return ValidationResult(valid=False, error="SQL inválido — não foi possível parsear")

    stmt_type = parsed[0].get_type()
    if stmt_type != "SELECT":
        return ValidationResult(
            valid=False,
            error=f"Apenas SELECT é permitido. Tipo detectado: {stmt_type}"
        )

    # Verifica palavras proibidas (case-insensitive)
    upper_sql = cleaned.upper()
    for keyword in settings.sql_blocked_keywords:
        if keyword in upper_sql.split():
            return ValidationResult(
                valid=False,
                error=f"Palavra-chave proibida detectada: {keyword}"
            )

    # Garante LIMIT
    if "LIMIT" not in upper_sql:
        cleaned += f"\nLIMIT {settings.sql_max_rows}"

    return ValidationResult(valid=True, cleaned_sql=cleaned)


# ── LLM Client ───────────────────────────────────────────────

def _get_llm() -> ChatGroq:
    settings = get_settings()
    return ChatGroq(
        api_key=settings.groq_api_key.get_secret_value(),
        model=settings.groq_model,
        temperature=settings.groq_temperature,
        max_tokens=settings.groq_max_tokens,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _call_llm(messages: list) -> str:
    """Chama o Groq com retry exponencial automático."""
    llm = _get_llm()
    response = llm.invoke(messages)
    return response.content.strip()


# ── Pipeline Principal ────────────────────────────────────────

def generate_sql(question: str) -> tuple[str, bool]:
    """
    Converte pergunta em SQL usando o LLM.
    Retorna (sql, from_cache).
    """
    # Verifica cache primeiro
    cached = _cache.get(question)
    if cached:
        logger.debug(f"Cache hit para: {question[:50]}...")
        return cached, True

    messages = [
        SystemMessage(content=_build_system_prompt()),
        HumanMessage(content=question),
    ]

    raw_sql = _call_llm(messages)

    # Remove possível markdown que o LLM inclua mesmo sendo instruído a não
    raw_sql = raw_sql.replace("```sql", "").replace("```", "").strip()

    _cache.set(question, raw_sql)
    return raw_sql, False


def execute_sql(sql: str) -> pd.DataFrame:
    """Executa SQL validado e retorna DataFrame."""
    settings = get_settings()
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text(sql).execution_options(timeout=settings.sql_timeout_seconds)
        )
        df = pd.DataFrame(result.fetchall(), columns=list(result.keys()))

    return df


def generate_answer(question: str, sql: str, df: pd.DataFrame) -> str:
    """Gera resposta em linguagem natural a partir dos resultados."""
    prompt = _build_answer_prompt(question, sql, df)
    messages = [HumanMessage(content=prompt)]
    return _call_llm(messages)


def ask(question: str) -> QueryResult:
    """
    Ponto de entrada principal — orquestra o pipeline completo.

    Args:
        question: Pergunta em português sobre os dados.

    Returns:
        QueryResult com SQL, DataFrame, resposta e metadados.
    """
    logger.info(f"Pergunta recebida: {question}")
    t0 = time.monotonic()

    try:
        # 1. Gerar SQL
        raw_sql, from_cache = generate_sql(question)
        logger.debug(f"SQL gerado:\n{raw_sql}")

        # 2. Validar
        validation = validate_sql(raw_sql)
        if not validation.valid:
            raise ValueError(f"SQL inválido: {validation.error}")

        clean_sql = validation.cleaned_sql

        # 3. Executar
        df = execute_sql(clean_sql)
        logger.info(f"Query retornou {len(df)} linhas")

        # 4. Gerar resposta em linguagem natural
        answer = generate_answer(question, clean_sql, df)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"Pipeline concluído em {elapsed_ms}ms (cache={from_cache})")

        return QueryResult(
            question=question,
            sql=clean_sql,
            df=df,
            answer=answer,
            execution_time_ms=elapsed_ms,
            cached=from_cache,
        )

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"Erro no pipeline: {exc}")
        return QueryResult(
            question=question,
            sql=raw_sql if "raw_sql" in dir() else "",
            df=pd.DataFrame(),
            answer="",
            execution_time_ms=elapsed_ms,
            error=str(exc),
        )
