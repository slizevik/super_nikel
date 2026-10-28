# Product Requirements Document (PRD) — SuperNikel

## 1. Product goal

SuperNikel is a local research assistant for a single user working with a personal library of scientific PDFs. The primary pain is not “chat with AI,” but “I have a folder full of papers and I cannot reliably find what I need, when I need it.”

The product must help the user:
- find relevant papers in a local library,
- read and index PDFs reliably,
- ask source-grounded questions,
- get answers with verifiable citations,
- later support dissertation writing and literature synthesis.

## 2. User and problem

### Primary user
A master’s student or researcher working in ML and RNA localization, with many PDFs stored on disk.

### Problem
- papers are stored in folders without searchable semantic structure,
- file names do not capture content,
- manual reading is slow and repetitive,
- users cannot quickly answer questions like “Which papers used dataset X?”

### Outcome
The product should make the personal paper library feel searchable, reviewable, and answerable without forcing the user to upload every file manually or accept opaque AI answers.

## 3. Non-goals for MVP

- generic public scientific search engine,
- multi-user platform,
- graph-first knowledge layer as a mandatory system component,
- autonomous paper-writing without human review,
- LLM-generated facts without traceable sources.

## 4. Product principles

- Local-first: the library stays on the user machine.
- No LLM during scanning/indexing.
- 100% source-backed answers: answers must cite documents returned by search.
- Read-only library flow: the user adds files in a folder; the app indexes them.
- Transparent status: the user sees what is indexed, queued, failed, or unavailable.
- Simple architecture before feature complexity.

## 5. Target stack

- Backend: FastAPI
- Frontend: React + TypeScript
- PDF extraction: PyMuPDF + Docling
- Background jobs: Celery + Redis
- Metadata and retrieval: PostgreSQL + pgvector
- Optional graph layer: Neo4j, only for later experiments, not for the MVP core
- Storage: local folder for source PDFs and local processed output directory

## 6. Key architectural constraints

- No LLM during PDF scanning and indexing.
- AI is invoked only on explicit user request.
- Every answer must cite source documents and retrieved excerpts.
- The backend is the only component that can read/write the library state.
- Original PDFs remain in the library folder; they are not duplicated into the database as the primary storage mechanism.
- The frontend may show/copy paths but cannot silently access arbitrary local folders.
- Graph/ontology work is optional and should not block the library workflow.

## 7. Definition of done for MVP

The MVP is successful when a user can:
- configure a local library folder,
- scan it,
- index new/changed PDFs,
- search by content and metadata,
- ask a question and receive a cited answer,
- open the source paper in its local folder,
- trust that the answer is grounded in the actual library.

## 8. 6-stage roadmap with atomic subtasks

### Stage 1 — Local library foundation

- [ ] Define library root and environment configuration
- [ ] Add `LIBRARY_ROOT` to backend configuration and Docker wiring
- [ ] Create local folder read-only mount strategy
- [ ] Implement document model for library sources
- [ ] Add migration for library metadata and path tracking
- [ ] Implement hashing and file-change detection (path + SHA-256)
- [ ] Build scan endpoint to enumerate library PDFs
- [ ] Build “new / changed / unchanged / missing” status logic
- [ ] Add document listing API with source path and status
- [ ] Add tests for scan behavior and hash comparison
- [ ] Validate library folder indexing on a real research folder

Acceptance criteria:
- a user can point the app to a folder of PDFs,
- the app detects added/updated/removed files,
- unchanged files are not reprocessed,
- the API exposes list and status correctly.

### Stage 2 — PDF parsing and extraction

- [ ] Select parsing stack: PyMuPDF for page/layout text extraction
- [ ] Implement ordered extraction for single-column and two-column PDFs
- [ ] Ensure left-column-first then right-column order for multi-column layout
- [ ] Save extracted Markdown or text output to the configured processed directory
- [ ] Detect and store figures/images with Docling
- [ ] Add page/section metadata to extraction output
- [ ] Handle PDFs with heavy figure content without breaking text order
- [ ] Add tests for extraction ordering on sample PDFs
- [ ] Add failure states for unreadable or malformed files

