import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, FileUp } from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { bulkUpsertEnvVars, fetchEnvVars } from "@/api/projects";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { parseDotEnv, type ParsedDotEnv } from "@/lib/env-parser";

interface EnvBulkImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: number;
}

function maskPreview(value: string): string {
  if (value.length <= 2) {
    return "****";
  }
  return `${value.slice(0, 3)}****`;
}

export function EnvBulkImportDialog({
  open,
  onOpenChange,
  projectId,
}: EnvBulkImportDialogProps) {
  const queryClient = useQueryClient();

  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<ParsedDotEnv | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<{ created: number; updated: number } | null>(null);

  const envQuery = useQuery({
    queryKey: ["env-vars", projectId],
    queryFn: () => fetchEnvVars(projectId),
    enabled: open,
    retry: 1,
  });

  const existingKeys = useMemo(
    () => new Set((envQuery.data?.env_vars ?? []).map((item) => item.key)),
    [envQuery.data],
  );

  const importMutation = useMutation({
    mutationFn: (entries: { key: string; value: string }[]) =>
      bulkUpsertEnvVars(projectId, entries),
    onSuccess: (response) => {
      setResult({ created: response.summary.created, updated: response.summary.updated });
      setParsed(null);
      setText("");
      void queryClient.invalidateQueries({ queryKey: ["env-vars", projectId] });
    },
    onError: (error) => {
      setErrorMessage(
        error instanceof ApiError ? error.message : "Gagal menyimpan environment variable.",
      );
    },
  });

  function reset() {
    setText("");
    setParsed(null);
    setErrorMessage(null);
    setResult(null);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) {
          reset();
        }
      }}
    >
      <DialogContent className="sm:max-w-2xl" data-testid="env-bulk-import-dialog">
        <DialogHeader>
          <DialogTitle>Bulk import .env</DialogTitle>
          <DialogDescription>
            Tempel isi file <code className="font-mono">.env</code> — komentar dan baris tidak
            valid akan dilewati. Key yang sudah ada diperbarui, bukan dihapus.
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div
            className="flex flex-col items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-6 text-center"
            data-testid="bulk-import-result"
          >
            <CircleCheck className="size-6 text-emerald-500" />
            <p className="text-sm font-medium">
              {result.created} variabel baru, {result.updated} diperbarui
            </p>
            <p className="text-xs text-muted-foreground">
              Nilai baru terpasang setelah aplikasi di-deploy ulang.
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <label htmlFor="bulk-env-text" className="text-sm font-medium">
                Isi file .env
              </label>
              <Textarea
                id="bulk-env-text"
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={8}
                placeholder={"DATABASE_URL=postgres://user:pass@host/db\nAPI_TOKEN=abc123\n# komentar diabaikan"}
                className="font-mono text-xs"
                data-testid="bulk-import-textarea"
              />
            </div>

            {parsed ? (
              <div className="space-y-3">
                <div className="overflow-x-auto">
                  <Table data-testid="bulk-import-preview">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Key</TableHead>
                        <TableHead>Nilai</TableHead>
                        <TableHead>Aksi</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {parsed.entries.map((entry) => (
                        <TableRow key={entry.key} data-testid="bulk-import-row">
                          <TableCell className="font-mono text-xs">{entry.key}</TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">
                            {maskPreview(entry.value)}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={
                                existingKeys.has(entry.key)
                                  ? "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                                  : "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                              }
                            >
                              {existingKeys.has(entry.key) ? "Update" : "Baru"}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {parsed.skipped.length > 0 ? (
                  <div className="space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                    <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
                      {parsed.skipped.length} baris dilewati
                    </p>
                    <ul className="space-y-0.5 text-xs text-amber-700/90 dark:text-amber-400/90">
                      {parsed.skipped.map((item) => (
                        <li key={`${item.lineNumber}-${item.reason}`}>
                          Baris {item.lineNumber}: {item.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}

            {errorMessage ? (
              <p className="text-sm text-destructive" data-testid="bulk-import-error">
                {errorMessage}
              </p>
            ) : null}
          </>
        )}

        <DialogFooter>
          {result ? (
            <Button type="button" onClick={() => onOpenChange(false)} data-testid="bulk-import-close">
              Tutup
            </Button>
          ) : (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={() => setParsed(null)}
                disabled={!parsed || importMutation.isPending}
              >
                Reset preview
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setParsed(parseDotEnv(text))}
                disabled={!text.trim()}
                data-testid="bulk-import-parse"
              >
                <FileUp />
                Parse
              </Button>
              <Button
                type="button"
                onClick={() => {
                  if (parsed) {
                    setErrorMessage(null);
                    importMutation.mutate(parsed.entries);
                  }
                }}
                disabled={!parsed || parsed.entries.length === 0 || importMutation.isPending}
                data-testid="bulk-import-submit"
              >
                {importMutation.isPending
                  ? "Menyimpan…"
                  : `Simpan ${parsed?.entries.length ?? 0} variabel`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
