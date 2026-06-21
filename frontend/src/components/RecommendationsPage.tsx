/** Экран рекомендаций (S4.5): кнопка генерации + история списком + деталь по id.
 *  Кнопка зовёт POST /recommendations/generate (снапшот → Opus → план); готовая запись
 *  попадает в историю слева и раскрывается планом справа. Деталь читается по id с бэкенда. */

import { useEffect, useState } from 'react';
import {
  ApiError,
  type DayNutrition,
  type GoalSnapshot,
  type MealPlan,
  type Recommendation,
  type WorkoutPlan,
} from '../lib/api';
import {
  useGenerateRecommendation,
  useRecommendation,
  useRecommendations,
} from '../lib/recommendations';

// ponytail: created_at — наивный UTC без 'Z'; для личного трекера сдвиг зоны при показе
// несущественен. Захотим точности — добавим 'Z' на бэке.
const dateTimeFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
});

// Дедлайн цели — дата без времени; отдельный формат без часов/минут.
const dateFmt = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

function formatCreated(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : dateTimeFmt.format(d);
}

// ponytail: 'YYYY-MM-DD' парсится как UTC-полночь; для зоны пользователя (MSK, +3) день
// не съезжает. Понадобятся отрицательные зоны — парсить по частям.
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : dateFmt.format(d);
}

function macrosLine(m: { protein_g: number; carbs_g: number; fat_g: number }): string {
  return `Б ${m.protein_g} · У ${m.carbs_g} · Ж ${m.fat_g} г`;
}

