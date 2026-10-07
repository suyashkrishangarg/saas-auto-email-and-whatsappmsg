"use client";

import { ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { useCallback, useMemo, useState } from "react";
import { api, BulkResult, checkGstin, checkPhone, ClientRow } from "@/lib/api";

type DraftRow = {
  key: string;
  consultantPhone: string;
  name: string;
  phone: string;
  gstin: string;
  sourceId?: string;
};

const HEADERS = [
  "consultant phone number",
  "client name",
  "client whatsapp number",
  "client gstin",
];

let seq = 0;
const newRow = (): DraftRow => ({
  key: `r${++seq}`,
  consultantPhone: "",
  name: "",
  phone: "",
  gstin: "",
});

function cellError(colIdx: number, row: DraftRow): string | null {
  if (colIdx === 0) return checkPhone(row.consultantPhone);
  if (colIdx === 1) return row.name.trim() ? null : "Name required";
  if (colIdx === 2) return checkPhone(row.phone);
  if (colIdx === 3) return row.gstin ? checkGstin(row.gstin) : "GSTIN required";
  return null;
}

export default function ClientGrid({ initial }: { initial: ClientRow[] }) {
  const [rows, setRows] = useState<DraftRow[]>(() =>
    initial.map((c) => ({
      key: `s${c.id}`,
      consultantPhone: "",
      name: c.name,
      phone: c.phone ?? "",
      gstin: c.gstin,
      sourceId: c.id,
    }))
  );
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<BulkResult | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const setCell = useCallback((rowIdx: number, field: keyof DraftRow, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === rowIdx ? { ...r, [field]: value } : r)));
    setDirty(true);
  }, []);

  /** Multi-row paste from Excel/Sheets: parse TSV, append parsed rows. */
  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLDivElement>) => {
    const text = e.clipboardData.getData("text/plain");
    if (!text || (!text.includes("\t") && !text.includes("\n"))) return;
    e.preventDefault();
    const lines = text.split("\n").map((l) => (l.endsWith("\r") ? l.slice(0, -1) : l)).filter((l) => l.trim().length > 0);
    const parsed: DraftRow[] = [];
    for (let i = 0; i < lines.length; i++) {
      const cols = lines[i].split("\t").map((c) => c.trim());
      if (
        i === 0 &&
        cols.length >= 4 &&
        HEADERS.some((h) => cols.join(" ").toLowerCase().includes(h))
      ) {
        continue;
      }
      parsed.push({
        key: `p${++seq}`,
        consultantPhone: cols[0] ?? "",
        name: cols[1] ?? "",
        phone: cols[2] ?? "",
        gstin: (cols[3] ?? "").toUpperCase(),
      });
    }
    if (parsed.length) {
      setRows((prev) => [...prev, ...parsed]);
      setDirty(true);
      setBanner(`Pasted ${parsed.length} row(s) from clipboard. Review, then Save All.`);
      setTimeout(() => setBanner(null), 4000);
    }
  }, []);

  const columns = useMemo<ColumnDef<DraftRow>[]>(
    () => [
      {
        id: "consultantPhone",
        header: "Consultant Phone Number",
        cell: ({ row }) => (
          <CellInput rowIdx={row.index} colIdx={0} row={row.original} field="consultantPhone" onChange={setCell} />
        ),
      },
      {
        id: "name",
        header: "Client Name",
        cell: ({ row }) => (
          <CellInput rowIdx={row.index} colIdx={1} row={row.original} field="name" onChange={setCell} />
        ),
      },
      {
        id: "phone",
        header: "Client WhatsApp Number",
        cell: ({ row }) => (
          <CellInput rowIdx={row.index} colIdx={2} row={row.original} field="phone" onChange={setCell} />
        ),
      },
      {
        id: "gstin",
        header: "Client GSTIN",
        cell: ({ row }) => (
          <CellInput rowIdx={row.index} colIdx={3} row={row.original} field="gstin" onChange={setCell} />
        ),
      },
    ],
    [setCell]
  );

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  const saveAll = async () => {
    setSaving(true);
    setResult(null);
    try {
      const payload = rows
        .filter((r) => r.name.trim() || r.gstin.trim())
        .map((r) => ({
          consultant_phone: r.consultantPhone || null,
          client_name: r.name.trim() || "Unnamed",
          client_phone: r.phone || null,
          client_gstin: r.gstin.trim().toUpperCase(),
        }));
      if (!payload.length) {
        setBanner("Nothing to save yet - paste rows or fill cells first.");
        return;
      }
      const res = await api<BulkResult>("/clients/bulk", {
        method: "POST",
        json: { rows: payload },
      });
      setResult(res);
      setDirty(false);
      setBanner(
        `Saved: ${res.created} new, ${res.updated} updated` +
          (res.errors.length ? `, ${res.errors.length} row error(s)` : "")
      );
    } catch (err) {
      setBanner(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
      setTimeout(() => setBanner(null), 6000);
    }
  };

  const addRow = () => {
    setRows((prev) => [...prev, newRow()]);
    setDirty(true);
  };

  return (
    <div onPaste={handlePaste}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm text-slate-500">
          Paste directly from Excel / Google Sheets (multi-row) inside the grid. Draft
          changes save together on <b>Save All</b>.
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={addRow}>+ Row</button>
          <button className="btn-primary" onClick={saveAll} disabled={saving}>
            {saving ? "Saving…" : "Save All"}
          </button>
        </div>
      </div>

      {banner && (
        <div className="mb-3 rounded-md border border-brand-100 bg-brand-50 px-3 py-2 text-sm text-brand-700">
          {banner}
        </div>
      )}
      {result && result.errors.length > 0 && (
        <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm">
          <p className="font-medium text-amber-800">Rows not saved:</p>
          <ul className="mt-1 list-inside list-disc text-amber-700">
            {result.errors.map((e) => (
              <li key={e.row}>
                Row {e.row} ({e.gstin || "no GSTIN"}): {e.error}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full min-w-[820px] border-collapse">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id} className="th">
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="hover:bg-slate-50/60">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="td p-0">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={4} className="td py-8 text-center text-slate-400">
                  No rows yet. Add a row or paste from Excel.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {dirty && <p className="mt-2 text-xs text-amber-600">Unsaved draft changes</p>}
    </div>
  );
}

function CellInput({
  rowIdx, colIdx, row, field, onChange,
}: {
  rowIdx: number;
  colIdx: number;
  row: DraftRow;
  field: keyof DraftRow;
  onChange: (i: number, f: keyof DraftRow, v: string) => void;
}) {
  const value = row[field] as string;
  const err = cellError(colIdx, row);
  const showError = value.trim().length > 0 && err !== null;
  return (
    <input
      className={
        "w-full border-0 bg-transparent px-3 py-2 text-sm outline-none focus:bg-brand-50 " +
        (showError ? "bg-red-50" : "")
      }
      value={value}
      title={showError ? (err ?? undefined) : undefined}
      onChange={(e) => onChange(rowIdx, field, e.target.value)}
      style={showError ? { boxShadow: "inset 0 0 0 1px #fca5a5" } : undefined}
    />
  );
}
