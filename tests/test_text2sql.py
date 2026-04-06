import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.text2sql import (
    ValidationResult,
    _QueryCache,
    validate_sql,
    generate_answer,
)

@pytest.fixture
def valid_select():
    return "SELECT id, name FROM customers LIMIT 10"


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "produto": ["Notebook Dell", "iPhone 15", "Smartwatch"],
        "unidades_vendidas": [150, 320, 210],
        "receita_total": [584850.0, 1759680.0, 398790.0],
    })

class TestValidateSql:

    def test_aceita_select_simples(self, valid_select):
        result = validate_sql(valid_select)
        assert result.valid is True
        assert result.error is None

    def test_rejeita_drop(self):
        result = validate_sql("DROP TABLE customers")
        assert result.valid is False
        assert "DROP" in result.error.upper()

    def test_rejeita_delete(self):
        result = validate_sql("DELETE FROM orders WHERE id = 1")
        assert result.valid is False

    def test_rejeita_update(self):
        result = validate_sql("UPDATE customers SET name='hacked'")
        assert result.valid is False

    def test_rejeita_insert(self):
        result = validate_sql("INSERT INTO customers VALUES (1, 'x', 'x@x.com')")
        assert result.valid is False

    def test_rejeita_truncate(self):
        result = validate_sql("TRUNCATE TABLE orders")
        assert result.valid is False

    def test_rejeita_sql_vazio(self):
        result = validate_sql("")
        assert result.valid is False
        assert result.error is not None

    def test_rejeita_apenas_comentario(self):
        result = validate_sql("-- DROP TABLE customers")

        assert result.valid is False

    def test_adiciona_limit_se_ausente(self):
        sql = "SELECT * FROM customers"
        result = validate_sql(sql)
        assert result.valid is True
        assert "LIMIT" in result.cleaned_sql.upper()

    def test_preserva_limit_existente(self):
        sql = "SELECT * FROM customers LIMIT 10"
        result = validate_sql(sql)
        assert result.valid is True
        # Não deve duplicar o LIMIT
        assert result.cleaned_sql.upper().count("LIMIT") == 1

    def test_normaliza_keywords_uppercase(self):
        sql = "select id, name from customers limit 5"
        result = validate_sql(sql)
        assert result.valid is True
        assert "SELECT" in result.cleaned_sql

    def test_aceita_select_com_join(self):
        sql = """
        SELECT c.name, COUNT(o.id) as total_pedidos
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        GROUP BY c.name
        ORDER BY total_pedidos DESC
        LIMIT 10
        """
        result = validate_sql(sql)
        assert result.valid is True

    def test_aceita_select_com_subquery(self):
        sql = """
        SELECT * FROM (
            SELECT product_id, SUM(quantity) as total
            FROM order_items
            GROUP BY product_id
        ) sub
        ORDER BY total DESC
        LIMIT 20
        """
        result = validate_sql(sql)
        assert result.valid is True

    def test_rejeita_drop_disfarçado_em_comentario_inline(self):
  
        result = validate_sql("SELECT 1; DROP TABLE customers")
       
        if result.valid:
            assert "DROP" not in result.cleaned_sql.upper().split()

class TestQueryCache:

    def test_miss_retorna_none(self):
        cache = _QueryCache()
        assert cache.get("pergunta nova") is None

    def test_set_e_get(self):
        cache = _QueryCache()
        cache.set("qual o total?", "SELECT SUM(total_amount) FROM orders LIMIT 500")
        result = cache.get("qual o total?")
        assert result is not None
        assert "SUM" in result

    def test_case_insensitive(self):
        cache = _QueryCache()
        cache.set("Qual o TOTAL?", "SELECT SUM(total_amount) FROM orders LIMIT 500")

        result = cache.get("qual o total?")
        assert result is not None

    def test_respeita_max_size(self):
        cache = _QueryCache(max_size=3)
        for i in range(5):
            cache.set(f"pergunta {i}", f"SELECT {i}")

        assert len(cache._store) <= 3

    def test_ttl_expirado(self, monkeypatch):
        import time
        cache = _QueryCache()
        cache.set("pergunta velha", "SELECT 1")

        monkeypatch.setattr(
            "core.text2sql.get_settings",
            lambda: MagicMock(cache_ttl_seconds=0),
        )

        key = cache._key("pergunta velha")
        cache._store[key] = ("SELECT 1", time.time() - 999)

        result = cache.get("pergunta velha")
        assert result is None

class TestAskPipeline:

    @patch("core.text2sql._call_llm")
    @patch("core.text2sql.execute_sql")
    def test_pipeline_sucesso(self, mock_exec, mock_llm, sample_df):
        mock_llm.side_effect = [
            "SELECT p.name as produto FROM products p LIMIT 10",  # SQL
            "Os 3 produtos mais vendidos são Notebook Dell, iPhone 15 e Smartwatch.",  # resposta
        ]
        mock_exec.return_value = sample_df

        from core.text2sql import ask
        result = ask("Quais os produtos mais vendidos?")

        assert result.success is True
        assert len(result.df) == 3
        assert result.answer != ""
        assert result.execution_time_ms >= 0

    @patch("core.text2sql._call_llm")
    def test_pipeline_sql_invalido_retorna_erro(self, mock_llm):
        mock_llm.return_value = "DROP TABLE customers"  # LLM retorna SQL perigoso

        from core.text2sql import ask
        result = ask("Delete todos os clientes")

        assert result.success is False
        assert result.error is not None

    @patch("core.text2sql._call_llm")
    @patch("core.text2sql.execute_sql")
    def test_resultado_vazio_tratado(self, mock_exec, mock_llm):
        mock_llm.side_effect = [
            "SELECT * FROM orders WHERE 1=0 LIMIT 500",
            "Nenhum resultado encontrado para a consulta.",
        ]
        mock_exec.return_value = pd.DataFrame()

        from core.text2sql import ask
        result = ask("Pedidos impossíveis")

        assert result.success is True
        assert result.df.empty

class TestIntegration:
    """
    Testes que requerem banco real.
    Marcados para pular se DATABASE_URL não estiver configurado.
    """

    @pytest.fixture(autouse=True)
    def skip_without_db(self):
        import os
        from sqlalchemy.exc import OperationalError
        try:
            from db.connection import check_connection
            if not check_connection():
                pytest.skip("Banco não disponível")
        except Exception:
            pytest.skip("Banco não disponível")

    def test_schema_description_nao_vazio(self):
        from db.connection import get_schema_description
        schema = get_schema_description()
        assert "TABLE" in schema
        assert "orders" in schema
        assert "customers" in schema

    def test_executa_select_simples(self):
        from core.text2sql import execute_sql
        df = execute_sql("SELECT 1 AS test_col LIMIT 1")
        assert not df.empty
        assert "test_col" in df.columns
