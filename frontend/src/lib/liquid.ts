/** Премиум-«жидкости» календаря: у каждой категории — иридесцентный мини-спектр (а не один
 *  тон), плюс космический mystery-спектр (магента→роза→коралл→золото, как на референсе).
 *  Жидкости СМЕШИВАЮТСЯ плавной интерполяцией одного градиента (без жёстких полос), а сверху
 *  идёт анимированный перелив (sheen/iridescence) — отсюда «премиум» и «переливается». */

// Каждая категория — спектр из 3 oklch-тонов: снизу-вверх внутри своей жидкости.
const SPECTRA: Record<string, readonly string[]> = {
  has_food: ['oklch(80% 0.18 162)', 'oklch(86% 0.19 150)', 'oklch(90% 0.18 138)'], // изумруд→зелёный→лайм (без бирюзы — Еда одного цвета на любой позиции)
  has_activity: ['oklch(72% 0.15 45)', 'oklch(84% 0.17 78)', 'oklch(91% 0.14 100)'], // коралл→янтарь→мёд
  has_training: ['oklch(55% 0.20 295)', 'oklch(64% 0.19 268)', 'oklch(75% 0.16 232)'], // фиолет→индиго→лазурь
  has_weight: ['oklch(58% 0.21 330)', 'oklch(72% 0.23 350)', 'oklch(84% 0.16 12)'], // фуксия→роза
  has_body: ['oklch(56% 0.18 300)', 'oklch(70% 0.17 285)', 'oklch(81% 0.14 268)'], // аметист→фиолет
  has_photo: ['oklch(72% 0.15 55)', 'oklch(85% 0.16 82)', 'oklch(92% 0.13 102)'], // бронза→золото
  has_inbody: ['oklch(60% 0.13 200)', 'oklch(72% 0.14 192)', 'oklch(83% 0.13 185)'], // циан→аква→тил (состав тела)
};

/** Космический mystery (идеальная неделя): магента→розовый→коралл→золото — как референс. */
export const MYSTERY_SPECTRUM = [
  'oklch(50% 0.23 350)',
  'oklch(66% 0.28 345)',
  'oklch(78% 0.21 18)',
  'oklch(90% 0.13 72)',
];

/** Представительный цвет категории (легенда/точки) — средний тон её спектра. */
export function keyColor(key: string): string {
  const s = SPECTRA[key];
  return s ? s[1] : 'oklch(80% 0.02 256)';
}

/** CSS-градиент жидкости снизу-вверх из спектров активных категорий (плавное смешение).
 *  0deg указывает вверх → первый стоп внизу. Несколько категорий перетекают друг в друга. */
export function liquidGradient(activeKeys: readonly string[], mystery: boolean): string {
  const colors = mystery ? MYSTERY_SPECTRUM : activeKeys.flatMap((k) => SPECTRA[k] ?? []);
  if (colors.length === 0) return 'transparent';
  if (colors.length === 1) return colors[0];
  const stops = colors
    .map((c, i) => `${c} ${Math.round((i / (colors.length - 1)) * 100)}%`)
    .join(', ');
  return `linear-gradient(0deg, ${stops})`;
}

/** Премиум-цвета категорий дня для ПОЛНОЙ заливки (3/3): еда — зелёный, активность — оранжевый,
 *  тренировки — фиолетово-магентовый (магента к розовому недели). По одному тону на категорию. */
const DAY_FULL_COLORS: Record<string, string> = {
  has_food: 'oklch(84% 0.18 160)',
  has_activity: 'oklch(83% 0.15 66)',
  has_training: 'oklch(62% 0.21 322)',
};

/** Заливка ПОЛНОГО дня (3/3): те же премиум-цвета категорий, но В ПОРЯДКЕ ВНЕСЕНИЯ (как частичный
 *  день) — первый внесённый снизу, последний сверху. Градиент подстраивается под порядок. */
export function dayFullFill(orderedKeys: readonly string[]): string {
  const colors = orderedKeys.map((k) => DAY_FULL_COLORS[k] ?? keyColor(k));
  return colors.length ? `linear-gradient(0deg, ${colors.join(', ')})` : 'transparent';
}

/** Цвет свечения вокруг полной жидкости/медали. */
export function glowColor(mystery: boolean): string {
  return mystery ? 'oklch(72% 0.26 345)' : 'oklch(84% 0.16 150)';
}

/** Доп. «медиа-кольцо» для дня с медиа тренировки (has_workout_media): тонкий золотистый
 *  кант + мягкое inset-свечение в тон спектра has_photo (бронза→золото). Это box-shadow-строка,
 *  складывается через запятую с внешним glow полного дня в одном `box-shadow`. */
export function mediaRingShadow(): string {
  return 'inset 0 0 0 1.5px oklch(86% 0.15 82 / 0.75), inset 0 0 10px -1px oklch(90% 0.15 85 / 0.85)';
}

/** Бонус-подсветка недельной ячейки за полные замеры (has_weight && has_body): фуксиево-розовое
 *  внешнее свечение (тон спектра has_weight) + аметистовый inset (тон has_body). box-shadow-строка,
 *  складывается через запятую с зелёным glow полной недели в одном `box-shadow`. */
export function measureGlow(): string {
  return '0 0 16px -1px oklch(74% 0.22 340 / 0.9), inset 0 0 9px -1px oklch(70% 0.16 290 / 0.7)';
}
