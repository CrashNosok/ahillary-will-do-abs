/** Нормализация данных тренировочного прогресса (S3.12) для графиков на экране
 *  «Прогресс». Сводит ряды S3.11 (/progress/strength, /progress/cardio) + личные
 *  рекорды S3.10 (/workouts/prs) в плоские «вью», которые компонент рисует без
 *  ветвлений. ТОЛЬКО реальные данные из БД: нет тренировок — пустой список (компонент
 *  покажет честный empty-state), демо/выдуманные ряды не подставляем. */

import type {
  CardioProgress,
  Exercise,
  PersonalRecord,
  SeriesPoint,
  Sport,
  StrengthProgress,
} from './api';

export type StrengthExerciseView = {
  id: number;
  name: string;
  weight: SeriesPoint[]; // рабочий вес, кг
  oneRm: SeriesPoint[]; // 1ПМ (Эпли), кг
  tonnage: SeriesPoint[]; // тоннаж, кг
  prWeightDates: Set<string>; // даты PR по рабочему весу — подсветка на линии веса
  pr1rmDates: Set<string>; // даты PR по 1ПМ — подсветка на линии 1ПМ
};

export type GroupTonnageView = { sportId: number | null; name: string; tonnage: SeriesPoint[] };

export type StrengthView = {
  exercises: StrengthExerciseView[];
  groups: GroupTonnageView[];
};

export type CardioExerciseView = {
  id: number | null;
  name: string;
  distance: SeriesPoint[]; // км/день
  pace: SeriesPoint[]; // сек/км (меньше — лучше)
  avgHr: SeriesPoint[]; // средний пульс
  efficiency: SeriesPoint[]; // метров на удар сердца
  prDistanceDates: Set<string>; // PR по дистанции
  prPaceDates: Set<string>; // PR по темпу
};

export type CardioView = { exercises: CardioExerciseView[] };

/** Даты PR данного упражнения и метрики — для подсветки точек на графике. */
function prDates(prs: PersonalRecord[], exerciseId: number, metric: string): Set<string> {
  return new Set(
    prs.filter((p) => p.exercise_id === exerciseId && p.metric === metric).map((p) => p.date),
  );
}

/** Силовой вью из реальных рядов (с подсветкой реальных PR). Нет данных → пустой список. */
export function buildStrengthView(
  data: StrengthProgress | undefined,
  exercises: Exercise[],
  sports: Sport[],
  prs: PersonalRecord[],
): StrengthView {
  if (!data) return { exercises: [], groups: [] };
  const exName = new Map(exercises.map((e) => [e.id, e.name]));
  const sportName = new Map(sports.map((s) => [s.id, s.name]));

  return {
    exercises: data.by_exercise.map((e) => ({
      id: e.exercise_id,
      name: exName.get(e.exercise_id) ?? `Упражнение ${e.exercise_id}`,
      weight: e.working_weight,
      oneRm: e.best_1rm,
      tonnage: e.tonnage,
      prWeightDates: prDates(prs, e.exercise_id, 'max_weight'),
      pr1rmDates: prDates(prs, e.exercise_id, 'best_1rm'),
    })),
    groups: data.by_group.map((g) => ({
      sportId: g.sport_id,
      name:
        g.sport_id === null
          ? 'Без вида спорта'
          : (sportName.get(g.sport_id) ?? `Вид спорта ${g.sport_id}`),
      tonnage: g.tonnage,
    })),
  };
}

/** Кардио-вью из реальных рядов (с подсветкой реальных PR). Нет данных → пустой список. */
export function buildCardioView(
  data: CardioProgress | undefined,
  exercises: Exercise[],
  prs: PersonalRecord[],
): CardioView {
  if (!data) return { exercises: [] };
  const exName = new Map(exercises.map((e) => [e.id, e.name]));

  return {
    exercises: data.by_exercise.map((e) => ({
      id: e.exercise_id,
      name:
        e.exercise_id === null
          ? 'Кардио (без упражнения)'
          : (exName.get(e.exercise_id) ?? `Упражнение ${e.exercise_id}`),
      distance: e.distance,
      pace: e.pace,
      avgHr: e.avg_hr,
      efficiency: e.efficiency,
      prDistanceDates:
        e.exercise_id === null ? new Set() : prDates(prs, e.exercise_id, 'max_distance'),
      prPaceDates: e.exercise_id === null ? new Set() : prDates(prs, e.exercise_id, 'best_pace'),
    })),
  };
}
