import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiPage, apiSend } from "../api/client";
import type { Page, Role, StaffUser } from "../api/types";
import { useMe } from "../auth/AuthContext";
import { ConfirmDialog } from "../components/Overlay";
import { Empty, ErrorNotice, Loading, PageHead } from "../components/States";
import { useToast } from "../components/Toast";
import { formatDate } from "../lib/format";
import { ROLE_DUTY, ROLE_LABEL } from "../lib/labels";
import { messageOf, useLoad } from "../lib/useLoad";

const ROLES: Role[] = ["farmer", "expert", "moderator", "admin"];

function useDebounced(value: string, delay = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

interface RoleChange {
  user: StaffUser;
  role: Role;
}

export function Users() {
  const me = useMe();
  const toast = useToast();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<Role | "all">("all");
  const [showDeleted, setShowDeleted] = useState(false);
  const [change, setChange] = useState<RoleChange | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const query = useDebounced(search);

  const params = { q: query, role: role === "all" ? undefined : role, include_deleted: showDeleted, limit: 25 };
  const { data, error, loading, reload, setData } = useLoad(
    () => apiPage<StaffUser>("/admin/users", params),
    JSON.stringify(params),
  );
  const items = data?.data ?? [];

  async function loadMore() {
    if (!data?.meta.next_cursor) return;
    setLoadingMore(true);
    try {
      const next = await apiPage<StaffUser>("/admin/users", { ...params, cursor: data.meta.next_cursor });
      setData((current): Page<StaffUser> | null =>
        current ? { data: [...current.data, ...next.data], meta: next.meta } : next,
      );
    } catch (reason) {
      toast.error(messageOf(reason));
    } finally {
      setLoadingMore(false);
    }
  }

  async function applyRole({ user, role: next }: RoleChange) {
    setBusy(true);
    try {
      const updated = await apiSend<StaffUser>("PATCH", `/admin/users/${user.id}/role`, { role: next });
      setData((current) =>
        current ? { ...current, data: current.data.map((item) => (item.id === updated.id ? updated : item)) } : current,
      );
      toast.show(`${updated.full_name} sekarang ${ROLE_LABEL[updated.role].toLowerCase()}.`);
      setChange(null);
    } catch (reason) {
      toast.error(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  const messageUser = (user: StaffUser) =>
    navigate(`/pengumuman?user=${user.id}&nama=${encodeURIComponent(user.full_name)}`);

  return (
    <>
      <PageHead
        title="Pengguna"
        intro="Semua akun Tanami. Ubah peran untuk mengangkat ahli yang sudah diverifikasi atau moderator yang ditunjuk."
      />

      <div className="toolbar">
        <input
          className="input"
          type="search"
          placeholder="Cari nama, username, atau email"
          aria-label="Cari pengguna"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <div className="segmented" role="group" aria-label="Saring berdasarkan peran">
          <button type="button" aria-pressed={role === "all"} onClick={() => setRole("all")}>
            Semua
          </button>
          {ROLES.map((item) => (
            <button key={item} type="button" aria-pressed={role === item} onClick={() => setRole(item)}>
              {ROLE_LABEL[item]}
            </button>
          ))}
        </div>
        <label className="check">
          <input type="checkbox" checked={showDeleted} onChange={(event) => setShowDeleted(event.target.checked)} />
          Sertakan akun yang dihapus
        </label>
      </div>

      {loading && !data ? <Loading /> : null}
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
      {data && items.length === 0 ? (
        <Empty title="Tidak ada akun yang cocok">Coba kata kunci lain atau hapus saringan peran.</Empty>
      ) : null}

      {items.length > 0 ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Nama</th>
                <th scope="col">Email</th>
                <th scope="col">Peran</th>
                <th scope="col">Data latih</th>
                <th scope="col">Bergabung</th>
                <th scope="col">
                  <span className="sr-only">Aksi</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((user) => {
                const isMe = user.id === me.id;
                const deleted = user.deleted_at !== null;
                return (
                  <tr key={user.id}>
                    <td>
                      <div className="cell-main">
                        {user.full_name}
                        {isMe ? <span className="tag you">Anda</span> : null}
                      </div>
                      <div className="cell-sub">@{user.username}</div>
                    </td>
                    <td>{user.email}</td>
                    <td>
                      {deleted ? (
                        <span className="mark mark-bad">Menunggu penghapusan</span>
                      ) : (
                        <select
                          className="select role-select"
                          aria-label={`Peran ${user.full_name}`}
                          value={user.role}
                          disabled={isMe}
                          title={isMe ? "Anda tidak dapat mengubah peran sendiri." : undefined}
                          onChange={(event) => setChange({ user, role: event.target.value as Role })}
                        >
                          {ROLES.map((item) => (
                            <option key={item} value={item}>
                              {ROLE_LABEL[item]}
                            </option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td>{user.consent_training_data ? "Diizinkan" : "Tidak"}</td>
                    <td className="num">{formatDate(user.created_at)}</td>
                    <td className="cell-right">
                      {!deleted ? (
                        <button type="button" className="btn btn-link" onClick={() => messageUser(user)}>
                          Kirim pesan
                        </button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {data?.meta.has_more ? (
            <div className="table-foot">
              <button type="button" className="btn btn-quiet" onClick={() => void loadMore()} disabled={loadingMore}>
                {loadingMore ? "Memuat..." : "Muat lebih banyak"}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog
        open={change !== null}
        title={change ? `Jadikan ${change.user.full_name} ${ROLE_LABEL[change.role].toLowerCase()}?` : ""}
        confirmLabel="Ubah peran"
        busy={busy}
        onCancel={() => setChange(null)}
        onConfirm={() => change && void applyRole(change)}
      >
        {change ? ROLE_DUTY[change.role] : ""} Perubahan berlaku pada permintaan berikutnya dari akun ini.
      </ConfirmDialog>
    </>
  );
}
