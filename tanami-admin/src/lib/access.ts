import type { Role } from "../api/types";

export type Area = "overview" | "reports" | "review" | "diseases" | "users" | "announcements";

// Mirrors the role checks in tanami-backend/app/api/v1/staff.py. The server
// enforces them; this only decides which screens are offered.
const ACCESS: Record<Area, Role[]> = {
  overview: ["expert", "moderator", "admin"],
  reports: ["moderator", "admin"],
  review: ["expert", "admin"],
  diseases: ["expert", "admin"],
  users: ["admin"],
  announcements: ["admin"],
};

export function canUse(role: Role | undefined, area: Area): boolean {
  return role !== undefined && ACCESS[area].includes(role);
}

export function isStaff(role: Role | undefined): boolean {
  return role !== undefined && role !== "farmer";
}
