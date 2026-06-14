# Roadmap — Sistema RAG com citações (Projeto Portfólio #2)

> Como usar este documento: cada fase tem um objetivo, os entregáveis esperados e um
> prompt pronto para colar no Claude Code. Os prompts assumem que as fases anteriores
> já foram concluídas e que você está na raiz do repositório. Substitua `RAG`
> pelo nome escolhido (sugestões: Citon, SourceLens, Veris, Citely, Cited).

## Stack definitiva

| Camada | Escolha | Por quê |
|---|---|---|
| Backend | Python 3.11 + FastAPI | RAGAS, LangChain/LlamaIndex, unstructured, sentence-transformers — tudo Python-first. Diversifica o portfólio frente ao Nexus (Node). |
| Vector DB | Qdrant (Docker local / Qdrant Cloud free para demo) | Hybrid search (denso + sparse/BM25) e filtros de metadata nativos. |
| Metadados / app data | PostgreSQL | Documentos, chunks (índice para o source viewer), histórico de conversas. |
| Cache | Redis | Cache de embeddings de query e de respostas repetidas. |
| Embeddings | OpenAI `text-embedding-3-small`, atrás de `EmbeddingProvider` | Barato, simples; interface permite trocar por BGE local depois. |
| LLM (geração) | Claude (Anthropic API), atrás de `LLMProvider`, saída estruturada | `answer` com marcadores `[n]` + `citations: [{number, document, page, section, quote, chunk_id}]`. |
| Re-ranking | Cross-encoder (`bge-reranker-v2-m3` via `sentence-transformers`) | Diferencial — separa "RAG básico" de "RAG bem pensado". |
| Avaliação | RAGAS | Faithfulness, answer relevancy, context precision/recall + métrica própria de citation accuracy. |
| Observabilidade | Langfuse (tracing LLM) + Prometheus/Grafana (métricas de serviço) + logging estruturado | Reaproveita o conhecimento de Prometheus/Grafana do Nexus. |
| Frontend | React + Vite + TypeScript | Reaproveita padrões do Nexus. |
| Deploy | Docker Compose (dev/prod); manifests K8s opcionais na fase final | K8s+Helm já foi provado no Nexus — não é o foco deste projeto. |

## Convenções gerais

- **Idioma**: todo código, comentários, docstrings, mensagens de commit, README e
  documentação técnica em **inglês** (projeto de portfólio para vagas internacionais).
  Este roadmap está em português só para você acompanhar.
- **Branches**: uma branch por fase (`feature/phase-N-description`), PR + merge ao
  final de cada fase.
- **Definition of done de cada fase**: testes passando, `docker-compose up` rodando
  ponta a ponta, README atualizado (seção "status"/"what's implemented so far").
- **Commits incrementais**: peça ao Claude Code para comitar em pontos lógicos dentro
  da fase, não só no final.

## Estrutura do repositório (alvo final)

```
/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers
│   │   ├── core/            # config, logging, security
│   │   ├── services/         # ingestion, embeddings, retrieval, generation, cache
│   │   ├── models/             # pydantic schemas + ORM models
│   │   ├── db/                  # session, migrations (alembic)
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api/
│   │   └── main.tsx
│   ├── package.json
│   └── Dockerfile
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   ├── grafana/
│   └── k8s/                 # fase 8, opcional
├── eval/
│   ├── dataset.json
│   └── run_ragas.py
└── README.md
```

## Cronograma resumido (ritmo part-time, ~2-4h por sessão)

| Fase | Foco | Sessões estimadas |
|---|---|---|
| 0 | Setup e arquitetura base | 1-2 |
| 1 | Ingestão e chunking com metadados | 3-4 |
| 2 | Embeddings + Qdrant | 2-3 |
| 3 | Retrieval híbrido + re-ranking | 2-3 |
| 4 | Geração com citações estruturadas | 3-4 |
| 5 | Frontend: chat + citações clicáveis | 4-5 |
| 6 | Avaliação com RAGAS | 2-3 |
| 7 | Observabilidade, cache e custos | 2-3 |
| 8 | Deploy e CI/CD | 2-3 |

