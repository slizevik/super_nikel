import { useEffect, useState } from "react";
import {
  Check,
  Copy,
  ChevronDown,
  ChevronRight,
  FileText,
  FlaskConical,
  LoaderCircle,
  RotateCcw,
  Send,
  Sparkles,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const LIBRARY_PAGE_SIZE = 50;

type LibraryDocument = {
  id: string;
  original_filename: string;
  library_relative_path: string;
  source_path: string | null;
  file_size_bytes: number;
  source_available: boolean;
  job_status: string | null;
  current_step: string | null;
  error_message: string | null;
};

type LibraryScanSummary = {
  discovered: number;
  queued: number;
  changed: number;
  unchanged: number;
  skipped_busy: number;
  errors: string[];
};

type AnswerCitation = {
  document_id: string;
  original_filename: string;
  library_relative_path: string;
  source_path: string;
  excerpt: string;
};

type AnswerResponse = {
  answer: string;
  citations: AnswerCitation[];
  translated_question: string | null;
};

type ChatTurn = {
  id: string;
  question: string;
  response: AnswerResponse;
};

function readableApiError(payload: unknown): string {
  if (typeof payload === "string") return payload;
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg ?? "Некорректные данные").join("; ");
    }
  }
  return "Сервер вернул неожиданный ответ.";
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error(
      "Не удалось связаться с backend. Проверьте, что API запущен и доступен.",
    );
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(readableApiError(payload));
  return payload as T;
}

function statusLabel(document: LibraryDocument): string {
  if (!document.source_available) return "Файл отсутствует";
  if (document.job_status === "completed") return "Текст индексирован";
  if (document.job_status === "failed") return "Ошибка обработки";
  if (document.job_status === "queued" || document.job_status === "processing") {
    return "Индексируется";
  }
  return "Ожидает индексации";
}

