import { useCallback, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Alert, Breadcrumbs, Button, Spinner, Text } from "@ansavva/design-system";

import { FileRow } from "../components/browse/FileRow";
import { FolderCard } from "../components/browse/FolderCard";
import { MediaTile } from "../components/browse/MediaTile";
import { CopyKeyButton } from "../components/common/CopyKeyButton";
import { CodeViewer } from "../components/text/CodeViewer";
import { Lightbox } from "../components/viewer/Lightbox";
import { ReelView } from "../components/viewer/ReelView";
import { useAuth } from "../context/AuthContext";
import { useReel } from "../hooks/useReel";
import { useTree } from "../hooks/useTree";
import type { FileEntry } from "../types";

const ROOT_PREFIX = "media/";

export function BrowsePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { email, logout } = useAuth();

  const prefix = params.get("prefix") ?? ROOT_PREFIX;
  const { data, loading, error } = useTree(prefix);

  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [textFile, setTextFile] = useState<FileEntry | null>(null);
  const [reelOpen, setReelOpen] = useState(false);

  // Reel mode walks recursively from wherever you are, so a folder of only
  // subfolders — `media/mr-p/` — still opens onto real media. It is fetched
  // lazily: the pages cost nothing until the reel is actually opened.
  const reel = useReel(prefix, reelOpen);

  const media = useMemo(
    () => (data?.files ?? []).filter((file) => file.kind === "image" || file.kind === "video"),
    [data],
  );
  const others = useMemo(
    () => (data?.files ?? []).filter((file) => file.kind !== "image" && file.kind !== "video"),
    [data],
  );

  const goTo = useCallback(
    (nextPrefix: string) => {
      setLightboxIndex(null);
      setTextFile(null);
      setReelOpen(false);
      setParams(nextPrefix === ROOT_PREFIX ? {} : { prefix: nextPrefix });
    },
    [setParams],
  );

  const openFile = useCallback(
    (file: FileEntry) => {
      if (file.kind === "text") {
        setTextFile(file);
        return;
      }
      const index = media.findIndex((item) => item.key === file.key);
      if (index >= 0) setLightboxIndex(index);
    },
    [media],
  );

  const isEmpty =
    !loading && !error && data && data.folders.length === 0 && data.files.length === 0;

  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Text variant="display">Studio</Text>
          <Text variant="caption" tone="muted">
            x-harness media library
          </Text>
        </div>

        <div className="flex items-center gap-2">
          {email && (
            <Text variant="caption" tone="muted" className="hidden sm:block">
              {email}
            </Text>
          )}
          <Button
            intent="ghost"
            size="sm"
            onClick={() => {
              void logout().then(() => navigate("/"));
            }}
          >
            Sign out
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Breadcrumbs.Root carries `w-full` of its own, so it needs a shrinking
            flex parent or it claims the row and wraps the button beneath it. */}
        <div className="min-w-0 flex-1">
          <Breadcrumbs.Root>
            {(data?.breadcrumbs ?? [{ name: "media", prefix: ROOT_PREFIX }]).map((crumb, index, all) => (
              <Breadcrumbs.Item
                key={crumb.prefix}
                current={index === all.length - 1}
                href={`?prefix=${encodeURIComponent(crumb.prefix)}`}
                onClick={(event: React.MouseEvent) => {
                  event.preventDefault();
                  goTo(crumb.prefix);
                }}
              >
                {crumb.name}
              </Breadcrumbs.Item>
            ))}
          </Breadcrumbs.Root>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {/* Clicking a folder navigates into it rather than opening an
              overlay, so this is that folder's "opened" copy affordance. */}
          <CopyKeyButton value={data?.prefix ?? prefix} noun="prefix" />

          <Button size="sm" onClick={() => setReelOpen(true)}>
            Play reel
          </Button>
        </div>
      </div>

      {loading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading folder" />
        </div>
      )}

      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not load this folder</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      {isEmpty && (
        <Text variant="body" tone="muted">
          This folder is empty.
        </Text>
      )}

      {data && data.folders.length > 0 && (
        <section className="flex flex-col gap-2">
          <Text variant="title">Folders</Text>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.folders.map((folder) => (
              <FolderCard
                key={folder.prefix}
                name={folder.name}
                prefix={folder.prefix}
                onOpen={() => goTo(folder.prefix)}
              />
            ))}
          </div>
        </section>
      )}

      {media.length > 0 && (
        <section className="flex flex-col gap-2">
          <Text variant="title">
            Media <span className="font-body text-sm text-muted">({media.length})</span>
          </Text>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {media.map((file, index) => (
              <MediaTile key={file.key} file={file} onOpen={() => setLightboxIndex(index)} />
            ))}
          </div>
        </section>
      )}

      {others.length > 0 && (
        <section className="flex flex-col gap-2">
          <Text variant="title">Files</Text>
          <div className="flex flex-col gap-2">
            {others.map((file) => (
              <FileRow key={file.key} file={file} onOpen={() => openFile(file)} />
            ))}
          </div>
        </section>
      )}

      {lightboxIndex !== null && media.length > 0 && (
        <Lightbox items={media} startIndex={lightboxIndex} onClose={() => setLightboxIndex(null)} />
      )}

      {textFile && <CodeViewer file={textFile} onClose={() => setTextFile(null)} />}

      {reelOpen && (
        <ReelView
          items={reel.items}
          loading={reel.loading}
          exhausted={reel.exhausted}
          startIndex={0}
          onLoadMore={reel.loadMore}
          onClose={() => setReelOpen(false)}
        />
      )}
    </div>
  );
}