Total: ~21-30 sessões — aproximadamente 6-10 semanas em ritmo de noites/fins de semana.

---

## Fase 0 — Setup e arquitetura base

**Objetivo**: monorepo funcional, ambiente local via Docker Compose, FastAPI e React
rodando, lint/test/CI configurados.

**Entregáveis**
- Estrutura de pastas conforme árvore acima.
- `docker-compose.yml` com backend, frontend, qdrant, postgres, redis.
- FastAPI: app skeleton, Pydantic Settings (`.env`), endpoint `GET /health` checando
  conectividade com Postgres, Qdrant e Redis.
- React + Vite + TS: layout base + chamada ao `/health` exibindo status.
- `ruff` + `black` no backend, `eslint` + `prettier` no frontend.
- `pytest` configurado com um smoke test.
- `.github/workflows/ci.yml` rodando lint + testes em push/PR.
- README com visão geral do projeto, diagrama de arquitetura (Mermaid ou ASCII) e
  instruções de setup local.

**Prompt para Claude Code**

```
Estou começando um projeto de portfólio: um sistema RAG (Retrieval-Augmented
Generation) com citações clicáveis, chamado [NOME_DO_PROJETO]. Stack: backend
Python 3.11 + FastAPI, frontend React + Vite + TypeScript, Qdrant como vector
database, PostgreSQL para metadados de documentos/chunks/conversas, Redis para
cache. Tudo orquestrado via Docker Compose para desenvolvimento local.

Crie a estrutura inicial do monorepo:

1. /backend: projeto FastAPI com Pydantic Settings (variáveis via .env e
   .env.example), estrutura de pastas app/api, app/core, app/services,
   app/models, app/db, e app/main.py. Implemente GET /health retornando o
   status da aplicação e a conectividade com Postgres, Qdrant e Redis.
   Configure ruff + black em pyproject.toml e pytest com um teste smoke
   para /health.

2. /frontend: Vite + React + TypeScript, layout básico (header + container),
   uma chamada fetch a /health exibindo o status retornado. Configure
   ESLint + Prettier.

3. /infra/docker-compose.yml orquestrando backend, frontend, qdrant,
   postgres e redis, com volumes persistentes e variáveis de ambiente
   via .env.example.

4. README.md com: visão geral do projeto, diagrama de arquitetura em
   Mermaid mostrando ingestion pipeline -> vector store -> retrieval ->
   generation -> frontend, e instruções de "how to run locally".

5. .github/workflows/ci.yml rodando lint e testes (backend e frontend)
   em push e pull request.

Todo o código, comentários, docstrings e documentação devem estar em
inglês. Ao final, suba os containers com docker-compose e confirme que
/health responde 200 com todas as dependências conectadas.
```

---

## Fase 1 — Ingestão e chunking com metadados

**Objetivo**: pipeline que recebe PDF/DOCX/MD/HTML, extrai texto preservando
metadados de origem (arquivo, página, seção/heading) e gera chunks com overlap,
persistidos no Postgres.

**Entregáveis**
- Modelos: `Document` (id, filename, content_type, status, uploaded_at) e `Chunk`
  (id, document_id, chunk_index, content, token_count, page_number, section_path,
  char_start, char_end).
- Parsers por tipo:
  - PDF (`pypdf`/`pdfplumber`) — extrai número de página.
  - DOCX (`python-docx`) — extrai hierarquia de headings (estilos "Heading 1/2/3").
  - Markdown (`markdown-it-py`) — extrai hierarquia de headings via tokens.
  - HTML (`BeautifulSoup4`) — extrai hierarquia via `h1`-`h6`.
