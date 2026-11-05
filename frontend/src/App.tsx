import { useEffect, useRef, useState } from "react";
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
  Trash2,
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
  chunk_id: string;
  original_filename: string;
  library_relative_path: string;
  source_path: string;
  excerpt: string;
  page_start: number | null;
  page_end: number | null;
  heading: string | null;
  retrieval_score: number;
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

type ChatSessionSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

type ChatSessionDetail = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Array<{
    id: string;
    question: string;
    answer: string;
    citations: AnswerCitation[];
    translated_question: string | null;
    created_at: string;
  }>;
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
  const [chatsLoading, setChatsLoading] = useState(true);
  const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
  const [activeChatId, setActiveChatId] = useState("");
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [collapsedSources, setCollapsedSources] = useState<Set<string>>(
    () => new Set(),
  );
  const [answerError, setAnswerError] = useState("");
  const [copiedDocumentId, setCopiedDocumentId] = useState("");
  const chatInitializationStarted = useRef(false);

  const refreshLibrary = async () => {
    const documents = await requestJson<LibraryDocument[]>(
      `${API_URL}/documents?limit=${LIBRARY_PAGE_SIZE}&offset=0`,
    );
    setLibrary(documents);
    setLibraryHasMore(documents.length === LIBRARY_PAGE_SIZE);
  };

  const refreshChats = async () => {
    const sessions = await requestJson<ChatSessionSummary[]>(`${API_URL}/chats`);
    setChatSessions(sessions);
    return sessions;
  };

  const openChat = async (chatId: string) => {
    setChatsLoading(true);
    setAnswerError("");
    try {
      const chat = await requestJson<ChatSessionDetail>(`${API_URL}/chats/${chatId}`);
      setActiveChatId(chat.id);
      setChatTurns(
        chat.messages.map((message) => ({
          id: message.id,
          question: message.question,
          response: {
            answer: message.answer,
            citations: message.citations,
            translated_question: message.translated_question,
          },
        })),
      );
      setCollapsedSources(new Set());
    } catch (caught) {
      setAnswerError(
        caught instanceof Error ? caught.message : "Не удалось открыть чат.",
      );
    } finally {
      setChatsLoading(false);
    }
  };

  const createChat = async () => {
    setAnswerError("");
    setChatsLoading(true);
    try {
      const chat = await requestJson<ChatSessionSummary>(`${API_URL}/chats`, {
        method: "POST",
      });
      setChatSessions((current) => [chat, ...current]);
      setActiveChatId(chat.id);
      setChatTurns([]);
      setCollapsedSources(new Set());
      setQuestion("");
    } catch (caught) {
      setAnswerError(
        caught instanceof Error ? caught.message : "Не удалось создать чат.",
      );
    } finally {
      setChatsLoading(false);
    }
  };

  const deleteChat = async (chatId: string) => {
    setAnswerError("");
    setChatsLoading(true);
    try {
      await requestJson<void>(`${API_URL}/chats/${chatId}`, { method: "DELETE" });
      const sessions = await refreshChats();
      if (sessions.length > 0) {
        await openChat(sessions[0].id);
      } else {
        await createChat();
      }
    } catch (caught) {
      setAnswerError(
        caught instanceof Error ? caught.message : "Не удалось удалить чат.",
      );
      setChatsLoading(false);
    }
  };

  useEffect(() => {
    refreshLibrary().catch((caught: unknown) => {
      setLibraryError(
        caught instanceof Error ? caught.message : "Не удалось загрузить библиотеку.",
      );
    });
  }, []);

  useEffect(() => {
    if (chatInitializationStarted.current) return;
    chatInitializationStarted.current = true;

    const initializeChats = async () => {
      try {
        const sessions = await refreshChats();
        if (sessions.length > 0) {
          await openChat(sessions[0].id);
        } else {
          await createChat();
        }
      } catch (caught) {
        setAnswerError(
          caught instanceof Error ? caught.message : "Не удалось загрузить чаты.",
        );
        setChatsLoading(false);
      }
    };
    void initializeChats();
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
    if (asking || chatsLoading || question.trim().length < 3 || !activeChatId) return;

    setAsking(true);
    setAnswerError("");
    const submittedQuestion = question.trim();
    try {
      const response = await requestJson<ChatSessionDetail["messages"][number]>(
        `${API_URL}/chats/${activeChatId}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: submittedQuestion }),
        },
      );
      setChatTurns((current) => [
        ...current,
        {
          id: response.id,
          question: response.question,
          response: {
            answer: response.answer,
            citations: response.citations,
            translated_question: response.translated_question,
          },
        },
      ]);
      setQuestion("");
      try {
        await refreshChats();
      } catch (caught) {
        setAnswerError(
          `Ответ сохранён, но список чатов не обновился: ${
            caught instanceof Error ? caught.message : "неизвестная ошибка"
          }`,
        );
      }
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
          <button
            className="library-scan-button"
            type="button"
            onClick={() => void createChat()}
            disabled={asking || chatsLoading}
          >
            Новый чат
          </button>
        </div>
        <p className="ask-description">
          Вопрос ищется по индексированным статьям. Русский запрос переводится
          для поиска по англоязычному тексту, а ответ формируется на русском и
          сопровождается источниками.
        </p>
        <div className="chat-sessions" aria-label="Сохранённые чаты">
          {chatSessions.map((chat) => (
            <div className="chat-session-item" key={chat.id}>
              <button
                className={`chat-session-button ${activeChatId === chat.id ? "chat-session-active" : ""}`}
                type="button"
                onClick={() => void openChat(chat.id)}
                disabled={asking || chatsLoading}
                aria-current={activeChatId === chat.id ? "page" : undefined}
                title={chat.title}
              >
                <span>{chat.title}</span>
                <small>{chat.message_count} сообщ.</small>
              </button>
              <button
                className="chat-delete-button"
                type="button"
                onClick={() => void deleteChat(chat.id)}
                disabled={asking || chatsLoading}
                aria-label={`Удалить чат: ${chat.title}`}
                title="Удалить чат"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {chatsLoading && <span className="chat-loading-label">Загружаю чаты…</span>}
        </div>
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
            disabled={asking || chatsLoading || !activeChatId}
          />
          <button
            className="ask-button"
            type="submit"
            disabled={asking || chatsLoading || !activeChatId || question.trim().length < 3}
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
          {[...chatTurns].reverse().map(({ id, question: askedQuestion, response }) => (
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
                                {(citation.page_start || citation.page_end || citation.heading) && (
                                  <small>
                                    {citation.heading && `${citation.heading} · `}
                                    {citation.page_start === citation.page_end
                                      ? `стр. ${citation.page_start}`
                                      : `стр. ${citation.page_start}–${citation.page_end}`}
                                  </small>
                                )}
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
