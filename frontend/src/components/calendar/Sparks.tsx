/** Слой искр-фейерверка для полной ячейки (день/неделя/медаль). Декоративный (aria-hidden),
 *  под prefers-reduced-motion скрывается целиком (см. .sparkle в index.css). Геометрию даёт
 *  makeSparks, размер частицы прокидывается в CSS как --spark-size. */

import { makeSparks, type SparkOptions } from '../../lib/sparks';

export function Sparks(opts: SparkOptions) {
  const { size, sparks } = makeSparks(opts);
  return (
    <span
      className="sparkles"
      aria-hidden="true"
      style={{ '--spark-size': `${size}px` } as React.CSSProperties}
    >
      {sparks.map((s, i) => (
        <span
          key={i}
          className="sparkle"
          style={
            {
              left: `${s.x}%`,
              top: `${s.y}%`,
              '--dx': `${s.dx}px`,
              '--dy': `${s.dy}px`,
              '--dur': `${s.dur}ms`,
              '--delay': `${s.delay}ms`,
            } as React.CSSProperties
          }
        />
      ))}
    </span>
  );
}