- Chunking baseado em tokens (`tiktoken`), ~300-500 tokens com ~50 de overlap,
  mantendo `page_number`/`section_path`/offsets de caracteres por chunk.
- Endpoints: `POST /documents` (upload + processamento em background),
  `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/chunks`.
- Testes com um arquivo de exemplo de cada tipo, verificando que os metadados
  de página/seção são preservados corretamente.

**Prompt para Claude Code**

```
Contexto: projeto [NOME_DO_PROJETO] (RAG com citações), backend FastAPI já
configurado na fase anterior.

Implemente o pipeline de ingestão de documentos:

1. Modelos SQLAlchemy + Pydantic schemas:
   - Document: id (uuid), filename, content_type, status
     (pending/processing/indexed/failed), uploaded_at.
   - Chunk: id (uuid), document_id (FK), chunk_index, content (text),
     token_count, page_number (nullable, int), section_path (nullable,
     string, ex: "Chapter 2 > Section 2.1"), char_start, char_end.
   Configure Alembic para migrations.

2. Parsers em app/services/parsing/, um módulo por tipo de arquivo:
   - pdf_parser.py: usa pypdf ou pdfplumber, retorna lista de (page_number,
     text) por página.
   - docx_parser.py: usa python-docx, percorre paragraphs, identifica
     headings pelo estilo (Heading 1/2/3) para montar section_path.
   - markdown_parser.py: usa markdown-it-py, percorre tokens, monta
     section_path a partir dos headings (#, ##, ###).
   - html_parser.py: usa BeautifulSoup4, mesma lógica de section_path a
     partir de h1-h6.
   Cada parser deve retornar uma lista de blocos de texto com seus
   metadados (page_number quando aplicável, section_path).

3. Chunking em app/services/chunking.py: usando tiktoken, divida os blocos
   em chunks de ~300-500 tokens com overlap de ~50 tokens, preservando
   page_number/section_path do bloco de origem e calculando char_start/
   char_end relativos ao texto original (necessário para destacar a
   citação no frontend depois).

4. Endpoints em app/api/documents.py:
   - POST /documents: recebe upload (multipart), salva o arquivo,
     cria o Document com status=pending, dispara o processamento em
     BackgroundTasks (parse -> chunk -> persist chunks -> status=indexed
     ou failed em caso de erro).
   - GET /documents: lista documentos com status.
   - GET /documents/{id}: detalhes de um documento.
   - GET /documents/{id}/chunks: lista chunks de um documento com seus
     metadados.

5. Testes em tests/: um arquivo de exemplo para cada tipo (PDF, DOCX, MD,
   HTML) em tests/fixtures/, verificando que page_number/section_path são
   extraídos corretamente e que os chunks têm overlap consistente.

Todo o código, comentários e mensagens de commit em inglês.
```

---

## Fase 2 — Embeddings + Qdrant

**Objetivo**: gerar embeddings para os chunks indexados e armazená-los no Qdrant
com suporte a busca híbrida (denso + sparse/BM25).

**Entregáveis**
- Interface `EmbeddingProvider` (abstract) + implementação
  `OpenAIEmbeddingProvider` (`text-embedding-3-small`, 1536 dimensões).
- Collection no Qdrant com vetor denso + vetor sparse (BM25 via FastEmbed).
- Job de indexação: lê chunks com `status != indexed_in_vector_store` do
  Postgres, gera embeddings em batch, faz upsert no Qdrant (point id = chunk
  id, payload com `document_id`, `page_number`, `section_path`, `content`).
- Endpoint para disparar/acompanhar indexação (ou trigger automático após a
  fase 1).
- Idempotência: reindexar não duplica pontos.
- Testes de integração contra o Qdrant do docker-compose.

**Prompt para Claude Code**

