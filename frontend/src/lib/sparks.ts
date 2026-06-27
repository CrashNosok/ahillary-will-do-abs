/** Параметризованный «фейерверк» искр для полных ячеек календаря (день/неделя/медаль).
 *  Один генератор вместо трёх захардкоженных массивов: count частиц разлетаются веером из
 *  центра ячейки на spread px, каждая — со своей длительностью/задержкой/направлением (хаос).
 *  Геометрия детерминирована по индексу (без Math.random) → стабильный рендер и снапшоты. */

export type Spark = {
  /** Позиция в контейнере, % (left/top). */
  x: number;
  y: number;
  /** Вектор разлёта наружу, px (CSS-переменные --dx/--dy). */
  dx: number;
  dy: number;
  /** Длительность и задержка анимации, ms. */
  dur: number;
  delay: number;
};

export type SparkOptions = {
  /** Сколько искр в фейерверке. */
  count?: number;
  /** На сколько px искра разлетается наружу. */
  spread?: number;
  /** Базовая длительность полёта, ms (к ней добавляется хаотичный разброс). */
  baseDur?: number;
  /** Диаметр частицы, px → пробрасывается в CSS как --spark-size. */
  size?: number;
};

/** Спецификация фейерверка: размер частицы (для --spark-size) + список искр. */
export type SparkBurst = {
  size: number;
  sparks: Spark[];
};

const DEFAULTS = { count: 8, spread: 14, baseDur: 1300, size: 5 } as const;

// Детерминированный псевдослучайный шум в [0;1) по целому индексу (классический hash на sin).
const noise = (n: number): number => {
  const v = Math.sin(n * 12.9898) * 43758.5453;
  return v - Math.floor(v);
};

/** Строит фейерверк искр по параметрам. Искры раскладываются по кольцу вокруг центра ячейки
 *  с лёгким хаосом по углу/радиусу, разлетаются наружу на ~spread px. */
export function makeSparks(opts: SparkOptions = {}): SparkBurst {
  const count = opts.count ?? DEFAULTS.count;
  const spread = opts.spread ?? DEFAULTS.spread;
  const baseDur = opts.baseDur ?? DEFAULTS.baseDur;
  const size = opts.size ?? DEFAULTS.size;

  const sparks: Spark[] = Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2 + noise(i) * 0.8; // равномерное кольцо + дрожание
    const radius = 30 + noise(i + 7) * 14; // 30–44% от центра
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const drift = spread * (0.7 + noise(i + 3) * 0.6); // разброс дальности полёта
    return {
      x: Math.round(50 + cos * radius),
      y: Math.round(50 + sin * radius),
      dx: Math.round(cos * drift),
      dy: Math.round(sin * drift),
      // Ровный темп: узкий разброс длительности (≈единая скорость) + плавный стаггер старта
      // по индексу (ровная «волна» искр), а не случайные сгустки из чистого шума.
      dur: Math.round(baseDur + noise(i + 11) * 250),
      delay: Math.round((i / count) * 500 + noise(i + 17) * 120),
    };
  });

  return { size, sparks };
}
