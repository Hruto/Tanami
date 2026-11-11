// All dates are shown in the service timezone, matching the mobile app.
const TIME_ZONE = "Asia/Jakarta";

const dateLong = new Intl.DateTimeFormat("id-ID", {
  timeZone: TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const dateShort = new Intl.DateTimeFormat("id-ID", {
  timeZone: TIME_ZONE,
  day: "numeric",
  month: "short",
  year: "numeric",
});
const dateTime = new Intl.DateTimeFormat("id-ID", {
  timeZone: TIME_ZONE,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const relative = new Intl.RelativeTimeFormat("id-ID", { numeric: "auto" });
const number = new Intl.NumberFormat("id-ID");

export const formatNumber = (value: number): string => number.format(value);
export const formatDateLong = (value: string | Date): string => dateLong.format(new Date(value));
export const formatDate = (value: string | Date): string => dateShort.format(new Date(value));
export const formatDateTime = (value: string | Date): string => dateTime.format(new Date(value));

export function formatRelative(value: string | Date, now: Date = new Date()): string {
  const seconds = (new Date(value).getTime() - now.getTime()) / 1000;
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "baru saja";
}

export function greeting(now: Date = new Date()): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, hour: "2-digit", hourCycle: "h23" }).format(now),
  );
  if (hour < 11) return "Selamat pagi";
  if (hour < 15) return "Selamat siang";
  if (hour < 18) return "Selamat sore";
  return "Selamat malam";
}

export function firstName(fullName: string): string {
  const parts = fullName.split(" ").filter(Boolean);
  const titled = parts[0]?.endsWith(".") && parts.length > 1;
  return (titled ? parts[1] : parts[0]) ?? fullName;
}