```
Contexto: projeto [NOME_DO_PROJETO], pipeline de ingestão e chunking já
implementado (chunks persistidos no Postgres com metadados de página/seção).

Implemente a geração de embeddings e indexação no Qdrant:

1. app/services/embeddings/base.py: defina uma interface abstrata
   EmbeddingProvider com um método embed(texts: list[str]) ->
   list[list[float]].

2. app/services/embeddings/openai_provider.py: implementação usando a
   API da OpenAI, modelo text-embedding-3-small (1536 dimensões), com
   batching e retry/backoff em caso de rate limit.

3. app/services/vector_store/qdrant_client.py: configure o cliente Qdrant
   e crie (se não existir) uma collection com:
   - vetor denso "dense" (1536 dim, cosine distance)
   - vetor sparse "sparse" (BM25 via FastEmbed, para suportar hybrid search)

4. app/services/indexing.py: job de indexação que:
   - busca chunks com status pending_vector_index no Postgres
   - gera embeddings densos via EmbeddingProvider e sparse via FastEmbed
     BM25
   - faz upsert no Qdrant usando o id do chunk como point id, e payload
     contendo document_id, document_filename, page_number, section_path
     e content (para exibir no source viewer sem nova query ao Postgres)
   - atualiza o status do chunk para indexed após sucesso
   Garanta idempotência: reindexar os mesmos chunks não cria pontos
   duplicados (upsert por id).

5. Endpoint POST /documents/{id}/index para disparar a indexação de um
   documento específico (ou ajuste o BackgroundTask da fase 1 para chamar
   este job automaticamente após o chunking).

6. Testes de integração em tests/ usando o Qdrant do docker-compose:
   verifique que após indexar, uma busca simples por similaridade retorna
   o chunk esperado, e que reindexar não duplica pontos na collection.

Todo o código, comentários e mensagens de commit em inglês.
```

---

## Fase 3 — Retrieval híbrido + re-ranking

**Objetivo**: dado uma pergunta, recuperar os chunks mais relevantes combinando
busca densa + BM25 (fusão via RRF no Qdrant) e re-ranking com cross-encoder.

**Entregáveis**
- `RetrievalService`: embed da query, hybrid search no Qdrant (top ~20 via
  RRF), re-ranking com cross-encoder para reduzir a top-k (~5).
- Suporte a filtros por metadata (`document_ids`, etc.) via payload do Qdrant.
- Endpoint `POST /retrieve` (uso interno/debug) retornando chunks + scores +
  metadados.
- Testes comparando resultados de busca puramente vetorial vs. híbrida em
  casos onde palavras-chave exatas importam (ex: nomes próprios, códigos).

**Prompt para Claude Code**

```
Contexto: projeto [NOME_DO_PROJETO], chunks já indexados no Qdrant com
vetores densos e sparse (BM25), payload contendo document_id, page_number,
section_path e content.

Implemente o serviço de retrieval híbrido:

1. app/services/retrieval/cross_encoder.py: carregue um cross-encoder
   (ex: BAAI/bge-reranker-v2-m3 via sentence-transformers), com um método
   rerank(query: str, candidates: list[dict]) -> list[dict] que retorna os
   candidatos ordenados por relevância com um campo rerank_score.

2. app/services/retrieval/service.py: RetrievalService com um método
   retrieve(query: str, top_k: int = 5, filters: dict | None = None):
   - gera o embedding denso e sparse (BM25) da query
   - executa uma query híbrida no Qdrant combinando os dois vetores com
     fusão RRF (Reciprocal Rank Fusion), retornando os top ~20 candidatos
   - aplica filtros de payload quando filters.document_ids for fornecido
   - re-rankeia os candidatos com o cross-encoder e retorna os top_k
   - cada item retornado deve conter: chunk_id, document_id,
     document_filename, page_number, section_path, content, dense_score,
     rerank_score

3. Endpoint POST /retrieve em app/api/retrieval.py (uso interno/debug),
   recebendo {"query": str, "top_k": int, "document_ids": list[str] | None}
   e retornando a lista de chunks com scores e metadados.

4. Testes em tests/: monte um pequeno conjunto de documentos de teste com
   pelo menos um caso onde uma palavra-chave exata (ex: um nome próprio ou
   código de erro) só é encontrada de forma confiável com BMERT/BM25 -
   compare os resultados de busca puramente densa vs. híbrida e confirme
   que a híbrida recupera o chunk correto.

Todo o código, comentários e mensagens de commit em inglês.
```