function App() {
  const [library, setLibrary] = useState<LibraryDocument[]>([]);
  const [libraryBusy, setLibraryBusy] = useState(false);
  const [libraryLoadingMore, setLibraryLoadingMore] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const [libraryHasMore, setLibraryHasMore] = useState(false);
  const [scanSummary, setScanSummary] = useState<LibraryScanSummary | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [collapsedSources, setCollapsedSources] = useState<Set<string>>(
    () => new Set(),
  );
  const [answerError, setAnswerError] = useState("");
  const [copiedDocumentId, setCopiedDocumentId] = useState("");

  const refreshLibrary = async () => {
    const documents = await requestJson<LibraryDocument[]>(
      `${API_URL}/documents?limit=${LIBRARY_PAGE_SIZE}&offset=0`,
    );
    setLibrary(documents);
    setLibraryHasMore(documents.length === LIBRARY_PAGE_SIZE);
  };

  useEffect(() => {
    refreshLibrary().catch((caught: unknown) => {
      setLibraryError(
        caught instanceof Error ? caught.message : "Не удалось загрузить библиотеку.",
      );
    });
  }, []);

  const scanLibrary = async () => {
    setLibraryBusy(true);
    setLibraryError("");
    setScanSummary(null);
    try {
      const summary = await requestJson<LibraryScanSummary>(
        `${API_URL}/library/scan`,
        { method: "POST" },
      );
      setScanSummary(summary);
      await refreshLibrary();
    } catch (caught) {
      setLibraryError(
        caught instanceof Error ? caught.message : "Не удалось просканировать библиотеку.",
      );
    } finally {
      setLibraryBusy(false);
    }
  };

  const loadMoreLibrary = async () => {
    setLibraryLoadingMore(true);
    setLibraryError("");
    try {
      const documents = await requestJson<LibraryDocument[]>(
        `${API_URL}/documents?limit=${LIBRARY_PAGE_SIZE}&offset=${library.length}`,
      );
      setLibrary((current) => [...current, ...documents]);
      setLibraryHasMore(documents.length === LIBRARY_PAGE_SIZE);
    } catch (caught) {
      setLibraryError(
        caught instanceof Error ? caught.message : "Не удалось загрузить документы.",
      );
    } finally {
      setLibraryLoadingMore(false);
    }
  };

  const askQuestion = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (asking || question.trim().length < 3) return;

    setAsking(true);
    setAnswerError("");
    const submittedQuestion = question.trim();
    try {
      const response = await requestJson<AnswerResponse>(`${API_URL}/answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: submittedQuestion }),
      });
      setChatTurns((current) => [
        ...current,
        {
          id: `${Date.now()}-${current.length}`,
          question: submittedQuestion,
          response,
        },
      ]);
      setQuestion("");
    } catch (caught) {
      setAnswerError(
        caught instanceof Error ? caught.message : "Не удалось получить ответ.",
      );
    } finally {
      setAsking(false);
    }
  };

  const copySourcePath = async (document: LibraryDocument | AnswerCitation) => {
    if (!document.source_path) {
      setLibraryError("Путь к статье не настроен в конфигурации backend.");
      return;
    }
    try {
      await navigator.clipboard.writeText(document.source_path);
      setCopiedDocumentId(
        "document_id" in document ? document.document_id : document.id,
      );
      window.setTimeout(() => setCopiedDocumentId(""), 1800);
    } catch {
      setLibraryError(
        "Браузер не разрешил копирование. Скопируйте путь вручную: " +
          document.source_path,
      );
    }
  };

  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Nikelpower, главная">
          <span className="brand-mark"><FlaskConical size={19} strokeWidth={2.2} /></span>
          <span>NIKELPOWER</span>
        </a>
        <span className="topbar-note">Личная исследовательская библиотека</span>
      </header>

      <section className="intro">
        <div className="eyebrow"><span className="eyebrow-dot" /> PERSONAL RESEARCH LIBRARY</div>
        <h1>Найдите нужное<br /><span>в своих статьях.</span></h1>
        <p>
          Добавляйте PDF в папку библиотеки, индексируйте их без LLM и задавайте
          вопросы по содержимому, когда понадобится.
        </p>
      </section>

      <section className="ask-panel" aria-label="Спросить ИИ">
        <div className="section-heading">
          <div>
            <span className="section-kicker">ОТВЕТЫ ПО ВАШЕЙ БИБЛИОТЕКЕ</span>
            <h2><Sparkles size={18} /> Чат по статьям</h2>
          </div>
          {chatTurns.length > 0 && (
            <button
              className="library-scan-button"
              type="button"
              onClick={() => {
                setChatTurns([]);
                setCollapsedSources(new Set());
              }}
              disabled={asking}
            >
              Новый диалог
            </button>
          )}
        </div>
        <p className="ask-description">
          Вопрос ищется по индексированным статьям. Русский запрос переводится
          для поиска по англоязычному тексту, а ответ формируется на русском и
          сопровождается источниками.
        </p>
        <form className="ask-form" onSubmit={askQuestion}>
          <label className="visually-hidden" htmlFor="library-question">
            Вопрос по статьям
          </label>
          <textarea
            id="library-question"
            className="question-input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={2000}
            placeholder="Например: какие методы локализации мРНК описаны в статьях?"
            rows={3}
            disabled={asking}
          />
          <button
            className="ask-button"
            type="submit"
            disabled={asking || question.trim().length < 3}
          >
            {asking
              ? <><LoaderCircle className="spin" size={16} /> ИИ анализирует найденные фрагменты…</>
              : <>Отправить <Send size={15} /></>}
          </button>
        </form>
        {answerError && <p className="library-error" role="alert">{answerError}</p>}
        <div className="chat-history" aria-live="polite">
          {chatTurns.length === 0 && (
            <p className="chat-empty">
              Например: «Какие датасеты использовались для обучения моделей?»
            </p>
          )}
          {chatTurns.map(({ id, question: askedQuestion, response }) => (
            <article className="chat-turn" key={id}>
              <div className="chat-question">
                <span>Вы</span>
                <p>{askedQuestion}</p>
              </div>
              {response.translated_question && (
                <p className="translated-question">
                  Поисковый запрос: {response.translated_question}
                </p>
              )}
              <div className="chat-answer">
                <span>Ответ по библиотеке</span>
                <p className="answer-text">{response.answer}</p>
                {response.citations.length > 0 && (
                  <div className="answer-citations">
                    <button
                      className="sources-toggle"
                      type="button"
                      aria-expanded={!collapsedSources.has(id)}
                      aria-controls={`sources-${id}`}
                      onClick={() =>
                        setCollapsedSources((current) => {
                          const next = new Set(current);
                          if (next.has(id)) next.delete(id);
                          else next.add(id);
                          return next;
                        })
                      }
                    >
                      {collapsedSources.has(id)
                        ? <ChevronRight size={15} />
                        : <ChevronDown size={15} />}
                      Источники ({response.citations.length})
                      <span>{collapsedSources.has(id) ? "Показать" : "Свернуть"}</span>
                    </button>
                    {!collapsedSources.has(id) && (
                      <div className="citation-list" id={`sources-${id}`}>
                        {response.citations.map((citation) => (
                          <article className="citation-card" key={citation.document_id}>
                            <div className="citation-heading">
                              <div>
                                <strong>{citation.original_filename}</strong>
                                <span>{citation.library_relative_path}</span>
                              </div>
                              <button
                                className="path-copy-button"
                                type="button"
                                onClick={() => void copySourcePath(citation)}
                              >
                                {copiedDocumentId === citation.document_id
                                  ? <Check size={14} />
                                  : <Copy size={14} />}
                                {copiedDocumentId === citation.document_id
                                  ? "Скопировано"
                                  : "Копировать путь"}
                              </button>
                            </div>
                            <blockquote>{citation.excerpt}</blockquote>
                          </article>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </article>
          ))}
          {asking && (
            <p className="chat-pending" role="status">
              <LoaderCircle className="spin" size={15} />
              Ищу подтверждения в статьях и готовлю ответ…
            </p>
          )}
        </div>
      </section>

      <section className="library-panel" aria-label="Личная библиотека статей">
        <div className="section-heading">
          <div>
            <span className="section-kicker">КОЛЛЕКЦИЯ</span>
            <h2>Статьи из папки</h2>
          </div>
          <button
            className="library-scan-button"
            type="button"
            onClick={scanLibrary}
            disabled={libraryBusy}
          >
            {libraryBusy
              ? <LoaderCircle className="spin" size={15} />
              : <RotateCcw size={15} />}
            {libraryBusy ? "Сканируем…" : "Сканировать папку"}
          </button>
        </div>
        <p className="library-description">
          Поместите статью в настроенную папку и запустите сканирование. Текст
          индексируется без обращения к модели.
        </p>
        {libraryError && <p className="library-error" role="alert">{libraryError}</p>}
        {scanSummary && (
          <p className="library-summary" role="status">
            Найдено: {scanSummary.discovered} · в очереди: {scanSummary.queued} ·
            изменено: {scanSummary.changed} · без изменений: {scanSummary.unchanged}
            {scanSummary.skipped_busy > 0 && ` · занято: ${scanSummary.skipped_busy}`}
            {scanSummary.errors.length > 0 && ` · ошибок: ${scanSummary.errors.length}`}
          </p>
        )}
        {library.length === 0 ? (
          <p className="library-empty">
            Документов пока нет. Добавьте PDF в папку и нажмите «Сканировать папку».
          </p>
        ) : (
          <ul className="library-list">
            {library.map((document) => (
              <li className="library-item" key={document.id}>
                <FileText className="library-file-icon" size={17} />
                <div className="library-item-info">
                  <strong>{document.original_filename}</strong>
                  <span>{document.library_relative_path}</span>
                </div>
                <span
                  className={`library-status ${document.job_status === "failed" ? "library-status-error" : ""}`}
                >
                  {statusLabel(document)}
                </span>
                {document.source_available && document.source_path && (
                  <button
                    className="path-copy-button"
                    type="button"
                    onClick={() => void copySourcePath(document)}
                    title={document.source_path}
                  >
                    {copiedDocumentId === document.id
                      ? <Check size={14} />
                      : <Copy size={14} />}
                    {copiedDocumentId === document.id
                      ? "Скопировано"
                      : "Копировать путь"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {libraryHasMore && (
          <button
            className="library-scan-button load-more-button"
            type="button"
            onClick={loadMoreLibrary}
            disabled={libraryLoadingMore}
          >
            {libraryLoadingMore ? "Загружаем…" : "Показать ещё статьи"}
          </button>
        )}
      </section>

      <footer className="footer">
        <span>Личная исследовательская библиотека · on-demand AI</span>
        <span><i className="footer-status-dot" /> Индексация без LLM</span>
      </footer>
    </main>
  );
}

export default App;
