import { useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Plus, X } from "lucide-react";
import { useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

import { ApiError } from "@/api/client";
import { updateApplication } from "@/api/projects";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Application } from "@/types/project";

const MAX_BRANCHES = 20;

interface ApplicationBranchesDialogProps {
  application: Application | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function normalizeBranch(value: string): string {
  return value.trim().replace(/^refs\/heads\//, "");
}

export function ApplicationBranchesDialog({
  application,
  open,
  onOpenChange,
}: ApplicationBranchesDialogProps) {
  const queryClient = useQueryClient();
  const [branches, setBranches] = useState<string[]>(() =>
    application && application.webhook_branches?.length > 0
      ? application.webhook_branches
      : application
        ? [application.branch]
        : [],
  );
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: (nextBranches: string[]) =>
      updateApplication(application!.id, { webhook_branches: nextBranches }),
    onSuccess: (_updated, nextBranches) => {
      if (application) {
        queryClient.setQueryData<Application[]>(
          ["project-applications", application.project_id],
          (current) =>
            current?.map((item) =>
              item.id === application.id
                ? { ...item, webhook_branches: nextBranches }
                : item,
            ),
        );
        void queryClient.invalidateQueries({
          queryKey: ["project-applications", application.project_id],
        });
      }
      void queryClient.invalidateQueries({ queryKey: ["applications"] });
      onOpenChange(false);
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : "Gagal menyimpan filter branch.",
      );
    },
  });

  function addBranch() {
    if (!application || saveMutation.isPending) {
      return;
    }
    const normalized = normalizeBranch(draft);
    if (!normalized) {
      setDraftError("Branch wajib diisi.");
      return;
    }
    if (/\s/.test(normalized)) {
      setDraftError("Branch tidak boleh mengandung spasi.");
      return;
    }
    if (normalized.length > 100) {
      setDraftError("Branch maksimal 100 karakter.");
      return;
    }
    if (branches.includes(normalized)) {
      setDraftError("Branch sudah ada di daftar.");
      return;
    }
    if (branches.length >= MAX_BRANCHES) {
      setDraftError(`Maksimal ${MAX_BRANCHES} branch per aplikasi.`);
      return;
    }
    setBranches([...branches, normalized]);
    setDraft("");
    setDraftError(null);
    setError(null);
  }

  function removeBranch(branch: string) {
    setBranches((current) => current.filter((item) => item !== branch));
    setDraftError(null);
    setError(null);
  }

  function handleDraftKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    addBranch();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!application || saveMutation.isPending) {
      return;
    }
    if (branches.length === 0) {
      setError("Minimal satu branch harus aktif.");
      return;
    }
    setError(null);
    saveMutation.mutate(branches);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="application-branches-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitBranch className="size-4" />
            Filter branch webhook
          </DialogTitle>
          <DialogDescription>
            {application
              ? `Push ke branch berikut akan men-deploy ${application.name}. Nama branch harus sama persis (case-sensitive).`
              : "Atur branch yang memicu deployment lewat webhook."}
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label>Branch yang memicu deploy</Label>
            <div
              className="flex flex-wrap gap-2 rounded-lg border bg-muted/20 p-2"
              data-testid="application-branch-list"
            >
              {branches.length === 0 ? (
                <p className="px-1 py-0.5 text-xs text-muted-foreground">
                  Belum ada branch. Tambahkan minimal satu.
                </p>
              ) : (
                branches.map((branch) => (
                  <Badge key={branch} variant="secondary" className="gap-1 pl-2.5">
                    <span className="font-mono">{branch}</span>
                    <button
                      type="button"
                      onClick={() => removeBranch(branch)}
                      className="rounded-full p-0.5 opacity-60 transition-opacity hover:bg-foreground/10 hover:opacity-100"
                      aria-label={`Hapus branch ${branch}`}
                      disabled={saveMutation.isPending}
                    >
                      <X className="size-3" />
                    </button>
                  </Badge>
                ))
              )}
            </div>
            <div className="flex gap-2">
              <Input
                data-testid="application-branch-input"
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setDraftError(null);
                }}
                onKeyDown={handleDraftKeyDown}
                placeholder="misal main atau release"
                className="font-mono"
                maxLength={100}
                autoComplete="off"
                disabled={saveMutation.isPending || branches.length >= MAX_BRANCHES}
              />
              <Button
                type="button"
                variant="outline"
                onClick={addBranch}
                data-testid="application-branch-add"
                disabled={saveMutation.isPending || branches.length >= MAX_BRANCHES}
              >
                <Plus />
                Tambah
              </Button>
            </div>
            {draftError ? (
              <p className="text-xs text-destructive" data-testid="application-branch-error">
                {draftError}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Maksimal {MAX_BRANCHES} branch. Branch deploy default:{" "}
                <code className="font-mono text-foreground">
                  {application?.branch ?? "-"}
                </code>
                .
              </p>
            )}
            {application && !branches.includes(application.branch) ? (
              <Button
                type="button"
                variant="link"
                size="sm"
                className="h-auto px-0"
                onClick={() => {
                  if (branches.length >= MAX_BRANCHES) {
                    setDraftError(`Maksimal ${MAX_BRANCHES} branch per aplikasi.`);
                    return;
                  }
                  setBranches([...branches, application.branch]);
                  setDraftError(null);
                }}
                disabled={saveMutation.isPending}
              >
                Gunakan branch deploy {application.branch}
              </Button>
            ) : null}
          </div>

          <p className="rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            Mode deployment manual tetap memakai branch default aplikasi. Filter ini
            hanya berlaku untuk webhook provider.
          </p>

          {error ? (
            <p className="text-sm text-destructive" data-testid="application-branches-error">
              {error}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={saveMutation.isPending}
            >
              Batal
            </Button>
            <Button
              type="submit"
              data-testid="application-branches-save"
              disabled={saveMutation.isPending || branches.length === 0}
            >
              {saveMutation.isPending ? "Menyimpan…" : "Simpan filter"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
