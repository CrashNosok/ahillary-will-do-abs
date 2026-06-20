/** Заглушка маршрута без наполнения — честно для каркаса спринта 0.
 *  Подтверждает, что роутинг до раздела доходит; контент появится в следующих спринтах. */
export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <section aria-labelledby="page-heading" className="max-w-2xl">
      <p className="font-display text-sm font-medium uppercase tracking-[0.2em] text-accent">
        {title}
      </p>
      <h1 id="page-heading" className="mt-3 text-display">
        Раздел в разработке
      </h1>
      <p className="mt-4 text-lg leading-relaxed text-muted">
        Маршрут «{title}» подключён к роутингу. Наполнение появится в следующих спринтах.
      </p>
    </section>
  );
}
