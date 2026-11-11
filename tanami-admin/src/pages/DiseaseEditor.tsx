import { useState } from "react";

import { ApiError, apiSend } from "../api/client";
import type { Disease, TreatmentStep, Treatments } from "../api/types";
import { useMe } from "../auth/AuthContext";
import { IconClose, IconPlus } from "../components/Icons";
import { Drawer } from "../components/Overlay";
import { useToast } from "../components/Toast";
import { CAUSE_LABEL } from "../lib/labels";

const NEWLINE = String.fromCharCode(10);

interface Draft {
  name_id: string;
  name_latin: string;
  symptoms: string;
  causes_text: string;
  prevention: string;
  severity_note: string;
  is_active: boolean;
  treatments: Treatments;
}

function toDraft(disease: Disease): Draft {
  const t = disease.treatments;
  return {
    name_id: disease.name_id,
    name_latin: disease.name_latin ?? "",
    symptoms: disease.symptoms,
    causes_text: disease.causes_text,
    prevention: disease.prevention,
    severity_note: disease.severity_note ?? "",
    is_active: disease.is_active,
    treatments: {
      first_aid: t.first_aid ?? [],
      organic: t.organic ?? [],
      chemical: t.chemical ?? [],
      safety_note: t.safety_note ?? "",
      when_to_call_expert: t.when_to_call_expert ?? "",
    },
  };
}

interface TextProps {
  id: string;
  label: string;
  hint?: string;
  value: string;
  error?: string | null;
  rows?: number;
  onChange: (value: string) => void;
}

function Text({ id, label, hint, value, error, rows = 4, onChange }: TextProps) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      {hint ? <span className="field-hint">{hint}</span> : null}
      <textarea
        id={id}
        className="textarea"
        rows={rows}
        value={value}
        aria-invalid={error ? true : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {error ? <span className="field-error">{error}</span> : null}
    </div>
  );
}

interface StepsProps {
  title: string;
  hint?: string;
  steps: TreatmentStep[];
  onChange: (steps: TreatmentStep[]) => void;
}

function Steps({ title, hint, steps, onChange }: StepsProps) {
  const update = (index: number, patch: Partial<TreatmentStep>) =>
    onChange(steps.map((step, i) => (i === index ? { ...step, ...patch } : step)));
  return (
    <fieldset className="steps">
      <legend className="field-label">{title}</legend>
      {hint ? <p className="field-hint">{hint}</p> : null}
      {steps.map((step, index) => (
        <div key={index} className="step">
          <input
            className="input"
            aria-label={`${title}, judul langkah ${index + 1}`}
            placeholder="Judul langkah"
            value={step.title}
            onChange={(event) => update(index, { title: event.target.value })}
          />
          <textarea
            className="textarea"
            rows={2}
            aria-label={`${title}, cara langkah ${index + 1}`}
            placeholder="Cara melakukannya"
            value={step.how}
            onChange={(event) => update(index, { how: event.target.value })}
          />
          <button
            type="button"
            className="icon-button step-remove"
            aria-label={`Hapus langkah ${index + 1}`}
            onClick={() => onChange(steps.filter((_, i) => i !== index))}
          >
            <IconClose />
          </button>
        </div>
      ))}
      <button
        type="button"
        className="btn btn-link step-add"
        onClick={() => onChange([...steps, { title: "", how: "" }])}
      >
        <IconPlus /> Tambah langkah
      </button>
    </fieldset>
  );
}

interface EditorProps {
  disease: Disease;
  onClose: () => void;
  onSaved: (updated: Disease) => void;
}

