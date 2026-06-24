/** Минимальные недельные формы (Вес / Замеры / Фото) для попапа недели. Даты НЕТ — пишем на
 *  дату недели (`date`). Раскрываются инлайн в строках попапа (как дневные формы), у каждой —
 *  кнопка «Сохранить». Замеры: талия/грудь/ягодицы обязательны, остальное по желанию. */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, type BodyMeasurementInput } from '../../lib/api';
import { inputCls, SaveButton, errText, numOrNull } from './formKit';

export function WeekWeightForm({ date }: { date: string }) {
  const qc = useQueryClient();
  const [w, setW] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api.createWeight({ date, weight_kg: Number(w) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const n = Number(w);
    if (!w.trim() || !Number.isFinite(n) || n <= 0) {
      setErr('Введите вес — число в кг.');
      return;
    }
    setErr(null);
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex max-w-[12rem] flex-col gap-1">
        <span className="text-xs text-muted">Вес, кг</span>
        <input
          className={`${inputCls} tabular-nums`}
          type="number"
          step="any"
          inputMode="decimal"
          value={w}
          onChange={(e) => {
            setW(e.target.value);
            setErr(null);
            save.reset();
          }}
          placeholder="—"
        />
      </label>
      {err && <p className="text-xs font-medium text-amber">{err}</p>}
      {save.isError && <p className="text-xs font-medium text-amber">{errText(save.error)}</p>}
      <SaveButton pending={save.isPending} success={save.isSuccess} />
    </form>
  );
}

type MKey = Exclude<keyof BodyMeasurementInput, 'date'>;
const REQUIRED: MKey[] = ['waist_cm', 'chest_cm', 'glutes_cm'];
const M_FIELDS: { key: MKey; label: string }[] = [
  { key: 'waist_cm', label: 'Талия' },
  { key: 'chest_cm', label: 'Грудь' },
  { key: 'glutes_cm', label: 'Ягодицы' },
  { key: 'belly_cm', label: 'Живот' },
  { key: 'shoulders_cm', label: 'Плечи' },
  { key: 'biceps_l_cm', label: 'Бицепс Л' },
  { key: 'biceps_r_cm', label: 'Бицепс П' },
  { key: 'calf_l_cm', label: 'Икра Л' },
  { key: 'calf_r_cm', label: 'Икра П' },
  { key: 'height_cm', label: 'Рост' },
];

export function WeekMeasurementsForm({ date }: { date: string }) {
  const qc = useQueryClient();
  const [vals, setVals] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => {
      const payload: BodyMeasurementInput = {
        date,
        height_cm: numOrNull(vals.height_cm),
        waist_cm: numOrNull(vals.waist_cm),
        belly_cm: numOrNull(vals.belly_cm),
        chest_cm: numOrNull(vals.chest_cm),
        shoulders_cm: numOrNull(vals.shoulders_cm),
        glutes_cm: numOrNull(vals.glutes_cm),
        biceps_l_cm: numOrNull(vals.biceps_l_cm),
        biceps_r_cm: numOrNull(vals.biceps_r_cm),
        calf_l_cm: numOrNull(vals.calf_l_cm),
        calf_r_cm: numOrNull(vals.calf_r_cm),
      };
      return api.createMeasurement(payload);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const missing = REQUIRED.filter((k) => numOrNull(vals[k]) == null);
    if (missing.length) {
      const labels = M_FIELDS.filter((f) => missing.includes(f.key)).map((f) => f.label);
      setErr(`Обязательные поля: ${labels.join(', ')}.`);
      return;
    }
    setErr(null);
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {M_FIELDS.map((f) => {
          const req = REQUIRED.includes(f.key);
          return (
            <label key={f.key} className="flex flex-col gap-1">
              <span className="text-xs text-muted">
                {f.label}
                {req && <span className="text-accent"> *</span>}
              </span>
              <input
                className={`${inputCls} tabular-nums`}
                type="number"
                step="any"
                inputMode="decimal"
                value={vals[f.key] ?? ''}
                onChange={(e) => {
                  setVals((v) => ({ ...v, [f.key]: e.target.value }));
                  setErr(null);
                  save.reset();
                }}
                placeholder="—"
              />
            </label>
          );
        })}
      </div>
      <p className="text-xs text-muted">
        <span className="text-accent">*</span> — обязательно
      </p>
      {err && <p className="text-xs font-medium text-amber">{err}</p>}
      {save.isError && <p className="text-xs font-medium text-amber">{errText(save.error)}</p>}
      <SaveButton pending={save.isPending} success={save.isSuccess} />
    </form>
  );
}

const photoBtn =
  'cursor-pointer rounded-full border border-line px-3 py-1.5 text-xs font-medium text-fg transition-colors duration-[var(--duration-fast)] hover:border-accent/50';

/** Съёмка с камеры устройства (ноутбук/телефон) через getUserMedia → кадр в JPEG-файл. */
function CameraShot({
  onCapture,
  onCancel,
}: {
  onCapture: (f: File) => void;
  onCancel: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      .then((stream) => {
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      })
      .catch(() => setErr('Камера недоступна. Разрешите доступ к камере или выберите файл.'));
    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const shoot = () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d')?.drawImage(v, 0, 0);
    canvas.toBlob(
      (blob) => blob && onCapture(new File([blob], 'camera.jpg', { type: 'image/jpeg' })),
      'image/jpeg',
      0.92,
    );
  };

  if (err)
    return (
      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium text-amber">{err}</p>
        <button type="button" onClick={onCancel} className={photoBtn + ' self-start'}>
          Назад
        </button>
      </div>
    );

  return (
    <div className="flex flex-col gap-2">
      <video
        ref={videoRef}
        playsInline
        muted
        className="h-44 w-auto rounded-lg border border-line bg-ink object-cover"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={shoot}
          className="rounded-full bg-accent px-4 py-1.5 text-xs font-semibold text-accent-ink"
        >
          Снять
        </button>
        <button type="button" onClick={onCancel} className={photoBtn}>
          Отмена
        </button>
      </div>
    </div>
  );
}

export function WeekPhotoForm({ date }: { date: string }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [camera, setCamera] = useState(false);

  const save = useMutation({
    mutationFn: () => api.uploadBodyPhoto(file as File, date),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['body-photos'] });
    },
  });

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    save.reset();
  };

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (file) save.mutate();
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      {camera ? (
        <CameraShot
          onCapture={(f) => {
            setCamera(false);
            pick(f);
          }}
          onCancel={() => setCamera(false)}
        />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            <label className={photoBtn}>
              Выбрать файл
              <input
                type="file"
                accept="image/png,image/jpeg,image/heic,image/heif,image/*"
                className="hidden"
                onChange={(e) => pick(e.target.files?.[0])}
              />
            </label>
            <button type="button" className={photoBtn} onClick={() => setCamera(true)}>
              Снять фото
            </button>
          </div>
          {preview && (
            <img
              src={preview}
              alt=""
              className="h-32 w-auto rounded-lg border border-line object-cover"
            />
          )}
          {save.isError && <p className="text-xs font-medium text-amber">{errText(save.error)}</p>}
          {save.isSuccess && <p className="text-xs font-medium text-accent">Фото сохранено ✓</p>}
          <SaveButton pending={save.isPending} success={save.isSuccess} disabled={!file} />
        </>
      )}
    </form>
  );
}
