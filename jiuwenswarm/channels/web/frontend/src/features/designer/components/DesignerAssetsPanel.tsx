import { FileText, Headphones, Image as ImageIcon, Trash2, Video } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useDesignerAssetLibraryStore,
  type DesignerAssetKind,
  type DesignerAssetSource,
} from '../designerAssetLibraryStore';
import { collectDesignerMaterials, isDesignerFallbackTextAsset, type DesignerMaterial } from '../designerMaterials';
import { DESIGNER_ASSET_DRAG_MIME, DESIGNER_PROJECT_ASSET_DRAG_MIME } from '../designerCanvasNodes';
import { designerAssetPreviewUrl } from '../designerAssetUrl';
import { designerWorkspaceClient, type DesignerProjectAsset } from '../designerGraphClient';
import { useDesignerRunStore } from '../designerRunStore';
import { useDesignerStore } from '../designerStore';
import { useDesignerUiStore } from '../designerUiStore';

type UnifiedAsset = {
  id: string;
  filename: string;
  kind: DesignerAssetKind;
  source: DesignerAssetSource;
  previewUrl: string | null;
  sizeLabel: string;
  onCanvas: boolean;
  /** Library-only assets can be deleted from the session library. */
  deletable: boolean;
  materialId?: string;
  nodeId?: string;
  sharedUri?: string;
  sharedMime?: string;
};

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function kindFromMaterial(material: DesignerMaterial): DesignerAssetKind {
  if (
    isDesignerFallbackTextAsset({
      kind: material.kind,
      uri: material.uri,
      mime_type: material.mimeType,
      label: material.label,
    })
  ) {
    return 'other';
  }
  if (material.kind === 'video' || (material.mimeType || '').startsWith('video/')) return 'video';
  if (material.kind === 'audio' || (material.mimeType || '').startsWith('audio/')) return 'audio';
  if (material.kind === 'image' || (material.mimeType || '').startsWith('image/')) return 'image';
  return 'other';
}

function AssetKindIcon({ kind }: { kind: DesignerAssetKind }) {
  if (kind === 'video') return <Video size={18} aria-hidden />;
  if (kind === 'audio') return <Headphones size={18} aria-hidden />;
  if (kind === 'other') return <FileText size={18} aria-hidden />;
  return <ImageIcon size={18} aria-hidden />;
}

function isUploadedMaterial(material: DesignerMaterial): boolean {
  return material.uri.startsWith('blob:');
}

type ListedSessionFile = {
  name: string;
  path: string;
};

function kindFromFilename(filename: string): DesignerAssetKind | null {
  const name = filename.toLowerCase();
  if (/\.(png|jpe?g|webp|gif|jfif)$/.test(name)) return 'image';
  if (/\.(mp4|webm|mov|m4v)$/.test(name)) return 'video';
  if (/\.(mp3|wav|m4a|aac|ogg|flac)$/.test(name)) return 'audio';
  return null;
}

