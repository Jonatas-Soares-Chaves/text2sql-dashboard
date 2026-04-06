# 🔍 Text-to-SQL · Análise de Dados por Linguagem Natural

> Converse com seu banco de dados em português. Sem SQL. Sem dashboards pré-definidos.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Groq](https://img.shields.io/badge/Groq-llama--3.3--70b-F55036?style=flat&logo=groq)](https://groq.com)
[![LangChain](https://img.shields.io/badge/LangChain-0.2-1C3C3C?style=flat)](https://langchain.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?style=flat&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.38-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Tests](https://img.shields.io/badge/Tests-pytest-brightgreen?style=flat&logo=pytest)](https://pytest.org)

**[🚀 Ver Demo ao Vivo](SEU_LINK_HF_SPACES)**  ·  **[📖 Documentação](#arquitetura)**

---

## O que é

Sistema que converte perguntas em português para SQL usando LLM (Groq / LLaMA 3.3 70B),
executa no PostgreSQL e responde em linguagem natural com visualização automática.

**Diferencial:** não é um chatbot genérico — é um pipeline de produção com
validação de segurança em múltiplas camadas, cache inteligente e resposta contextualizada.

---

## Demo

| Você digita | O sistema faz |
|---|---|
| *"Qual o total de receita por mês em 2024?"* | Gera SQL com DATE_TRUNC, executa, plota linha temporal |
| *"Top 5 produtos mais vendidos?"* | JOIN entre 3 tabelas, retorna tabela + gráfico de barras |
| *"Qual estado tem mais clientes VIP?"* | GROUP BY + filtro de segmento, mapa de resultados |
| *"Compare receita de 2023 vs 2024"* | CTE comparativa, delta percentual calculado |

---

## Arquitetura

```
Pergunta (PT-BR)
      │
      ▼
 [LLM — Groq]  ← System prompt com schema injetado dinamicamente
      │
      ▼
  SQL bruto
      │
      ▼
 [Validação]   ← Blacklist DDL/DML + sqlparse + LIMIT obrigatório
      │
      ▼
 [PostgreSQL]  ← Execução com timeout + máx 500 linhas
      │
      ▼
  DataFrame
      │
      ▼
 [LLM — Groq]  ← Interpreta resultado → resposta em PT-BR
      │
      ▼
  Dashboard    ← Streamlit + Plotly (gráfico automático)
```

---

## Segurança

Múltiplas camadas independentes — o sistema **nunca executa DDL ou DML** mesmo que o LLM tente gerá-lo:

1. **Blacklist explícita** — `DROP`, `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, `ALTER`, `CREATE` são detectados e bloqueados antes da execução
2. **Type check** — `sqlparse` verifica que o statement é do tipo `SELECT`
3. **LIMIT obrigatório** — adicionado automaticamente se ausente (máx 500 linhas)
4. **Timeout** — queries lentas são canceladas automaticamente (10s)
5. **Usuário read-only** — conta do banco sem permissões de escrita

---

## Stack & Decisões Técnicas

| Escolha | Alternativa considerada | Motivo |
|---|---|---|
| Groq (llama-3.3-70b) | OpenAI GPT-4 | Gratuito, <500ms de latência, sem custo de API |
| LangChain | Chamada direta à API | Retry automático, abstração de provedor, facilita troca futura |
| PostgreSQL | SQLite | Tipos de dados ricos, suporte a window functions, produção-ready |
| Pydantic v2 Settings | python-dotenv puro | Validação de tipos + suporte a HF Secrets automaticamente |
| sqlparse | Regex manual | Parsing real de AST SQL — mais robusto contra edge cases |
| Cache em memória | Redis | Zero dependência externa para portfólio |

---

## Início Rápido

```bash
git clone https://github.com/SEU_USUARIO/text2sql-portfolio
cd text2sql-portfolio
cp .env.example .env  # adicione GROQ_API_KEY

docker compose up -d
# Dashboard em http://localhost:8501
```

---

## Testes

```bash
pytest tests/ -v --cov=core --cov-report=term-missing
```