---

## Fase 4 — Geração com citações estruturadas

**Objetivo**: orquestrar retrieval + LLM para gerar respostas com citações
estruturadas, em streaming.

**Entregáveis**
- Interface `LLMProvider` + implementação `AnthropicLLMProvider`, usando saída
  estruturada (tool use / JSON schema):
  `{"answer": "... [1] ... [2] ...", "citations": [{"number": 1, "document_id":
  ..., "document_name": ..., "page": ..., "section": ..., "quote": "...",
  "chunk_id": ...}]}`.
- Prompt template: instrui o modelo a responder **apenas** com base no
  contexto fornecido, citar com `[n]`, incluir uma `quote` verbatim do chunk
  (para validação posterior), e responder "não sei" quando o contexto for
  insuficiente.
- Endpoint `POST /chat` com streaming via SSE: retrieval -> monta prompt com
  os chunks numerados -> chama o LLM -> streama a resposta.
- Persistência de conversas no Postgres (mensagens + citações associadas).
- Testes: respostas citam corretamente os chunks corretos; resposta "não sei"
  quando o contexto não cobre a pergunta.

**Prompt para Claude Code**

```
Contexto: projeto [NOME_DO_PROJETO], RetrievalService implementado e
funcional (retorna chunks com document_id, page_number, section_path,
content e scores).

Implemente a geração de respostas com citações estruturadas:

1. app/services/llm/base.py: interface abstrata LLMProvider com um método
   generate(prompt: str, context_chunks: list[dict]) que retorna um objeto
   estruturado: {"answer": str, "citations": list[Citation]}, onde
   Citation = {number, document_id, document_name, page, section, quote,
   chunk_id}.

2. app/services/llm/anthropic_provider.py: implementação usando a API da
   Anthropic (Claude). Use tool use / structured output para forçar o
   schema acima. O prompt do sistema deve instruir o modelo a:
   - responder somente com base nos chunks de contexto fornecidos
     (numerados [1], [2], ... na ordem em que aparecem no prompt)
   - inserir os marcadores [n] no texto da resposta nos pontos onde cada
     fonte é usada
   - para cada citação usada, incluir em "citations" uma "quote" que seja
     um trecho literal (verbatim) do chunk correspondente, para permitir
     validação posterior
   - responder "I don't have enough information to answer this" (em
     inglês, já que o conteúdo do app será em inglês) quando os chunks de
     contexto não cobrirem a pergunta, sem inventar citações

3. app/services/chat.py: ChatService.ask(question: str, conversation_id:
   str | None) que:
   - chama RetrievalService.retrieve(question)
   - monta o prompt numerando os chunks recuperados como fontes [1]..[n]
   - chama LLMProvider.generate()
   - persiste a pergunta, a resposta e as citações associadas no Postgres
     (modelos Conversation e Message)

4. Endpoint POST /chat (SSE) em app/api/chat.py: recebe {"question": str,
   "conversation_id": str | None}, streama a resposta do LLM token a
   token (ou em chunks), e ao final envia um evento com o objeto
   "citations" completo.

5. Testes em tests/: usando um conjunto de documentos de teste,
   - verifique que perguntas cobertas pelo contexto retornam citações
     cujas "quote" realmente existem nos chunks referenciados
   - verifique que uma pergunta sem relação com os documentos retorna a
     resposta de "não sei" sem citações inventadas

Todo o código, comentários e mensagens de commit em inglês.
```

---

## Fase 5 — Frontend: chat + citações clicáveis