export function DesignerAssetsPanel({ scope = 'session' }: { scope?: 'session' | 'project' }) {
  const { t } = useTranslation();
  const libraryAssets = useDesignerAssetLibraryStore((state) => state.assets);
  const [projectAssets, setProjectAssets] = useState<DesignerProjectAsset[]>([]);
  const [sessionFiles, setSessionFiles] = useState<ListedSessionFile[]>([]);
  const removeAsset = useDesignerAssetLibraryStore((state) => state.removeAsset);
  const domainGraph = useDesignerStore((state) => state.domainGraph);
  const clearAssetReferences = useDesignerStore((state) => state.clearAssetReferences);
  const clearUploadedOutput = useDesignerRunStore((state) => state.clearUploadedOutput);
  const run = useDesignerRunStore((state) => state.run);
  const openViewer = useDesignerUiStore((state) => state.openViewer);

  const canvasAssetIds = useMemo(() => {
    const ids = new Set<string>();
    if (!domainGraph) return ids;
    for (const node of domainGraph.nodes) {
      const upload = node.config?.upload as { asset_id?: string } | undefined;
      if (upload?.asset_id) ids.add(upload.asset_id);
      const materials = node.config?.materials;
      if (Array.isArray(materials)) {
        for (const item of materials) {
          if (item && typeof item === 'object' && typeof (item as { asset_id?: string }).asset_id === 'string') {
            ids.add((item as { asset_id: string }).asset_id);
          }
        }
      }
    }
    return ids;
  }, [domainGraph]);

  const projectId = String(domainGraph?.project_id || '');
  const sessionId = String(domainGraph?.metadata?.session_id || '');
  useEffect(() => {
    if (!projectId) {
      setProjectAssets([]);
      return;
    }
    let cancelled = false;
    void designerWorkspaceClient.assets(projectId)
      .then((payload) => {
        if (!cancelled) setProjectAssets(payload.assets || []);
      })
      .catch(() => {
        if (!cancelled) setProjectAssets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [domainGraph?.updated_at, projectId]);

  useEffect(() => {
    if (!sessionId) {
      setSessionFiles([]);
      return;
    }
    let cancelled = false;
    const dir = `agent/sessions/${sessionId}/uploads`;
    void fetch(`/file-api/list-files?dir=${encodeURIComponent(dir)}`, { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) return [];
        const payload = (await response.json()) as { files?: Array<{ name?: string; path?: string; isDirectory?: boolean }> };
        return (payload.files || [])
          .filter((item) => item && !item.isDirectory && item.name && item.path && kindFromFilename(item.name))
          .map((item) => ({ name: String(item.name), path: String(item.path) }));
      })
      .then((files) => {
        if (!cancelled) setSessionFiles(files);
      })
      .catch(() => {
        if (!cancelled) setSessionFiles([]);
      });
    return () => {
      cancelled = true;
    };
  }, [domainGraph?.updated_at, sessionId]);

  const materials = useMemo(
    () => collectDesignerMaterials(domainGraph, run).filter((item) => !item.placeholder),
    [domainGraph, run],
  );
  const visibleLibrary = useMemo(() => {
    return libraryAssets.filter((asset) => {
      if (projectId && asset.projectId && asset.projectId !== projectId) return false;
      if (scope === 'project') return true;
      if (!sessionId) return !asset.sessionId;
      return asset.sessionId === sessionId;
    });
  }, [libraryAssets, projectId, scope, sessionId]);

  const unified: UnifiedAsset[] = useMemo(() => {
    const items: UnifiedAsset[] = [];
    const seenUris = new Set<string>();

    const serverAssets = scope === 'project'
      ? projectAssets
      : projectAssets.filter((asset) => !sessionId || asset.session_id === sessionId);
    const knownNames = new Set(serverAssets.map((asset) => asset.filename.toLowerCase()));
    for (const asset of serverAssets) {
      seenUris.add(asset.uri);
      items.push({
        id: asset.id,
        filename: asset.filename,
        kind: asset.kind,
        source: asset.source,
        previewUrl: asset.kind === 'image' ? designerAssetPreviewUrl(asset.uri) : null,
        sizeLabel: asset.kind,
        onCanvas: asset.session_id === sessionId,
        deletable: false,
        nodeId: asset.session_id === sessionId ? asset.node_id : undefined,
        sharedUri: asset.uri,
        sharedMime: asset.mime_type,
      });
    }
    if (sessionId) {
      for (const file of sessionFiles) {
        const kind = kindFromFilename(file.name);
        if (!kind || knownNames.has(file.name.toLowerCase())) continue;
        knownNames.add(file.name.toLowerCase());
        seenUris.add(file.path);
        items.push({
          id: `file:${sessionId}:${file.name}`,
          filename: file.name,
          kind,
          source: 'uploaded',
          previewUrl: kind === 'image' ? designerAssetPreviewUrl(file.path) : null,
          sizeLabel: kind,
          onCanvas: false,
          deletable: false,
          sharedUri: file.path,
        });
      }
    }

    for (const asset of visibleLibrary) {
      if (knownNames.has(asset.filename.toLowerCase())) continue;
      knownNames.add(asset.filename.toLowerCase());
      seenUris.add(asset.objectUrl);
      items.push({
        id: asset.id,
        filename: asset.filename,
        kind: asset.kind,
        source: asset.source,
        previewUrl: asset.kind === 'image' ? asset.objectUrl : null,
        sizeLabel: formatBytes(asset.size),
        onCanvas: canvasAssetIds.has(asset.id),
        deletable: true,
        nodeId: asset.nodeId,
      });
    }

    if (scope === 'session') {
      for (const material of materials) {
        if (isUploadedMaterial(material) && seenUris.has(material.uri)) {
          continue;
        }
        if (seenUris.has(material.uri)) continue;
        seenUris.add(material.uri);
        const kind = kindFromMaterial(material);
        items.push({
          id: `gen:${material.id}`,
          filename: material.label,
          kind,
          source: material.source || (isUploadedMaterial(material) ? 'uploaded' : 'generated'),
          previewUrl: kind === 'image' ? material.previewUrl : null,
          sizeLabel: material.kind,
          onCanvas: true,
          deletable: false,
          materialId: material.id,
          nodeId: material.nodeId,
        });
      }
    }

    return items;
  }, [canvasAssetIds, materials, projectAssets, scope, sessionFiles, sessionId, visibleLibrary]);

  const onDelete = useCallback(
    (assetId: string) => {
      const affectedNodeIds: string[] = [];
      if (domainGraph) {
        for (const node of domainGraph.nodes) {
          const upload = node.config?.upload as { asset_id?: string } | undefined;
          if (upload?.asset_id === assetId) {
            affectedNodeIds.push(node.id);
          }
        }
      }
      clearAssetReferences(assetId);
      for (const nodeId of affectedNodeIds) {
        clearUploadedOutput(nodeId);
      }
      removeAsset(assetId);
    },
    [clearAssetReferences, clearUploadedOutput, domainGraph, removeAsset],
  );

  const onOpen = useCallback(
    (item: UnifiedAsset) => {
      if (item.materialId) {
        openViewer(item.materialId);
        return;
      }
      if (item.nodeId) {
        openViewer(item.nodeId);
        return;
      }
      const library = libraryAssets.find((asset) => asset.id === item.id);
      if (!library) return;
      const match = materials.find((material) => material.uri === library.objectUrl);
      if (match) openViewer(match.id);
    },
    [libraryAssets, materials, openViewer],
  );

  if (unified.length === 0) {
    return (
      <div className="designer-assets-panel" data-testid="designer-assets-panel" data-scope={scope}>
        <p className="designer-assets-panel__empty">
          {t(scope === 'project' ? 'designer.assets.emptyProject' : 'designer.assets.empty')}
        </p>
      </div>
    );
  }

  return (
    <div className="designer-assets-panel" data-testid="designer-assets-panel" data-scope={scope}>
      <ul className="designer-assets-panel__list">
        {unified.map((asset) => (
          <li
            key={asset.id}
            className="designer-assets-panel__item"
            data-testid="designer-assets-panel-item"
            data-asset-id={asset.id}
            data-source={asset.source}
          >
            <button
              type="button"
              className="designer-assets-panel__open"
              draggable={Boolean(asset.deletable || asset.sharedUri)}
              onDragStart={(event) => {
                if (asset.sharedUri) {
                  event.dataTransfer.setData(
                    DESIGNER_PROJECT_ASSET_DRAG_MIME,
                    JSON.stringify({
                      uri: asset.sharedUri,
                      filename: asset.filename,
                      kind: asset.kind,
                      mime_type: asset.sharedMime || '',
                    }),
                  );
                  event.dataTransfer.effectAllowed = 'copy';
                  return;
                }
                if (!asset.deletable) return;
                event.dataTransfer.setData(DESIGNER_ASSET_DRAG_MIME, asset.id);
                event.dataTransfer.effectAllowed = 'copy';
              }}
              onClick={() => onOpen(asset)}
              data-testid="designer-assets-panel-open"
            >
              <div className="designer-assets-panel__thumb">
                {asset.kind === 'image' && asset.previewUrl ? (
                  <img src={asset.previewUrl} alt="" />
                ) : (
                  <AssetKindIcon kind={asset.kind} />
                )}
              </div>
              <div className="designer-assets-panel__meta">
                <span className="designer-assets-panel__name" title={asset.filename}>
                  {asset.filename}
                </span>
                <span className="designer-assets-panel__sub">
                  {asset.source === 'uploaded'
                    ? t('designer.assets.sourceUploaded')
                    : t('designer.assets.sourceGenerated')}
                  {' · '}
                  {asset.sizeLabel}
                  {' · '}
                  {asset.onCanvas ? t('designer.assets.onCanvas') : t('designer.assets.libraryOnly')}
                </span>
              </div>
            </button>
            {asset.deletable ? (
              <button
                type="button"
                className="designer-assets-panel__delete"
                aria-label={t('designer.assets.delete')}
                title={t('designer.assets.delete')}
                data-testid="designer-assets-panel-delete"
                onClick={() => onDelete(asset.id)}
              >
                <Trash2 size={14} aria-hidden />
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
