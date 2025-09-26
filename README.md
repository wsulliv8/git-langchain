# Git Odyssey

> Every repo has a story

# Problem

Today’s AI coding assistants (Cursor, GitHub Copilot, etc.) work only on the **current snapshot** of a codebase.

- They can’t answer queries about previous changes
- They can’t explain the **evolution** of the system across commits.
- Developers lose valuable historical context unless they manually read commit logs and diffs.

# Vision

Bring version control history into the AI development experience.
Instead of treating a repo as a static snapshot, treats it as a **narrative**.

- Git Odyssey automatically generates **natural-language summaries** of commits and exposes them to AI tools.
- Developers can ask questions like:
  - "When was UserManager refactored into AccountService?"
  - "Show me all commits where logging changed in the payment pipeline."
  - "Summarize the evolution of error handling in this module over time."

# Features

**Commit Analysis**

- For each commit, Git Odyssey runs an AI model over the diff.
- Produces a structured summary: changed files, added/removed functions, intent (e.g. bug fix, refactor, feature addition).

**AI Query Layer**

- Summaries are stored as metadata alongside commit IDs.
  - Indexed for semantic search (vector DB).
- Developers ask natural-language questions.
- Odyssey retrieves relevant commit summaries and diffs.
- Answers are grounded in the repo’s **evolution**, not just its current state.

# Use Cases

- **Onboarding:** New developers quickly understand why the code looks the way it does.
- **Knowledge preservation**: Commit messages are often sparse; Odyssey generates richer natural-language narratives.
- **Change justification:** Document historical reasoning for audits or reviews.
- **Evolutionary codegen:** Generate new code that respects past decisions and patterns.

# Technical Considerations

- **Integration**: Git Odyssey can run as a CLI tool, a website, a desktop application, a GitHub Action, or plugin inside IDEs like Cursor.
- **Scalability**: Incremental updates (process new commits only).
- **Model choice**: Summarization models fine-tuned on diffs + commit messages.
- **Storage**: Lightweight DB (SQLite/Vector DB) alongside repo metadata.
- **Privacy**: Local-first option (process commits without sending code externally).

# Interactive Git History

```bash
❯ git log --graph
* commit a1b2c3 (main)
|  Summary: "Introduced error logging for payment failures."
|
* commit d4e5f6
|  Summary: "Refactored UserManager into AccountService for modularity."
|
| * commit g7h8i9 (feature/api)
| | Summary: "Added initial REST endpoints for account management."
| |
| * commit j0k1l2
| | Summary: "Bug fix: corrected validation on signup form."
|/
* commit m3n4o5
   Summary: "Initial commit: project scaffolding with CI setup."

```

In a UI (web/IDE plugin), this graph could be **interactive**:

