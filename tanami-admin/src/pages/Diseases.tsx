import { useState } from "react";

import { apiPage } from "../api/client";
import type { Disease } from "../api/types";
import { Empty, ErrorNotice, Loading, PageHead } from "../components/States";
import { formatDate } from "../lib/format";
import { CAUSE_LABEL } from "../lib/labels";
import { useLoad } from "../lib/useLoad";
import { DiseaseEditor } from "./DiseaseEditor";

export function Diseases() {
  const { data, error, loading, reload, setData } = useLoad(() => apiPage<Disease>("/admin/diseases"), "diseases");
  const [editing, setEditing] = useState<Disease | null>(null);
  const items = data?.data ?? [];

  function onSaved(updated: Disease) {
    setData((current) =>
      current ? { ...current, data: current.data.map((item) => (item.code === updated.code ? updated : item)) } : current,
    );
    setEditing(null);
  }

  return (
    <>
      <PageHead
        title="Basis penyakit"
        intro="Teks yang dibaca petani setelah deteksi: gejala, penyebab, dan cara menangani. Setiap perubahan ditandatangani atas nama penyunting dan tidak tertimpa saat aplikasi diperbarui."
      />
      {loading && !data ? <Loading /> : null}
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
      {data && items.length === 0 ? <Empty title="Basis penyakit masih kosong" /> : null}

      {items.length > 0 ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Penyakit</th>
                <th scope="col">Penyebab</th>
                <th scope="col">Di aplikasi</th>
                <th scope="col">Terakhir ditinjau</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.code}
                  className="is-clickable"
                  tabIndex={0}
                  onClick={() => setEditing(item)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setEditing(item);
                    }
                  }}
                >
                  <td>
                    <div className="cell-main">{item.name_id}</div>
                    {item.name_latin ? <div className="cell-sub latin">{item.name_latin}</div> : null}
                  </td>
                  <td>{CAUSE_LABEL[item.cause_category] ?? item.cause_category}</td>
                  <td>
                    <span className={item.is_active ? "mark mark-ok" : "mark mark-off"}>
                      {item.is_active ? "Tampil" : "Disembunyikan"}
                    </span>
                  </td>
                  <td>
                    <div>{item.reviewed_by ?? "Belum ditinjau"}</div>
                    {item.reviewed_at ? <div className="cell-sub">{formatDate(item.reviewed_at)}</div> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {editing ? <DiseaseEditor disease={editing} onClose={() => setEditing(null)} onSaved={onSaved} /> : null}
    </>
  );
}
