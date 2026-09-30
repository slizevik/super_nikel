import { useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  FileText,
  FlaskConical,
  LoaderCircle,
  RotateCcw,
  Upload,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const POLL_INTERVAL_MS = 2000;

type Entity = {
  id: string;
  type: string;
  label: string;
  canonical_label: string;
  aliases: string[];
  evidence: string;
};

type IngestionJob = {
  id: string;
  status: "queued" | "processing" | "awaiting_persistence" | "completed" | "failed";
  current_step: string | null;
  progress_percent: number;
  error_code: string | null;
  error_message: string | null;
  extraction_result: {
    entities: Entity[];
    relationships: unknown[];
    unclassified_entities: { text: string; context: string }[];
  } | null;
  tokens_consumed: number;
  token_budget_limit: number;
};

type UploadResponse = {
  document: { id: string; original_filename: string; file_size_bytes: number };
  job: IngestionJob;
};

type Stage =
  | "upload"
  | "queue"
  | "parsing"
  | "images"
  | "extracting"
  | "validating"
  | "done"
  | "error";

const stageLabels: Record<string, string> = {
  queued: "В очереди",
  queued_for_text_extraction: "Задание принято",
  parsing_pdf: "Чтение PDF в Docling",
  describing_images: "Анализ изображений",
  extracting_entities: "Извлечение сущностей",
  validating_extraction: "Проверка результата",
  awaiting_persistence: "Извлечение завершено",
  pdf_parsing_failed: "Ошибка чтения PDF в Docling",
  image_description_failed: "Ошибка анализа изображений",
  entity_extraction_failed: "Ошибка извлечения сущностей",
  extraction_validation_failed: "Ошибка проверки результата",
  llm_configuration: "Ошибка конфигурации LLM",
  pipeline_failed: "Внутренняя ошибка обработки",
  worker_enqueue_failed: "Ошибка запуска фонового задания",
};

const errorStageLabels: Record<string, string> = {
  PDF_PARSING_FAILED: "Ошибка чтения PDF в Docling",
  IMAGE_DESCRIPTION_FAILED: "Ошибка анализа изображений",
  ENTITY_EXTRACTION_FAILED: "Ошибка извлечения сущностей",
  EXTRACTION_VALIDATION_FAILED: "Ошибка проверки извлечённых данных",
  LLM_CREDENTIALS_MISSING: "Ошибка конфигурации Yandex Cloud AI",
  TOKEN_LIMIT_EXCEEDED: "Превышен лимит токенов",
  WORKER_UNAVAILABLE: "Ошибка запуска фонового задания",
  PIPELINE_INTERNAL_ERROR: "Внутренняя ошибка обработки",
};

const entityTypeLabels: Record<string, string> = {
  Material: "Материал",
  Process: "Процесс",
  Equipment: "Оборудование",
  Property: "Свойство",
  Experiment: "Эксперимент",
  Publication: "Публикация",
  Document: "Документ",
  Expert: "Эксперт",
  Facility: "Предприятие",
  Condition: "Условие",
  Country: "Страна",
  Claim: "Утверждение",
};

const pipelineSteps: { id: Stage; label: string }[] = [
  { id: "upload", label: "Загрузка" },
  { id: "parsing", label: "Чтение PDF" },
  { id: "extracting", label: "Извлечение" },
  { id: "done", label: "Результат" },
];

function getStage(job: IngestionJob): Stage {
  if (job.status === "failed") return "error";
  if (job.status === "awaiting_persistence" || job.status === "completed") {
    return "done";
  }
  if (job.current_step === "parsing_pdf") return "parsing";
  if (job.current_step === "describing_images") return "images";
  if (job.current_step === "extracting_entities") return "extracting";
  if (job.current_step === "validating_extraction") return "validating";
  return "queue";
}

function formatBytes(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} КБ`
    : `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function readableApiError(payload: unknown): string {
  if (typeof payload === "string") return payload;
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String(detail.message);
    }
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
  if (!response.ok) {
    throw new Error(readableApiError(payload));
  }
  return payload as T;
}

