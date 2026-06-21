/** Нормализация данных тренировочного прогресса (S3.12) для графиков на экране
 *  «Прогресс». Сводит ряды S3.11 (/progress/strength, /progress/cardio) + личные
 *  рекорды S3.10 (/workouts/prs) в плоские «вью», которые компонент рисует без
 *  ветвлений. Когда реальной динамики ещё нет (одна тренировка / пустая БД), отдаём
 *  демо-набор с многоточечным трендом и парой PR — графики и подсветка PR обязаны
 *  отрисоваться (критерии приёмки). Чистый модуль: без React, легко проверяется. */

import type {
  CardioProgress,
  Exercise,
  ExerciseCardioSeries,
  ExerciseStrengthSeries,
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
  isSample: boolean;
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

export type CardioView = { exercises: CardioExerciseView[]; isSample: boolean };

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function iso(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Равномерные `points` дат внутри окна периода, заканчивая сегодня. */
function demoDates(periodDays: number, points: number): string[] {
  const end = new Date();
  const step = Math.max(1, Math.floor((periodDays - 1) / (points - 1)));
  const dates: string[] = [];
  for (let i = points - 1; i >= 0; i--) {
    const d = new Date(end);
    d.setDate(d.getDate() - i * step);
    dates.push(iso(d));
  }
  return dates;
}

/** Линейный тренд from→to по датам (округление до 0.1). */
function trend(dates: string[], from: number, to: number): SeriesPoint[] {
  const n = dates.length;
  return dates.map((date, i) => ({
    date,
    value: Math.round((from + ((to - from) * i) / (n - 1)) * 10) / 10,
  }));
}

/** Есть ли в рядах реальная динамика (≥2 точек хотя бы в одной метрике). Один
 *  изолированный замер — не тренд, для него честнее показать демо. */
function hasStrengthDynamics(series: ExerciseStrengthSeries[]): boolean {
  return series.some(
    (e) => e.working_weight.length >= 2 || e.best_1rm.length >= 2 || e.tonnage.length >= 2,
  );
}

function hasCardioDynamics(series: ExerciseCardioSeries[]): boolean {
  return series.some(
    (e) =>
      e.distance.length >= 2 ||
      e.pace.length >= 2 ||
      e.avg_hr.length >= 2 ||
      e.efficiency.length >= 2,
  );
}

/** Даты PR данного упражнения и метрики — для подсветки точек на графике. */
function prDates(prs: PersonalRecord[], exerciseId: number, metric: string): Set<string> {
  return new Set(
    prs.filter((p) => p.exercise_id === exerciseId && p.metric === metric).map((p) => p.date),
  );
}

/** Демо силовых: два упражнения с растущим весом/1ПМ и парой PR (середина + финал),
 *  чтобы динамика и подсветка PR были видны на пустой БД. */
function buildStrengthSample(periodDays: number): StrengthView {
  const dates = demoDates(periodDays, 7);
  const prAt = new Set([dates[3], dates[6]]); // подсвечиваем два явных рекорда

  const bench: StrengthExerciseView = {
    id: -1,
    name: 'Жим лёжа (демо)',
    weight: trend(dates, 70, 85),
    oneRm: trend(dates, 88, 112),
    tonnage: trend(dates, 1400, 2040),
    prWeightDates: prAt,
    pr1rmDates: prAt,
  };
  const squat: StrengthExerciseView = {
    id: -2,
    name: 'Присед (демо)',
    weight: trend(dates, 100, 120),
    oneRm: trend(dates, 125, 150),
    tonnage: trend(dates, 2000, 2640),
    prWeightDates: new Set([dates[6]]),
    pr1rmDates: new Set([dates[6]]),
  };

  return {
    exercises: [bench, squat],
    groups: [
      { sportId: -1, name: 'Пауэрлифтинг (демо)', tonnage: trend(dates, 3400, 4680) },
      { sportId: -2, name: 'Бодибилдинг (демо)', tonnage: trend(dates, 1800, 2500) },
    ],
    isSample: true,
  };
}

/** Демо кардио: один бег с растущей дистанцией, улучшающимся темпом и PR. */
function buildCardioSample(periodDays: number): CardioView {
  const dates = demoDates(periodDays, 7);
  const run: CardioExerciseView = {
    id: -1,
    name: 'Бег (демо)',
    distance: trend(dates, 4, 7),
    pace: trend(dates, 330, 300), // темп падает — бежим быстрее
    avgHr: trend(dates, 158, 148),
    efficiency: trend(dates, 1.1, 1.5),
    prDistanceDates: new Set([dates[6]]),
    prPaceDates: new Set([dates[6]]),
  };
  return { exercises: [run], isSample: true };
}

/** Силовой вью: реальные ряды (с подсветкой реальных PR), если есть динамика; иначе демо. */
export function buildStrengthView(
  data: StrengthProgress | undefined,
  exercises: Exercise[],
  sports: Sport[],
  prs: PersonalRecord[],
  periodDays: number,
): StrengthView {
  if (!data || !hasStrengthDynamics(data.by_exercise)) {
    return buildStrengthSample(periodDays);
  }
  const exName = new Map(exercises.map((e) => [e.id, e.name]));
  const sportName = new Map(sports.map((s) => [s.id, s.name]));

  return {
    isSample: false,
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

/** Кардио-вью: реальные ряды (с подсветкой реальных PR), если есть динамика; иначе демо. */
export function buildCardioView(
  data: CardioProgress | undefined,
  exercises: Exercise[],
  prs: PersonalRecord[],
  periodDays: number,
): CardioView {
  if (!data || !hasCardioDynamics(data.by_exercise)) {
    return buildCardioSample(periodDays);
  }
  const exName = new Map(exercises.map((e) => [e.id, e.name]));

  return {
    isSample: false,
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