- **Click a node** see full diff + AI summary + commit message side-by-side.
- **Hover over a branch** get a high-level summary of what that branch contributed.
- **Search box** ask natural language questions:
  - _“Show me all commits related to error handling.”_
  - _“When did we first introduce JWT authentication?”_
  - _“Summarize all changes to_ [_payment.py_](http://payment.py/)_.”_

The system retrieves the relevant commit summaries and highlights those nodes on the graph.

Think of it as a **visual map of your repository’s history**, but instead of showing only commit hashes and author names, each commit node also carries an **AI-generated natural language summary** of the changes.

### **Structure**

- **Nodes = commits**
  - Each node displays:
    - Commit hash (short form)
    - Author + date
    - AI-generated summary (e.g., _“Refactored_ _UserManager_ _into_ _AccountService_ _to simplify authentication logic”_)
- **Edges = parent/child relationships**
  - Shows branches and merges visually, just like `git log --graph` but with richer context.
- **Branches = color-coded paths**
  - Different lines for `main`, `feature/`, and `hotfix/` branches.

# **High-level Architecture**

1. **Ingest**: Walk the repo (all commits or incremental since last run), collect snapshots + diffs + metadata (PRs, issues).
2. **Normalize**: Build structured objects (Commit, FileDelta, Hunk, PR, Issue).
3. **Summarize**: Create machine-readable + human summaries per unit (hunk ->file->commit->PR->branch->release).
4. **Index**: Store content and embeddings in a _hybrid index_; vector (semantic) + keyword/field (exact, time, path).
5. **Retrieve**: For a natural-language question, retrieve the most relevant commits/diffs/snippets.
6. **Assemble context**: Compress to fit the LLM’s window (hierarchical, query-aware).
7. **Answer with citations**: Include pointers to commit SHAs, files, hunk ranges.

### Ingestion

Use git plumbing to iterate commits:

- **Blobs/snapshots**: for current code questions.
- **Diffs**: parent -> unified diffs; keep hunks with line ranges.
- **Metadata**: author, date, message, parents, branch; PR title/body, linked issues (via API or conventional commit syntax).

### Normalization

Convert raw git outputs into typed, consistent objects.

- `Commit{ sha, parents[], author, date, message, branchHints[], tagHints[] }`
- `FileDelta{ sha, pathOld, pathNew, status(Add/Mod/Del/Rename), lang, locAdd, locDel }`
- `Hunk{ sha, pathNew, startOld, lenOld, startNew, lenNew, text }`
- `PR{ id, title, body, state, createdAt, mergedAt, commits[], issues[] }`
- `Issue{ id, title, body, labels[], closedAt }`

### Summarizer

Generate concise summaries for each granularity.

- **Hunk summary** ($\leq$ 1–2 sentences, structured tags):
- **FileDelta summary:** roll up hunk intents; list key symbols/files affected.
- **Commit summary:** combine file summaries + commit message + PR body snippets.
- **PR summary:** group commits; produce release-note style output; classify breaking changes.
- **Branch/Release summary:** aggregate over ranges or tags.

### Indexer

Make everything searchable by semantics and by fields.

- **Vector index**
  - Hunk summaries, file summaries, commit summaries, PR summaries
- **Keyword/field index** (Elasticsearch/OpenSearch or Postgres):
  - Fields: sha, path, lang, author, date, branch, tags(intents), issueIds, prId.
- **Graph links** (lightweight):
  - Edges: Commit->FileDelta->Hunk, Commit->PR->Issue, Child Commit->Parent Commit
- **TTL & compaction:** keep raw diffs, summaries, embeddings; evict old large blobs if storage constrained, retain summaries.

## **Retriever**

**Goal:** Given a natural-language question, gather the most relevant evidence.

- **Hybrid retrieval steps:**
  1. Vector search top-K (e.g., 50) across summaries.
  2. Re-rank with BM25 and filters (time window, path, branch).
  3. Expand neighbors in graph (include PR/Issue texts for top hits).
- **Filters:** path:src/payments, after:2024-01-01, branch:main
- **Ranking features:** recency boosts, PR merged commits boost, intent match boost.

## **Context Assembler**

Fit strongest information into model’s context window

- **Budgeting:** allocate tokens per “evidence unit”:
  - Commit summary (short), top 1–3 hunk summaries, minimal raw diff lines (unified, clipped), PR excerpt (rationale lines only).
- **Compression:**
  - Merge overlapping hunks; strip unchanged lines.
  - Generate “mini-abstracts” of long PRs.
  - Prefer structured bullet points over prose to save tokens.
- **Citations:** sha, path:lineRange, prId, issueId.
  - Example: d4e5f6@src/auth/account_service.py:120-148 (PR#482)

## **Prompt Assembler**

Generate the prompt for the LLM

- **System**: "You are Git Odyssey... An AI tool that summarizes git commit history changes and answers queries based on the code changes. Always cite evidence by SHA/path/line."
- **Context**: assembled evidence pack.
- **Instruction**: concise answer + bullets + citations; admit uncertainty when evidence is weak;

## **UI / Integrations**

**Web app:** Timeline graph, faceted search (path/intent/time), commit cards with expand-diff, PR pane, "Ask" chat dock.

# Tech Stack

## **Core Ingestion & Processing**

- **Python:** rich ecosystem for Git (pygit2, GitPython), NLP, embeddings, orchestration.

## **Summarization & LLM Layer**

- **Model orchestration:**
  - **LangChain** or **LlamaIndex** -> for retrieval, chunking, context assembly.
- **LLM choices:**
  - **Hosted APIs (fast MVP):** GPT-4o, Claude, Gemini.
  - **Local / self-hosted (for privacy):** Llama 3, DeepSeek, CodeLlama, deployed with vLLM or Ollama.
- **Summarization pipeline:** structured prompts -> hunk -> file -> commit -> PR -> branch -> release (cached in DB).

## **Indexing & Retrieval**

- **Vector DB:**
  - **pgvector** (Postgres extension) -> simplest, pairs structured + vector queries.
- **Keyword search:**
  - Postgres full-text search or Elasticsearch/OpenSearch for commit messages, PR text, issue IDs.
- **Graph relations:** Neo4j for Commit <-> PR <-> Issue <-> Hunk.

## **Data Storage**

- **Postgres** -> canonical store for commits, diffs, summaries, PR metadata.
- **Blob storage** → for raw diffs, large snapshots, logs if needed.
- **Schema example:** commit, file_delta, hunk, summary, embedding.

## **Backend Services**

- **FastAPI (Python)** -> async, easy API for chat/IDE/UI integration.

## **Frontend**

- **Web App:**
  - **Next.js + React + Tailwind** -> modern, flexible UI.
  - Libraries: **React Flow** for Git graph