function App() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState("Научная статья");
  const [job, setJob] = useState<IngestionJob | null>(null);
  const [documentName, setDocumentName] = useState("");
  const [stage, setStage] = useState<Stage>("upload");
  const [error, setError] = useState<{ title: string; message: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setFile(null);
    setJob(null);
    setDocumentName("");
    setStage("upload");
    setError(null);
    setBusy(false);
    if (fileInput.current) fileInput.current.value = "";
  };

  const handleFileChange = (selected: File | undefined) => {
    setError(null);
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      setFile(null);
      setError({
        title: "Неподдерживаемый формат",
        message: "Выберите документ в формате PDF.",
      });
      return;
    }
    setFile(selected);
  };

  const submitDocument = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file || busy) return;
    if (!category.trim()) {
      setError({
        title: "Не указана категория",
        message: "Заполните категорию документа.",
      });
      return;
    }

    setBusy(true);
    setError(null);
    setStage("queue");
    setJob(null);
    setDocumentName(file.name);
    let uploadAccepted = false;

    try {
      const form = new FormData();
      form.append("file", file);
      form.append("category", category.trim());
      const uploaded = await requestJson<UploadResponse>(
        `${API_URL}/documents`,
        { method: "POST", body: form },
      );
      uploadAccepted = true;
      setJob(uploaded.job);

      let current = uploaded.job;
      while (current.status !== "failed" && current.status !== "completed"
        && current.status !== "awaiting_persistence") {
        setStage(getStage(current));
        await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
        current = await requestJson<IngestionJob>(
          `${API_URL}/jobs/${current.id}/status`,
        );
        setJob(current);
      }

      setStage(getStage(current));
      if (current.status === "failed") {
        setError({
          title:
            errorStageLabels[current.error_code ?? ""] ??
            stageLabels[current.current_step ?? ""] ??
            "Ошибка обработки документа",
          message:
            current.error_message ??
            "Задание завершилось ошибкой без дополнительного описания.",
        });
      }
    } catch (caught) {
      setStage("error");
      setError({
        title: uploadAccepted
          ? "Ошибка проверки статуса задания"
          : "Не удалось загрузить документ",
        message:
          caught instanceof Error
            ? caught.message
            : "Произошла непредвиденная ошибка.",
      });
    } finally {
      setBusy(false);
    }
  };

  const entities = job?.extraction_result?.entities ?? [];
  const currentStepLabel = job?.current_step
    ? stageLabels[job.current_step] ?? job.current_step
    : "Обработка документа";
  const completedSteps =
    stage === "done"
      ? 4
      : stage === "validating"
        ? 3
        : stage === "extracting" || stage === "images"
          ? 2
          : stage === "parsing"
            ? 1
            : 0;

  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Nikelpower, главная">
          <span className="brand-mark"><FlaskConical size={19} strokeWidth={2.2} /></span>
          <span>NIKELPOWER</span>
        </a>
        <span className="topbar-note">Тестирование обработки документов</span>
      </header>

      <section className="intro">
        <div className="eyebrow"><span className="eyebrow-dot" /> MVP · PDF INGESTION</div>
        <h1>Загрузите документ.<br /><span>Получите знания.</span></h1>
        <p>
          Проверьте обработку PDF: от чтения текста до извлечения материалов,
          процессов и других сущностей.
        </p>
      </section>

      <section className="workspace" aria-label="Загрузка документа">
        <div className="upload-panel">
          <div className="section-heading">
            <div>
              <span className="section-kicker">ШАГ 01</span>
              <h2>Новый документ</h2>
            </div>
            <span className="format-badge"><FileText size={14} /> PDF</span>
          </div>

          <form onSubmit={submitDocument}>
            <input
              ref={fileInput}
              className="visually-hidden"
              type="file"
              accept=".pdf,application/pdf"
              onChange={(event) => handleFileChange(event.target.files?.[0])}
            />
            <button
              className={`dropzone ${file ? "dropzone-selected" : ""}`}
              type="button"
              onClick={() => fileInput.current?.click()}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                handleFileChange(event.dataTransfer.files[0]);
              }}
              disabled={busy}
            >
              <span className="upload-icon">
                {file ? <Check size={20} /> : <Upload size={20} />}
              </span>
              {file ? (
                <>
                  <span className="drop-title">{file.name}</span>
                  <span className="drop-hint">{formatBytes(file.size)} · Нажмите, чтобы заменить файл</span>
                </>
              ) : (
                <>
                  <span className="drop-title">Перетащите PDF сюда</span>
                  <span className="drop-hint">или нажмите, чтобы выбрать файл</span>
                </>
              )}
            </button>

            <label className="field-label" htmlFor="category">Категория документа</label>
            <input
              id="category"
              className="text-input"
              type="text"
              maxLength={100}
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              placeholder="Например, научная статья"
              disabled={busy}
            />

            {error && (
              <div className="error-box" role="alert">
                <AlertCircle size={19} />
                <div>
                  <strong>{error.title}</strong>
                  <p>{error.message}</p>
                  {job?.error_code && (
                    <span className="error-code">Код: {job.error_code}</span>
                  )}
                </div>
              </div>
            )}

            <button className="submit-button" type="submit" disabled={!file || busy}>
              {busy ? (
                <><LoaderCircle className="spin" size={18} /> Обрабатываем документ…</>
              ) : (
                <>Загрузить и обработать <ChevronRight size={18} /></>
              )}
            </button>
            <div className="privacy-note">
              <CircleHelp size={14} />
              Принимаются только PDF-файлы. Оригинал сохраняется в системе.
            </div>
          </form>
        </div>

        <div className="result-panel" aria-live="polite">
          {!job && !busy && !error && (
            <div className="empty-state">
              <div className="empty-art">
                <div className="art-card art-card-back"><span /><span /><span /></div>
                <div className="art-card art-card-front">
                  <span className="art-file"><FileText size={23} /></span>
                  <span /><span /><span />
                  <i className="art-spark spark-one" /><i className="art-spark spark-two" />
                </div>
              </div>
              <h2>Здесь появится результат</h2>
              <p>Загрузите PDF, чтобы увидеть ход обработки и найденные сущности.</p>
            </div>
          )}

          {(busy || job) && (
            <div className="processing-content">
              <div className="section-heading result-heading">
                <div>
                  <span className="section-kicker">ШАГ 02</span>
                  <h2>{stage === "done" ? "Результат обработки" : "Обработка документа"}</h2>
                </div>
                {stage === "done" && (
                  <span className="success-badge"><CheckCircle2 size={15} /> Готово</span>
                )}
              </div>

              <div className="file-summary">
                <span className="file-icon"><FileText size={18} /></span>
                <span className="file-summary-name">{documentName || "PDF-документ"}</span>
                {job && <span className="file-summary-status">{job.status === "failed" ? "Ошибка" : stage === "done" ? "Успешно" : "В работе"}</span>}
              </div>

              <div className="steps" aria-label="Этапы обработки">
                {pipelineSteps.map((step, index) => {
                  const isComplete = index < completedSteps;
                  const isCurrent = index === completedSteps && stage !== "done" && stage !== "error";
                  const isFailed = stage === "error" && (
                    (index === 1 && job?.current_step === "pdf_parsing_failed") ||
                    (index === 2 && job?.current_step !== "pdf_parsing_failed")
                  );
                  return (
                    <div className={`step ${isComplete ? "step-complete" : ""} ${isCurrent ? "step-current" : ""} ${isFailed ? "step-failed" : ""}`} key={step.id}>
                      <span className="step-indicator">
                        {isComplete ? <Check size={13} /> : isCurrent ? <LoaderCircle className="spin" size={14} /> : isFailed ? <AlertCircle size={14} /> : <span>{index + 1}</span>}
                      </span>
                      <span className="step-label">{step.label}</span>
                      {index < pipelineSteps.length - 1 && <span className="step-connector" />}
                    </div>
                  );
                })}
              </div>

              {job && stage !== "done" && stage !== "error" && (
                <div className="progress-area">
                  <div className="progress-caption">
                    <span>{currentStepLabel}</span>
                    <span>{job.progress_percent}%</span>
                  </div>
                  <div className="progress-track">
                    <span style={{ width: `${job.progress_percent}%` }} />
                  </div>
                </div>
              )}

              {stage === "done" && (
                <div className="result-notice">
                  <CheckCircle2 size={18} />
                  <div>
                    <strong>Текст обработан, сущности извлечены</strong>
                    <span>Результат готов. Сохранение сущностей в граф пока не входит в этот этап.</span>
                  </div>
                </div>
              )}

              {job && stage === "done" && (
                <>
                  <div className="entities-heading">
                    <div>
                      <h3>Извлечённые сущности</h3>
                      <span>{entities.length} {entities.length === 1 ? "сущность" : "сущностей"}</span>
                    </div>
                    <span className="entity-count">{entities.length}</span>
                  </div>
                  {entities.length > 0 ? (
                    <ul className="entity-list">
                      {entities.map((entity) => (
                        <li className="entity-card" key={entity.id}>
                          <div className="entity-topline">
                            <span className={`entity-type entity-type-${entity.type.toLowerCase()}`}>
                              {entityTypeLabels[entity.type] ?? entity.type}
                            </span>
                          </div>
                          <strong className="entity-name">{entity.canonical_label}</strong>
                          {entity.label !== entity.canonical_label && (
                            <span className="entity-source-label">В тексте: {entity.label}</span>
                          )}
                          {entity.aliases.length > 0 && (
                            <span className="entity-aliases">Также: {entity.aliases.join(", ")}</span>
                          )}
                          <blockquote>{entity.evidence}</blockquote>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="no-entities">
                      <FileText size={19} />
                      <span>Сущности не найдены. Документ обработан, но модель не вернула подходящих сущностей.</span>
                    </div>
                  )}
                  {job.extraction_result?.unclassified_entities?.length ? (
                    <div className="unclassified-note">
                      Ещё не классифицировано: {job.extraction_result.unclassified_entities.map((entity) => entity.text).join(", ")}
                    </div>
                  ) : null}
                  <div className="usage-note">
                    Использовано токенов: {job.tokens_consumed.toLocaleString("ru-RU")} из {job.token_budget_limit.toLocaleString("ru-RU")}
                  </div>
                </>
              )}

              {stage === "error" && (
                <div className="failure-summary">
                  <AlertCircle size={18} />
                  <span>{error?.title ?? "Обработка остановлена с ошибкой"}</span>
                </div>
              )}
            </div>
          )}
          {(stage === "done" || stage === "error") && (
            <button className="reset-button" type="button" onClick={reset}>
              <RotateCcw size={15} /> Загрузить другой документ
            </button>
          )}
        </div>
      </section>

      <footer className="footer">
        <span>© Nikelpower · Инструмент проверки pipeline</span>
        <span><span className="footer-status-dot" /> PDF → Docling → LLM</span>
      </footer>
    </main>
  );
}

export default App;
