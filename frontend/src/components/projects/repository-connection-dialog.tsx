import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2 } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { ApiError } from "@/api/client";
import { updateProjectRepository } from "@/api/projects";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { detectGitProvider } from "@/lib/git-provider";
import type { GitProvider, Project } from "@/types/project";

interface RepositoryConnectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: Project;
}

function validateRepositoryUrl(value: string): string | null {
  if (!value) {
    return "URL repository wajib diisi.";
  }
  if (!value.startsWith("https://") && !value.startsWith("http://")) {
    return "URL harus diawali https:// atau http://.";
  }
  try {
    const parsed = new URL(value);
    if (!parsed.hostname) {
      return "URL repository tidak valid.";
    }
  } catch {
    return "URL repository tidak valid.";
  }
  return null;
}

function validateBranch(value: string): string | null {
  if (!value) {
    return "Branch default wajib diisi.";
  }
  if (/\s/.test(value)) {
    return "Branch tidak boleh mengandung spasi.";
  }
  if (value.length > 100) {
    return "Branch maksimal 100 karakter.";
  }
  return null;
}

export function RepositoryConnectionDialog({
  open,
  onOpenChange,
  project,
}: RepositoryConnectionDialogProps) {
  const queryClient = useQueryClient();
  const [repositoryUrl, setRepositoryUrl] = useState(project.repository_url ?? "");
  const [defaultBranch, setDefaultBranch] = useState(
    project.default_branch ?? "main",
  );
  const [provider, setProvider] = useState<GitProvider>(
    project.provider ?? detectGitProvider(project.repository_url) ?? "github",
  );
  const [providerTouched, setProviderTouched] = useState(false);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const repositoryError = validateRepositoryUrl(repositoryUrl.trim());
  const branchError = validateBranch(defaultBranch.trim());
  const isValid = !repositoryError && !branchError;

  const saveMutation = useMutation({
    mutationFn: () =>
      updateProjectRepository(project.id, {
        repository_url: repositoryUrl.trim(),
        default_branch: defaultBranch.trim(),
        provider,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["project", project.id] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      onOpenChange(false);
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : "Gagal menyimpan koneksi repository.",
      );
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    if (!isValid || saveMutation.isPending) {
      return;
    }
    setError(null);
    saveMutation.mutate();
  }

  function handleRepositoryChange(value: string) {
    setRepositoryUrl(value);
    if (!providerTouched) {
      const detected = detectGitProvider(value.trim());
      if (detected) {
        setProvider(detected);
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="repository-connection-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="size-4" />
            {project.repository_url ? "Ubah koneksi repository" : "Hubungkan repository"}
          </DialogTitle>
          <DialogDescription>
            Simpan URL repository dan branch default project. Data ini dipakai untuk
            tautan pengaturan webhook dan konteks integrasi Git.
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="repository-provider">Provider</Label>
            <Select
              value={provider}
              onValueChange={(value) => {
                setProvider(value as GitProvider);
                setProviderTouched(true);
              }}
            >
              <SelectTrigger
                id="repository-provider"
                data-testid="repository-provider"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="github">GitHub</SelectItem>
                <SelectItem value="gitlab">GitLab</SelectItem>
                <SelectItem value="bitbucket">Bitbucket</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="repository-url">URL repository</Label>
            <Input
              id="repository-url"
              data-testid="repository-url"
              value={repositoryUrl}
              onChange={(event) => handleRepositoryChange(event.target.value)}
              placeholder="https://github.com/org/repo"
              className="font-mono"
              autoComplete="off"
            />
            {touched && repositoryError ? (
              <p className="text-xs text-destructive" data-testid="repository-url-error">
                {repositoryError}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Gunakan URL clone HTTPS, misal https://github.com/org/repo.git.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="repository-default-branch">Branch default</Label>
            <Input
              id="repository-default-branch"
              data-testid="repository-default-branch"
              value={defaultBranch}
              onChange={(event) => setDefaultBranch(event.target.value)}
              placeholder="main"
              className="font-mono"
              maxLength={100}
              autoComplete="off"
            />
            {touched && branchError ? (
              <p className="text-xs text-destructive">{branchError}</p>
            ) : null}
          </div>

          <p className="rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            Filter branch deploy diatur per aplikasi. Koneksi project tidak mengubah
            branch aplikasi yang sudah ada.
          </p>

          {error ? (
            <p className="text-sm text-destructive" data-testid="repository-connection-error">
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
              data-testid="repository-connection-save"
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? "Menyimpan…" : "Simpan koneksi"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