// Время генерации (S4.9): до секунды — в миллисекундах, дальше — в секундах с одним знаком.
function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms} мс` : `${(ms / 1000).toFixed(1)} с`;
}

// «Модель: X» и, если замер есть, « · сгенерировано за Yс». У записей до S4.9 времени нет.
function modelLine(model: string, generationMs: number | null): string {
  return generationMs == null
    ? `Модель: ${model}`
    : `Модель: ${model} · сгенерировано за ${formatDuration(generationMs)}`;
}

// Человеческие подписи целевых обхватов. Ключи цели — «голые» (waist, chest…), как в
// target_measurements_json; неизвестный ключ показываем как есть.
const MEASUREMENT_LABELS_RU: Record<string, string> = {
  waist: 'Талия',
  belly: 'Живот',
  chest: 'Грудь',
  hips: 'Бёдра',
  shoulders: 'Плечи',
  biceps_l: 'Бицепс (л)',
  biceps_r: 'Бицепс (п)',
  glutes: 'Ягодицы',
  calf_l: 'Икра (л)',
  calf_r: 'Икра (п)',
};

/** Числовые цели в виде читаемых строк: вес, % жира, целевые обхваты. Пусто — целей нет. */
function goalTargets(goal: GoalSnapshot): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  if (goal.target_weight_kg != null) {
    out.push({ label: 'Целевой вес', value: `${goal.target_weight_kg} кг` });
  }
  if (goal.target_body_fat_pct != null) {
    out.push({ label: 'Целевой % жира', value: `${goal.target_body_fat_pct}%` });
  }
  for (const [key, val] of Object.entries(goal.target_measurements ?? {})) {
    out.push({ label: MEASUREMENT_LABELS_RU[key] ?? key, value: `${val} см` });
  }
  return out;
}

export default function RecommendationsPage() {
  const { data: history, isPending: historyPending } = useRecommendations();
  const generate = useGenerateRecommendation();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: detail, isPending: detailPending } = useRecommendation(selectedId);

  // По умолчанию открыта самая свежая запись истории, пока пользователь не выбрал другую.
  useEffect(() => {
    if (selectedId == null && history && history.length > 0) {
      setSelectedId(history[0].id);
    }
  }, [history, selectedId]);

  function onGenerate() {
    // Защита от двойного вызова (S4.9): кнопка дизейблится на isPending, но гасим и сам
    // обработчик — на случай повторного клика до перерисовки запрос не дублируется.
    if (generate.isPending) return;
    generate.mutate(undefined, { onSuccess: (rec) => setSelectedId(rec.id) });
  }

  const generateError =
    generate.error instanceof ApiError
      ? generate.error.status === 502
        ? 'Модель недоступна (502). Проверьте ключ LLM и повторите.'
        : `Не удалось сгенерировать (${generate.error.status}).`
      : generate.error
        ? 'Не удалось сгенерировать. Проверьте, что сервер запущен.'
        : null;

  return (
    <section aria-labelledby="reco-heading" className="flex flex-col gap-[var(--space-section)]">
      <div className="max-w-2xl">
        <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
          Рекомендации
        </p>
        <h1 id="reco-heading" className="mt-3 text-display">
          План от модели
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Сгенерируйте план питания и тренировок по вашим данным. Каждая генерация сохраняется в
          историю — её можно открыть и сравнить с прошлыми.
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={onGenerate}
            disabled={generate.isPending}
            className="rounded-xl bg-accent px-5 py-3 font-display font-semibold text-accent-ink transition-all duration-[var(--duration-normal)] ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-[0_10px_30px_-10px] hover:shadow-accent/60 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {generate.isPending ? 'Генерирую…' : 'Сгенерировать рекомендацию'}
          </button>
          {generate.isPending && (
            <span className="text-sm text-muted">Модель составляет план, это занимает время…</span>
          )}
        </div>

        {generateError && (
          <p role="alert" className="mt-3 text-sm font-medium text-amber">
            {generateError}
          </p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
        <HistoryList
          history={history}
          isPending={historyPending}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        <DetailPanel
          hasHistory={Boolean(history && history.length > 0)}
          detail={selectedId == null ? null : (detail ?? null)}
          isPending={selectedId != null && detailPending}
        />
      </div>
    </section>
  );
}

function HistoryList({
  history,
  isPending,
  selectedId,
  onSelect,
}: {
  history: Recommendation[] | undefined;
  isPending: boolean;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="flex flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-surface p-6">
      <h2 className="text-display">История</h2>
      {isPending ? (
        <p className="text-muted">Загрузка…</p>
      ) : !history || history.length === 0 ? (
        <p className="text-muted">
          История пуста. Нажмите «Сгенерировать рекомендацию» — первая появится здесь.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {history.map((rec) => {
            const active = rec.id === selectedId;
            return (
              <li key={rec.id}>
                <button
                  type="button"
                  onClick={() => onSelect(rec.id)}
                  aria-current={active}
                  className={`flex w-full flex-col items-start gap-0.5 rounded-xl border px-4 py-3 text-left transition-colors duration-[var(--duration-fast)] ${
                    active
                      ? 'border-accent/60 bg-panel'
                      : 'border-line hover:border-accent/40 hover:bg-panel'
                  }`}
                >
                  <span className="font-display font-semibold tracking-tight">
                    {formatCreated(rec.created_at)}
                  </span>
                  <span className="text-sm text-muted">{rec.model}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function DetailPanel({
  hasHistory,
  detail,
  isPending,
}: {
  hasHistory: boolean;
  detail: Recommendation | null;
  isPending: boolean;
}) {
  return (
    <div className="flex flex-col gap-6 rounded-[var(--radius-card)] border border-line bg-gradient-to-br from-panel to-surface p-6">
      {isPending ? (
        <p className="text-muted">Загрузка плана…</p>
      ) : !detail ? (
        <p className="text-muted">
          {hasHistory
            ? 'Выберите рекомендацию из истории слева, чтобы посмотреть план.'
            : 'Здесь появится план, когда вы сгенерируете первую рекомендацию.'}
        </p>
      ) : detail.output_json ? (
        <RecommendationPlanView
          plan={detail.output_json}
          created={detail.created_at}
          model={detail.model}
          generationMs={detail.generation_ms}
          goal={detail.input_snapshot_json?.goal ?? null}
        />
      ) : (
        // Запись без распарсенного плана — показываем сырой ответ, чтобы не «терять» её.
        <div>
          <h2 className="text-display">План недоступен</h2>
          <p className="mt-1 text-sm text-muted">
            {formatCreated(detail.created_at)} · {modelLine(detail.model, detail.generation_ms)}
          </p>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-sm text-muted">
            {detail.raw_text ?? '—'}
          </pre>
        </div>
      )}
    </div>
  );
}

function RecommendationPlanView({
  plan,
  created,
  model,
  generationMs,
  goal,
}: {
  plan: NonNullable<Recommendation['output_json']>;
  created: string;
  model: string;
  generationMs: number | null;
  goal: GoalSnapshot | null;
}) {
  return (
    <>
      <div>
        <h2 className="text-display">План от {formatCreated(created)}</h2>
        <p className="mt-1 text-sm text-muted">{modelLine(model, generationMs)}</p>
      </div>

      {goal && <GoalCard goal={goal} />}

      <section aria-label="План питания" className="flex flex-col gap-4">
        <h3 className="font-display text-lg font-semibold tracking-tight">Питание</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <DayCard title="Тренировочный день" day={plan.meal_plan.training_day} />
          <DayCard title="День отдыха" day={plan.meal_plan.rest_day} />
        </div>
        {plan.meal_plan.notes && (
          <p className="text-sm leading-relaxed text-muted">{plan.meal_plan.notes}</p>
        )}
      </section>

      <RationaleCard note={plan.sync_note} />

      <WorkoutPlanView plan={plan.workout_plan} mealPlan={plan.meal_plan} />
    </>
  );
}

// Цель, под которую сгенерирован план: целевые метрики, дедлайн и мотивация («зачем»).
function GoalCard({ goal }: { goal: GoalSnapshot }) {
  const targets = goalTargets(goal);
  return (
    <section
      aria-label="Цель"
      className="flex flex-col gap-3 rounded-xl border border-accent/30 bg-panel p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-display text-lg font-semibold tracking-tight">Цель</h3>
        {goal.deadline && (
          <span className="text-sm text-muted">до {formatDate(goal.deadline)}</span>
        )}
      </div>
      {targets.length > 0 ? (
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {targets.map((t) => (
            <div key={t.label} className="flex items-baseline justify-between gap-3">
              <dt className="text-sm text-muted">{t.label}</dt>
              <dd className="font-display font-semibold tracking-tight">{t.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-muted">Числовые цели не заданы.</p>
      )}
      {goal.why_notes && (
        <blockquote className="border-l-2 border-accent/50 pl-4 text-muted italic">
          {goal.why_notes}
        </blockquote>
      )}
    </section>
  );
}

// Обоснование: как рацион увязан с тренировками (sync_note из плана модели).
function RationaleCard({ note }: { note: string }) {
  return (
    <section aria-label="Обоснование" className="rounded-xl border border-line bg-surface p-5">
      <h3 className="font-display text-lg font-semibold tracking-tight">Обоснование</h3>
      <p className="mt-2 leading-relaxed text-muted">{note}</p>
    </section>
  );
}

function DayCard({ title, day }: { title: string; day: DayNutrition }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-display font-semibold tracking-tight">{title}</span>
        <span className="font-display text-xl font-semibold tracking-tight">
          {day.calories}
          <span className="ml-1 text-sm font-normal text-muted">ккал</span>
        </span>
      </div>
      <p className="text-sm text-muted">{macrosLine(day.macros)}</p>
      <ul className="flex flex-col gap-1.5 border-t border-line pt-3">
        {day.meals.map((meal, i) => (
          <li key={i} className="flex items-baseline justify-between gap-3 text-sm">
            <span>{meal.name}</span>
            <span className="text-muted">{meal.calories} ккал</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function WorkoutPlanView({ plan, mealPlan }: { plan: WorkoutPlan; mealPlan: MealPlan }) {
  // Связка еда↔тренировка: каждая тренировка из расписания — это «тренировочный день»,
  // т.е. ей соответствует более калорийный рацион (mealPlan.training_day); дни без
  // тренировки идут по рациону отдыха (mealPlan.rest_day).
  const trainingCal = mealPlan.training_day.calories;
  const restCal = mealPlan.rest_day.calories;
  return (
    <section aria-label="План тренировок" className="flex flex-col gap-4">
      <h3 className="font-display text-lg font-semibold tracking-tight">
        Тренировки · {plan.days_per_week} в неделю
      </h3>

      <FoodLinkLegend trainingCal={trainingCal} restCal={restCal} />

      <div className="flex flex-col gap-3">
        {plan.schedule.map((wday) => (
          <div key={wday.day} className="rounded-xl border border-line bg-surface p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1.5">
              <p className="font-display font-semibold tracking-tight">
                День {wday.day}. {wday.focus}
              </p>
              {/* Пометка связки с едой: тренировочный день → рацион тренировочного дня. */}
              <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-accent">
                🍽 Рацион тренировочного дня · {trainingCal} ккал
              </span>
            </div>
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {wday.exercises.map((ex, i) => (
                <li key={i} className="flex items-baseline justify-between gap-3">
                  <span>{ex.name}</span>
                  <span className="text-muted">
                    {ex.sets}×{ex.reps}
                    {ex.working_weight_kg != null && ` · ${ex.working_weight_kg} кг`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-line bg-surface p-4">
        <p className="font-display font-semibold tracking-tight">Недельная прогрессия</p>
        <ol className="mt-2 flex flex-col gap-1.5 text-sm">
          {plan.weekly_progression.map((w) => (
            <li key={w.week} className="flex gap-2">
              <span className="shrink-0 text-muted">Неделя {w.week}:</span>
              <span>{w.adjustment}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

// Связка еда↔тренировка в явном виде: какой рацион в день тренировки, какой — в день
// отдыха. Делает зависимость питания от наличия нагрузки видимой прямо в плане тренировок.
function FoodLinkLegend({ trainingCal, restCal }: { trainingCal: number; restCal: number }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-accent/30 bg-panel p-4 sm:flex-row sm:items-center sm:gap-4">
      <span className="font-display text-xs font-semibold tracking-[0.15em] text-accent uppercase">
        Связка с едой
      </span>
      <p className="text-sm leading-relaxed text-muted">
        Дни тренировок → рацион <span className="font-medium text-fg">тренировочного дня</span> (
        {trainingCal} ккал); дни отдыха → рацион{' '}
        <span className="font-medium text-fg">дня отдыха</span> ({restCal} ккал).
      </p>
    </div>
  );
}
