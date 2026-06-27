/** «Цели и план по видам спорта» в «Мой кабинет»: на каждый привязанный вид — числовые цели
 *  по измеримым базовым упражнениям (силовые/кардио). План навыков добавляется отдельным блоком
 *  (Фаза 5). Цели по упражнениям рисуются целевыми линиями на графиках «Прогресс». */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { Achievement, AchievementTier, UserSport } from '../lib/api';
import {
  useAchievementsForSport,
  useGenerateAchievements,
  usePlanAchievement,
} from '../lib/achievements';
import {
  useDeleteExerciseTarget,
  useExerciseTargets,
  useSaveExerciseTarget,
} from '../lib/exerciseTargets';
import { useExercises } from '../lib/sports';

const TIER_LABEL: Record<AchievementTier, string> = {
  foundation: 'База',
  intermediate: 'Средний',
  advanced: 'Продвинутый',
  elite: 'Элита',
};

const inputCls =
  'rounded-xl border border-line bg-surface px-4 py-2.5 text-fg outline-none transition-colors duration-[var(--duration-fast)] focus:border-accent';

export default function SportPlanSection({ sports }: { sports: UserSport[] }) {
  if (sports.length === 0) return null;
  return (
    <div className="flex flex-col gap-5">
      <h2 className="text-display">Цели и план по видам спорта</h2>
      <div className="flex flex-col gap-5">
        {sports.map((s) => (
          <div
            key={s.sport_id}
            className="flex flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-surface p-6"
          >
            <h3 className="font-display text-xl font-semibold tracking-tight">{s.name}</h3>
            <ExerciseTargetsForSport sportId={s.sport_id} />
            <SkillPlanForSport sportId={s.sport_id} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Числовые цели по измеримым упражнениям вида (силовые/кадио). Одна форма: пустое значение
 *  снимает цель, число — ставит/обновляет (upsert). Навыковые упражнения сюда не идут — они в
 *  плане навыков (статус-механика достижений). */
function ExerciseTargetsForSport({ sportId }: { sportId: number }) {
  const { data: allExercises } = useExercises();
  const { data: targets } = useExerciseTargets();
  const save = useSaveExerciseTarget();
  const del = useDeleteExerciseTarget();
  const exercises = allExercises?.filter((e) => e.sport_id === sportId);
  const measurable = (exercises ?? []).filter((e) => e.kind === 'strength' || e.kind === 'cardio');
  const [vals, setVals] = useState<Record<number, string>>({});
  const hydrated = useRef(false);

  useEffect(() => {
    if (hydrated.current || !exercises || !targets) return;
    const tmap = new Map(targets.map((t) => [t.exercise_id, t.target_value]));
    const next: Record<number, string> = {};
    // measurable выводим внутри эффекта (стабильные зависимости — exercises/targets).
    for (const ex of exercises.filter((e) => e.kind === 'strength' || e.kind === 'cardio')) {
      const t = tmap.get(ex.id);
      next[ex.id] = t != null ? String(t) : '';
    }
    setVals(next);
    hydrated.current = true;
  }, [exercises, targets]);

  if (exercises && measurable.length === 0) {
    return (
      <p className="text-sm text-muted">
        Нет измеримых упражнений для числовых целей — развитие этого вида в плане навыков ниже.
      </p>
    );
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const tmap = new Map((targets ?? []).map((t) => [t.exercise_id, t.target_value]));
    for (const ex of measurable) {
      const raw = (vals[ex.id] ?? '').trim();
      const n = raw === '' ? null : Number(raw);
      const cur = tmap.get(ex.id) ?? null;
      if (n == null) {
        if (cur != null) del.mutate(ex.id); // очистили — снимаем цель
      } else if (Number.isFinite(n) && n !== cur) {
        save.mutate({ exercise_id: ex.id, target_value: n, unit: ex.unit });
      }
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <p className="text-sm font-medium text-muted">Цели по упражнениям</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {measurable.map((ex) => (
          <label key={ex.id} className="flex flex-col gap-1">
            <span className="text-xs text-muted">
              {ex.name}
              {ex.unit ? `, ${ex.unit}` : ''}
            </span>
            <input
              type="number"
              inputMode="decimal"
              step="any"
              min="0"
              value={vals[ex.id] ?? ''}
              onChange={(e) => setVals((v) => ({ ...v, [ex.id]: e.target.value }))}
              placeholder="—"
              className={`${inputCls} tabular-nums`}
            />
          </label>
        ))}
      </div>
      {(save.isError || del.isError) && (
        <p role="alert" className="text-sm font-medium text-amber">
          Часть целей не сохранилась — проверьте, что сервер запущен, и повторите.
        </p>
      )}
      <button
        type="submit"
        disabled={save.isPending || del.isPending}
        className="w-fit rounded-xl border border-line px-4 py-2 text-sm font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {save.isPending || del.isPending ? 'Сохраняем…' : 'Сохранить цели упражнений'}
      </button>
    </form>
  );
}

/** План навыков вида (через достижения): «В план» (locked→in_progress) и «Учу» (снять). «Освоено»
 *  (unlocked) — только просмотр (закрытие через видео-пруф на странице вида / витрине ачивок).
 *  Если навыков ещё нет — кнопка LLM-генерации набора под дисциплину. */
function SkillPlanForSport({ sportId }: { sportId: number }) {
  const { data: achievements, isPending } = useAchievementsForSport(sportId);
  const plan = usePlanAchievement(sportId);
  const generate = useGenerateAchievements(sportId);
  const list = achievements ?? [];

  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4">
      <p className="text-sm font-medium text-muted">План навыков — чему хочу научиться</p>
      {isPending ? (
        <p className="text-sm text-muted">Загрузка…</p>
      ) : list.length === 0 ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">Навыки для этого вида ещё не заведены.</p>
          <button
            type="button"
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            className="w-fit rounded-xl border border-line px-4 py-2 text-sm font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {generate.isPending ? 'Генерируем…' : 'Сгенерировать навыки'}
          </button>
          {generate.isError && (
            <p className="text-sm font-medium text-amber">
              Не удалось сгенерировать (модель недоступна).
            </p>
          )}
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {list.map((a) => (
            <li
              key={a.id}
              className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-panel px-3 py-2"
            >
              <span className="font-medium">{a.title}</span>
              {a.level && (
                <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">
                  {TIER_LABEL[a.level as AchievementTier] ?? a.level}
                </span>
              )}
              <SkillStatusControl achievement={a} plan={plan} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const skillBtn =
  'rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-[var(--duration-fast)] disabled:cursor-not-allowed disabled:opacity-60';

/** Контрол статуса навыка в плане: «В план» / «Учу — убрать» / «Освоено» (только просмотр). */
function SkillStatusControl({
  achievement,
  plan,
}: {
  achievement: Achievement;
  plan: ReturnType<typeof usePlanAchievement>;
}) {
  if (achievement.status === 'unlocked') {
    return (
      <span className="ml-auto rounded-full bg-accent/15 px-3 py-1 text-xs font-semibold text-accent">
        Освоено ✓
      </span>
    );
  }
  const planned = achievement.status === 'in_progress';
  return (
    <button
      type="button"
      onClick={() => plan.mutate({ achievementId: achievement.id, planned: !planned })}
      disabled={plan.isPending}
      className={`ml-auto ${skillBtn} ${
        planned
          ? 'border-accent bg-accent/15 text-accent hover:bg-accent/25'
          : 'border-line text-fg hover:border-accent/50'
      }`}
    >
      {planned ? 'Учу — убрать' : 'В план'}
    </button>
  );
}
