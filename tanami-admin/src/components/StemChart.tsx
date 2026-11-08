import { useEffect, useState, type CSSProperties } from "react";

import { formatNumber } from "../lib/format";

interface Day {
  day: string;
  disease: number;
  ripeness: number;
}

const HEIGHT = 230;
const BASELINE = 178;
const TOP = 28;

const dayFormat = new Intl.DateTimeFormat("id-ID", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const monthFormat = new Intl.DateTimeFormat("id-ID", { month: "short", timeZone: "UTC" });

function parseDay(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

/**
 * Daily scans drawn as plant stems: the stem height is the number of photos
 * analysed that day, the leaf at the tip marks leaf photos and a second,
 * lighter leaf marks fruit photos. Empty days are a seed on the soil line.
 */
function useNarrow(query = "(max-width: 600px)"): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setNarrow(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return narrow;
}

export function StemChart({ days: allDays }: { days: Day[] }) {
  const [active, setActive] = useState<number | null>(null);
  // A phone shows the last week so the labels stay readable.
  const narrow = useNarrow();
  const days = narrow ? allDays.slice(-7) : allDays;
  // The viewBox roughly matches the rendered width so text stays near 1:1.
  const WIDTH = narrow ? 360 : 1000;
  const STEP = WIDTH / Math.max(1, days.length);
  const max = Math.max(1, ...days.map((d) => d.disease + d.ripeness));
  const scale = (value: number) => ((BASELINE - TOP) * value) / max;

  const focused = active === null ? null : days[active];

  return (
    <figure className="stems">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby="stems-caption">
        <line x1="0" x2={WIDTH} y1={BASELINE} y2={BASELINE} className="stems-soil" />
        {days.map((day, index) => {
          const x = STEP * index + STEP / 2;
          const total = day.disease + day.ripeness;
          const tip = BASELINE - scale(total);
          const fork = BASELINE - scale(day.disease);
          const date = parseDay(day.day);
          const isLast = index === days.length - 1;
          const showMonth = index === 0 || date.getUTCDate() === 1;
          return (
            <g
              key={day.day}
              className={active === index ? "stem is-active" : "stem"}
              style={{ "--delay": `${index * 45}ms` } as CSSProperties}
              tabIndex={0}
              onMouseEnter={() => setActive(index)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
            >
              <rect x={x - STEP / 2} y={0} width={STEP} height={HEIGHT} fill="transparent" />
              {total === 0 ? (
                <circle cx={x} cy={BASELINE} r="3" className="stem-seed" />
              ) : (
                <>
                  <line x1={x} x2={x} y1={BASELINE} y2={tip} className="stem-line" pathLength={1} />
                  {day.disease > 0 ? (
                    <path
                      d={`M ${x} ${fork} c -2 -9 -9 -13 -17 -13 c 1 8 7 13 17 13 Z`}
                      className="stem-leaf"
                    />
                  ) : null}
                  {day.ripeness > 0 ? (
                    <path
                      d={`M ${x} ${tip} c 2 -9 9 -13 17 -13 c -1 8 -7 13 -17 13 Z`}
                      className="stem-fruit"
                    />
                  ) : null}
                  <text x={x} y={tip - 18} className="stem-value num">
                    {formatNumber(total)}
                  </text>
                </>
              )}
              <text x={x} y={BASELINE + 22} className={isLast ? "stem-day is-today" : "stem-day"}>
                {date.getUTCDate()}
              </text>
              {showMonth ? (
                <text x={x} y={BASELINE + 40} className="stem-month">
                  {monthFormat.format(date)}
                </text>
              ) : null}
              {isLast ? (
                <text x={x} y={BASELINE + 40} className="stem-month">
                  hari ini
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <figcaption id="stems-caption" className="stems-caption">
        {focused ? (
          <span>
            {dayFormat.format(parseDay(focused.day))}: {formatNumber(focused.disease)} foto daun,{" "}
            {formatNumber(focused.ripeness)} foto buah.
          </span>
        ) : (
          <span>
            Foto yang dianalisis per hari, {days.length} hari terakhir. Daun hijau tua untuk foto daun, daun hijau
            muda untuk foto buah.
          </span>
        )}
      </figcaption>
      <table className="sr-only">
        <caption>Jumlah foto dianalisis per hari</caption>
        <thead>
          <tr>
            <th>Tanggal</th>
            <th>Foto daun</th>
            <th>Foto buah</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.day}>
              <td>{dayFormat.format(parseDay(day.day))}</td>
              <td>{day.disease}</td>
              <td>{day.ripeness}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