**Objetivo**: interface de chat que renderiza as citações `[n]` como elementos
clicáveis, abrindo um painel com o trecho original em destaque.

**Entregáveis**
- Componente de chat com streaming (consumindo o SSE de `POST /chat`).
- Parser do texto da resposta: identifica `[n]` e renderiza como badge
  clicável.
- "Source Viewer": painel/modal que busca o chunk (`GET /chunks/{id}`),
  mostra documento, página/seção, e destaca a `quote` citada dentro do
  trecho (usando `char_start`/`char_end`).
- Página de gerenciamento de documentos: upload com progresso, lista com
  status (pending/processing/indexed/failed), exclusão.
- Visual consistente (reaproveitar tokens de design do Nexus, se aplicável).

**Prompt para Claude Code**

```
Contexto: projeto [NOME_DO_PROJETO], backend expõe POST /chat (SSE) que
retorna {"answer": "... [1] ... [2] ...", "citations": [{number,
document_id, document_name, page, section, quote, chunk_id}, ...]}, e
GET /chunks/{id} retornando {content, char_start, char_end,
document_name, page, section}.

Implemente o frontend de chat com citações:

1. Componente ChatWindow (React + TS): input de pergunta, lista de
   mensagens (usuário/assistente), consumindo o streaming SSE de
   POST /chat e exibindo a resposta token a token.

2. Componente CitedAnswer: recebe o texto da resposta e a lista de
   citations, faz parsing dos marcadores [n] no texto e renderiza cada
   um como um badge clicável (ex: superscript ou pill numerado). Ao
   clicar, abre o SourceViewer para a citação correspondente.

3. Componente SourceViewer (modal ou painel lateral): dado um chunk_id,
   busca GET /chunks/{id}, exibe document_name, page/section, e o
   conteúdo do chunk com a "quote" citada destacada (highlight) usando
   char_start/char_end para localizar o trecho dentro do content.
   Inclua um link/botão para abrir o documento original (se aplicável).

4. Página DocumentsPage: upload de arquivos (drag-and-drop ou input,
   com barra de progresso via POST /documents), tabela listando
   documentos com status (pending/processing/indexed/failed, com
   polling ou refresh manual), e ação de exclusão.

5. Roteamento básico (ex: react-router) entre a página de chat e a
   página de documentos. Estilo visual limpo e consistente — se fizer
   sentido, reaproveite tokens de design (cores, tipografia, espaçamento)
   do projeto Nexus para manter identidade visual entre os dois projetos
   do portfólio.

Todo o código, comentários e mensagens de commit em inglês.
```

---

## Fase 6 — Avaliação com RAGAS

**Objetivo**: medir a qualidade do RAG (retrieval e geração) com RAGAS, mais
uma métrica própria de "citation accuracy".

**Entregáveis**
- Dataset de avaliação: ~20-30 perguntas com resposta de referência (ground
  truth), baseado em um conjunto fixo de documentos de teste.
- Script `eval/run_ragas.py`: roda o pipeline RAG para cada pergunta, coleta
  `contexts`/`answer`, computa `faithfulness`, `answer_relevancy`,
  `context_precision`, `context_recall` via RAGAS.
- Métrica própria de citation accuracy: para cada citação retornada, verifica
  se a `quote` aparece (ou é muito similar) no conteúdo do chunk referenciado.
- Relatório (JSON/Markdown) com scores agregados e por pergunta.
- (Opcional) GitHub Action manual/agendada que roda o eval e publica o
  relatório como artifact.

**Prompt para Claude Code**

