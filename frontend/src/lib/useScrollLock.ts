/** Блокирует скролл фона, пока смонтирована модалка. Компенсирует ширину скроллбара
 *  (padding-right), чтобы фон не «дёргался» при его исчезновении. Восстанавливает прежние
 *  значения при размонтировании (корректно при вложенных модалках). */

import { useEffect } from 'react';

export function useScrollLock(): void {
  useEffect(() => {
    const html = document.documentElement; // именно корень — на нём скроллится вьюпорт
    const { body } = document;
    const scrollbar = window.innerWidth - html.clientWidth;
    const prevOverflow = html.style.overflow;
    const prevPaddingRight = body.style.paddingRight;

    html.style.overflow = 'hidden';
    if (scrollbar > 0) body.style.paddingRight = `${scrollbar}px`;

    return () => {
      html.style.overflow = prevOverflow;
      body.style.paddingRight = prevPaddingRight;
    };
  }, []);
}