Acceptance criteria:
- text extraction is readable for mixed layout article PDFs,
- multi-column reading order is consistent,
- figure-heavy PDFs do not corrupt extracted content,
- parse failures are surfaced in status UI and logs.

### Stage 3 — Search and retrieval

- [ ] Store extracted text and metadata in PostgreSQL
- [ ] Add full-text search layer for indexed document text
- [ ] Add pagination and ordering for retrieval results
- [ ] Add result ranking by relevance and document metadata
- [ ] Limit retrieval to top N excerpts for answer generation
- [ ] Validate that retrieved excerpts come from the actual indexed library
- [ ] Add endpoint to fetch relevant excerpts for a question
- [ ] Add tests for retrieval relevance and source validation

Acceptance criteria:
- the user can query the library by concept or keyword,
- relevant excerpts are returned without LLM involvement,
- only indexed library content is used as search source.

### Stage 4 — On-demand AI answers with citations

- [ ] Add question endpoint for explicit user requests
- [ ] Search library and retrieve the best excerpts
- [ ] Enforce “LLM only after retrieval” flow
- [ ] Send only retrieved excerpts to the LLM
- [ ] Validate all cited document IDs against the retrieved set
- [ ] Return answer, citations, and evidence snippets to the frontend
- [ ] Add conservative fallback if evidence is weak or absent
- [ ] Add UI block for “Ask AI” and source-backed results
- [ ] Add tests for citation correctness and hallucination guards

Acceptance criteria:
- no model call is made without a question,
- answer is grounded in retrieved excerpts,
- every citation is verifiable,
- the system refuses to fabricate references.

### Stage 5 — Research workflow and thesis support

- [ ] Add library list UI with status, metadata, and source path
- [ ] Add “Open in folder” or “copy path” action for local documents
- [ ] Add filter/search in the library UI
- [ ] Add translated paragraph or article request flow
- [ ] Add “question by article” interaction for a selected paper
- [ ] Add summary mode for multiple relevant papers
- [ ] Add dissertation-writing support: compare methods and dataset usage
- [ ] Add draft-analysis prompts for writing guidance
- [ ] Add warnings when recommendations are speculative

Acceptance criteria:
- the user can work with the library without uploading files,
- the UI supports research review, not just raw metadata,
- suggestions remain framed as hypotheses and guidance, not claims of certainty.

### Stage 6 — Hardening, evaluation, and scaling

- [ ] Run evaluation set of real research questions against the library
- [ ] Measure citation accuracy and false-answer rate
- [ ] Add benchmark for PDF extraction quality on multi-column layouts
- [ ] Add observability for scan jobs, parse failures, and retrieval quality
- [ ] Add logging for API request IDs and worker task outcomes
- [ ] Add policy for document reindexing and stale file status
- [ ] Add optional semantic retrieval layer as a second step
- [ ] Add optional persona-based assistant modes for future use
- [ ] Decide whether Neo4j remains optional or becomes a second-phase feature

Acceptance criteria:
- the project reliably handles a real library of research PDFs,
- the user can trust the answer pipeline,
- future enhancements are layered on proven core functionality.

## 9. Success metrics

### Product metrics
- time to find a relevant paper decreases meaningfully versus manual folder search,
- answer quality is accepted by the user for domain questions,
- citations are trusted and verified,
- users can work with a local library without uploading every paper through the UI.

### Technical metrics
- scan completeness > 95% for valid PDFs in the configured folder,
- extraction success for standard research PDFs,
- no answer returned without a valid cited source set,
- no LLM invocation during indexing workflow.

## 10. Release strategy

### MVP release
Focus on the local library, scan, extraction, retrieval, and source-backed answer flow.

### Phase 2
Add translation, article summaries, and better dissertation-analysis workflows.

### Phase 3
Add persona layers and optional semantic or graph-based enhancements only if the core library workflow proves valuable.

## 11. Final recommendation

The product should not start as a graph-rich scientific platform. It should start as a disciplined local research assistant that solves one real pain well: “I have a folder of papers and need to find and reason from them quickly.”

That is the right MVP because it is useful to a real user, technically feasible within a short development cycle, and much more robust than attempting an ontology-first system before the library workflow is proven.