```
Contexto: projeto [NOME_DO_PROJETO], pipeline completo de chat (retrieval +
geração com citações) funcionando via ChatService.

Implemente a avaliação com RAGAS:

1. eval/dataset.json: crie um dataset com 20-30 perguntas baseadas em um
   conjunto de 3-5 documentos de teste (use os mesmos documentos de teste
   das fases anteriores ou adicione novos), cada entrada contendo:
   {"question": str, "ground_truth": str, "expected_document_ids": [...]}
   (expected_document_ids ajuda a validar context_recall manualmente se
   necessário).

2. eval/run_ragas.py: script que, para cada pergunta do dataset:
   - chama ChatService.ask() (ou diretamente RetrievalService +
     LLMProvider) para obter contexts (chunks recuperados) e answer
   - monta o dataset no formato esperado pelo RAGAS (question, contexts,
     answer, ground_truth)
   - computa as métricas faithfulness, answer_relevancy,
     context_precision e context_recall via biblioteca ragas
   - implementa uma métrica adicional citation_accuracy: para cada
     citação retornada pela resposta, verifica (via comparação de string
     normalizada/similaridade) se a "quote" da citação está contida no
     content do chunk referenciado pelo chunk_id; reporta a proporção de
     citações válidas
   - salva um relatório em eval/results/report.json e um resumo legível
     em eval/results/report.md (scores agregados + por pergunta,
     destacando as piores perguntas para análise)

3. Adicione um comando (ex: Makefile target ou script em
   backend/pyproject.toml) "make eval" que roda eval/run_ragas.py contra
   o ambiente local (docker-compose up necessário).

4. (Opcional) .github/workflows/eval.yml: workflow disparado manualmente
   (workflow_dispatch) ou semanalmente, que sobe o docker-compose, roda
   o eval e publica eval/results/report.md como artifact do workflow.

Todo o código, comentários, mensagens de commit e o relatório (textos
fixos) em inglês.
```

---

## Fase 7 — Observabilidade, cache e custos

**Objetivo**: logging estruturado, tracing (Langfuse), cache (Redis), métricas
(Prometheus/Grafana) e estimativa de custo por query.

**Entregáveis**
- Logging estruturado (`structlog`): por query, registra texto, chunks
  recuperados (ids + scores), chunks pós-rerank, resposta, latências por
  etapa, tokens de prompt/completion, custo estimado em USD.
- Integração com Langfuse: trace da pipeline (retrieval + geração como spans
  aninhados).
- Cache Redis: embeddings de queries repetidas (hash da query normalizada) e
  respostas completas para queries idênticas (TTL configurável).
- Métricas Prometheus: contagem de requests, histogramas de latência por
  etapa, taxa de cache hit, expostas em `/metrics`.
- Dashboard Grafana (JSON) reaproveitando a estrutura do Nexus, com painel de
  custo estimado diário.

**Prompt para Claude Code**

```
Contexto: projeto [NOME_DO_PROJETO], pipeline de chat completo e avaliado.

Implemente observabilidade, cache e tracking de custos:

1. Logging estruturado: configure structlog para emitir logs JSON. Em
   ChatService.ask(), registre por requisição: a query, os chunk_ids e
   scores retornados pelo retrieval, os chunk_ids pós-rerank, a resposta
   gerada, latência de cada etapa (retrieval, rerank, generation), tokens
   de prompt e completion, e o custo estimado em USD (com base em uma
   tabela de preço por modelo configurável em app/core/config.py).

2. Integração Langfuse: instrumente ChatService.ask() para criar um trace
   por requisição, com spans para retrieval, rerank e generation,
   incluindo os metadados relevantes (chunk_ids, scores, tokens).

3. Cache Redis em app/services/cache.py:
   - cache de embeddings: antes de gerar o embedding de uma query, calcule
     um hash da query normalizada e verifique o cache; se houver hit,
     reutilize o embedding
   - cache de respostas: para queries idênticas (mesmo hash de query e
     mesmos document_ids de filtro), cacheie a resposta completa
     (answer + citations) com um TTL configurável (ex: 1 hora)
   - exponha as duas flags de hit/miss nos logs estruturados e nas
     métricas

4. Métricas Prometheus em app/core/metrics.py, expostas em GET /metrics:
   - contador de requests por endpoint
   - histograma de latência por etapa (retrieval, rerank, generation,
     total)
   - taxa de cache hit (embeddings e respostas)
   - gauge de custo estimado acumulado (USD)

5. infra/grafana/dashboard.json: dashboard reaproveitando a estrutura
   visual usada no projeto Nexus (mesmos painéis de latência/throughput
   quando aplicável), adicionando um painel novo de "estimated daily LLM
   cost (USD)" e um painel de cache hit rate.

Todo o código, comentários, labels de métricas e mensagens de commit em
inglês.
```

