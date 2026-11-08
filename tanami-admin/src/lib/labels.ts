import type { Role } from "../api/types";

// Copies of the backend's display labels (app/domain.py). They only decorate
// codes the API already returns; the API stays the source of truth.

export const ROLE_LABEL: Record<Role, string> = {
  farmer: "Petani",
  expert: "Ahli",
  moderator: "Moderator",
  admin: "Admin",
};

export const ROLE_DUTY: Record<Role, string> = {
  farmer: "Memakai aplikasi Tanami tanpa akses ke ruang kerja tim.",
  expert: "Meninjau hasil deteksi yang ditandai salah dan menyunting basis penyakit.",
  moderator: "Memutuskan laporan forum: menampilkan lagi, menyembunyikan, atau menghapus.",
  admin: "Akses penuh, termasuk mengubah peran dan mengirim pengumuman.",
};

export const LABEL_NAME: Record<string, string> = {
  healthy: "Sehat",
  anthracnose: "Antraknosa",
  cercospora_leaf_spot: "Bercak daun cercospora",
  bacterial_wilt: "Layu bakteri",
  leaf_curl_virus: "Keriting daun (virus)",
  pest_damage: "Kerusakan akibat hama",
  nutrient_deficiency: "Kekurangan hara",
  unripe: "Mentah",
  turning: "Mengkal",
  ripe: "Matang",
  overripe: "Terlalu matang",
};

export function labelName(code: string | null | undefined): string {
  if (!code) return "Tidak dikenali";
  return LABEL_NAME[code] ?? code;
}

export const CAUSE_LABEL: Record<string, string> = {
  healthy: "Sehat",
  fungus: "Jamur",
  bacteria: "Bakteri",
  virus: "Virus",
  pest: "Hama",
  nutrient_deficiency: "Kekurangan hara",
  unknown: "Belum diketahui",
};

export const STATUS_LABEL: Record<string, string> = {
  confident: "Yakin",
  uncertain: "Ragu-ragu",
  unknown: "Tidak dikenali",
  invalid_image: "Foto tidak layak",
};

export const REASON_LABEL: Record<string, string> = {
  spam: "Spam",
  scam: "Penipuan",
  abuse: "Kata-kata kasar",
  wrong_info: "Informasi salah",
  other: "Lainnya",
};

export const OUTCOME_LABEL: Record<string, string> = {
  failed: "Gagal panen",
  suboptimal: "Kurang optimal",
  normal: "Sesuai target",
  bumper: "Panen raya",
};