export function DiseaseEditor({ disease, onClose, onSaved }: EditorProps) {
  const me = useMe();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => toDraft(disease));
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<{ field: string | null; message: string } | null>(null);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const setT = <K extends keyof Treatments>(key: K, value: Treatments[K]) =>
    setDraft((current) => ({ ...current, treatments: { ...current.treatments, [key]: value } }));
  const errorFor = (field: string) => (problem?.field === field ? problem.message : null);
  const inlineFields = ["symptoms", "treatments.safety_note", "treatments.when_to_call_expert"];

  async function save() {
    setSaving(true);
    setProblem(null);
    const clean = (steps: TreatmentStep[]) =>
      steps.map((s) => ({ title: s.title.trim(), how: s.how.trim() })).filter((s) => s.title || s.how);
    try {
      const updated = await apiSend<Disease>("PATCH", `/admin/diseases/${disease.code}`, {
        name_id: draft.name_id.trim(),
        name_latin: draft.name_latin.trim() || null,
        symptoms: draft.symptoms.trim(),
        causes_text: draft.causes_text.trim(),
        prevention: draft.prevention.trim(),
        severity_note: draft.severity_note.trim() || null,
        is_active: draft.is_active,
        treatments: {
          first_aid: draft.treatments.first_aid.map((line) => line.trim()).filter(Boolean),
          organic: clean(draft.treatments.organic),
          chemical: clean(draft.treatments.chemical),
          safety_note: draft.treatments.safety_note.trim(),
          when_to_call_expert: draft.treatments.when_to_call_expert.trim(),
        },
      });
      toast.show(`${updated.name_id} disimpan atas nama ${me.full_name}.`);
      onSaved(updated);
    } catch (reason) {
      if (reason instanceof ApiError) setProblem({ field: reason.field, message: reason.message });
      else setProblem({ field: null, message: "Perubahan gagal disimpan. Coba lagi." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open
      onClose={onClose}
      title={disease.name_id}
      subtitle={`${CAUSE_LABEL[disease.cause_category] ?? disease.cause_category}, kode ${disease.code}`}
      footer={
        <>
          <span className="field-hint">Disimpan atas nama {me.full_name} dengan tanggal hari ini.</span>
          <div className="drawer-actions">
            <button type="button" className="btn btn-quiet" onClick={onClose} disabled={saving}>
              Batal
            </button>
            <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={saving}>
              {saving ? "Menyimpan..." : "Simpan perubahan"}
            </button>
          </div>
        </>
      }
    >
      <div className="editor">
        {problem && !inlineFields.includes(problem.field ?? "") ? (
          <p className="notice" role="alert">
            {problem.message}
          </p>
        ) : null}

        <label className="check">
          <input
            type="checkbox"
            checked={draft.is_active}
            onChange={(event) => set("is_active", event.target.checked)}
          />
          Tampilkan penyakit ini di aplikasi petani
        </label>

        <div className="editor-row">
          <div className="field">
            <label className="field-label" htmlFor="name_id">
              Nama
            </label>
            <input
              id="name_id"
              className="input"
              value={draft.name_id}
              onChange={(event) => set("name_id", event.target.value)}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="name_latin">
              Nama latin
            </label>
            <input
              id="name_latin"
              className="input latin"
              value={draft.name_latin}
              onChange={(event) => set("name_latin", event.target.value)}
            />
          </div>
        </div>

        <Text
          id="symptoms"
          label="Gejala"
          value={draft.symptoms}
          error={errorFor("symptoms")}
          onChange={(v) => set("symptoms", v)}
        />
        <Text id="causes_text" label="Penyebab" value={draft.causes_text} onChange={(v) => set("causes_text", v)} />
        <Text id="prevention" label="Pencegahan" value={draft.prevention} onChange={(v) => set("prevention", v)} />
        <Text
          id="severity_note"
          label="Catatan tingkat keparahan"
          rows={2}
          value={draft.severity_note}
          onChange={(v) => set("severity_note", v)}
        />

        <h3 className="editor-section">Penanganan</h3>
        <Text
          id="first_aid"
          label="Pertolongan pertama"
          hint="Satu langkah per baris. Tampil paling atas di hasil deteksi."
          rows={3}
          value={draft.treatments.first_aid.join(NEWLINE)}
          onChange={(v) => setT("first_aid", v.split(NEWLINE))}
        />
        <Steps title="Penanganan organik" steps={draft.treatments.organic} onChange={(s) => setT("organic", s)} />
        <Steps
          title="Penanganan kimia"
          hint="Sebutkan golongan bahan aktif tanpa dosis. Petani diarahkan membaca label kemasan."
          steps={draft.treatments.chemical}
          onChange={(s) => setT("chemical", s)}
        />
        <Text
          id="safety_note"
          label="Catatan keselamatan"
          hint="Wajib diisi bila ada penanganan kimia."
          rows={2}
          value={draft.treatments.safety_note}
          error={errorFor("treatments.safety_note")}
          onChange={(v) => setT("safety_note", v)}
        />
        <Text
          id="when_to_call_expert"
          label="Kapan menghubungi penyuluh"
          rows={2}
          value={draft.treatments.when_to_call_expert}
          error={errorFor("treatments.when_to_call_expert")}
          onChange={(v) => setT("when_to_call_expert", v)}
        />
      </div>
    </Drawer>
  );
}