---

## Fase 8 — Deploy e CI/CD

**Objetivo**: Dockerfiles de produção, CI/CD completo e deploy de uma demo
pública.

**Entregáveis**
- Dockerfiles multi-stage (backend e frontend).
- `docker-compose.prod.yml`.
- GitHub Actions: build + push de imagens (GHCR), testes (unitários +
  integração), eval RAGAS como job agendado/manual (não em todo PR, por
  custo).
- (Opcional) manifests K8s/Helm reaproveitando padrões do Nexus.
- Deploy de uma demo pública (ex: Fly.io/Render para backend+frontend, Qdrant
  Cloud free tier, Neon/Supabase free tier para Postgres) com alguns
  documentos de exemplo pré-indexados.

**Prompt para Claude Code**

```
Contexto: projeto [NOME_DO_PROJETO], aplicação completa e testada
localmente via docker-compose.

Prepare o deploy de produção e CI/CD:

1. backend/Dockerfile e frontend/Dockerfile: builds multi-stage,
   otimizados (cache de dependências, imagem final mínima, usuário não-
   root).

2. infra/docker-compose.prod.yml: variante de produção do compose,
   sem volumes de desenvolvimento, com variáveis de ambiente via secrets/
   .env, restart policies e healthchecks.

3. .github/workflows/cicd.yml:
   - job de lint + test (backend e frontend) em todo push/PR
   - job de build e push das imagens para GHCR em merge na main
   - job de eval RAGAS via workflow_dispatch (manual) ou em schedule
     semanal, publicando eval/results/report.md como artifact
   - (opcional) job de deploy automático para o ambiente de demo após
     merge na main

4. (Opcional) infra/k8s/: manifests ou Helm chart para backend, frontend,
   seguindo os mesmos padrões usados no projeto Nexus (Deployments,
   Services, ConfigMaps, Secrets, Ingress). Documente no README como isso
   se relaciona com a opção de usar Qdrant Cloud/Neon para os serviços
   gerenciados.

5. Prepare um conjunto pequeno de documentos de exemplo (3-5 documentos
   públicos/sem direitos restritos) em /seed-data, e um script
   eval/seed_demo.py (ou similar) que faz upload e indexação automática
   desses documentos em um ambiente novo — para que a demo pública já
   tenha conteúdo navegável sem o visitante precisar fazer upload.

6. Atualize o README com: link da demo pública (placeholder), instruções
   de deploy, e uma seção "Architecture decisions" resumindo as escolhas
   de stack (Qdrant, hybrid search, structured citations, RAGAS,
   Langfuse) e o porquê de cada uma — isso ajuda recrutadores/
   entrevistadores a entenderem rapidamente o que foi demonstrado.

Todo o código, configuração, comentários, mensagens de commit e README em
inglês.
```

---

## Próximos passos imediatos

1. Escolha o nome do projeto e substitua `RAG` nos prompts.
2. Rode o prompt da Fase 0 no Claude Code para criar o monorepo e validar o
   ambiente local.
3. Reúna 3-5 documentos de teste variados (pelo menos um PDF com múltiplas
   páginas, um Markdown com headings, e um DOCX ou HTML) — eles serão usados
   nas fases 1, 3, 4 e 6.
4. Siga as fases em ordem; cada uma assume que a anterior está com testes
   passando e o ambiente local rodando ponta a ponta.