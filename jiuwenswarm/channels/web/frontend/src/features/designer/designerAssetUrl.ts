import { webRequest } from '../../services/webClient';

/** Turn a Designer output_ref.uri into a browser-playable /file-api URL. */

export function localPathToFileUri(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  if (/^[A-Za-z]:\//.test(normalized)) {
    return `file:///${normalized}`;
  }
  if (normalized.startsWith('/')) {
    return `file://${normalized}`;
  }
  return `file:///${normalized}`;
}

export function fileUriToLocalPath(uri: string): string | null {
  const value = (uri || '').trim();
  if (!value) return null;
  if (value.startsWith('designer://')) return null;
  if (/^https?:\/\//i.test(value)) return null;
  if (value.startsWith('file:')) {
    try {
      const parsed = new URL(value);
      let pathname = decodeURIComponent(parsed.pathname);
      if (/^\/[A-Za-z]:\//.test(pathname)) {
        pathname = pathname.slice(1);
      }
      return pathname;
    } catch {
      return null;
    }
  }
  return value;
}

export function isPlaceholderAsset(uri: string | null | undefined): boolean {
  return Boolean(uri?.startsWith('designer://'));
}

export function designerAssetPreviewUrl(uri: string | null | undefined): string | null {
  const value = (uri || '').trim();
  if (!value) return null;
  if (/^https?:\/\//i.test(value)) return value;
  // Session-local uploads use blob URLs.
  if (value.startsWith('blob:')) return value;
  const localPath = fileUriToLocalPath(value);
  if (!localPath) return null;
  return `/file-api/raw-file?path=${encodeURIComponent(localPath)}`;
}

export async function saveDesignerTextFile(uri: string, content: string): Promise<void> {
  const filePath = fileUriToLocalPath(uri);
  if (!filePath) throw new Error('missing_file_path');
  const response = await fetch('/file-api/file-content', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path: filePath, content }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail.slice(0, 160) || `HTTP ${response.status}`);
  }
}

function mediaTypeForUpload(file: File): 'image' | 'video' | 'audio' {
  const type = (file.type || '').toLowerCase();
  if (type.startsWith('video/')) return 'video';
  if (type.startsWith('audio/')) return 'audio';
  return 'image';
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const payload = result.includes(',') ? result.split(',')[1] : result;
      if (!payload) reject(new Error('upload_failed'));
      else resolve(payload);
    };
    reader.onerror = () => reject(reader.error ?? new Error('upload_failed'));
    reader.readAsDataURL(file);
  });
}

export async function uploadDesignerAsset(file: File, sessionId?: string): Promise<{
  path: string;
  filename: string;
  mime_type?: string;
}> {
  if (sessionId) {
    try {
      const base64Data = await readFileAsBase64(file);
      const persisted = await webRequest<{
        media_items?: Array<{ path?: string; filename?: string; mime_type?: string }>;
      }>(
        'media.persist',
        {
          session_id: sessionId,
          content: '',
          include_av: true,
          media_items: [{
            type: mediaTypeForUpload(file),
            filename: file.name,
            mime_type: file.type,
            mimeType: file.type,
            base64Data,
            size_bytes: file.size,
          }],
        },
        { timeoutMs: 60_000 },
      );
      const uploaded = persisted.media_items?.find((item) => item.path);
      if (uploaded?.path) {
        return {
          path: uploaded.path,
          filename: uploaded.filename || file.name,
          mime_type: uploaded.mime_type || file.type,
        };
      }
    } catch {
      // The running gateway may still be image-only. Fall through to the dev upload route.
    }
  }
  const form = new FormData();
  form.append('file', file);
  const response = await fetch('/file-api/upload', {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail.slice(0, 160) || `HTTP ${response.status}`);
  }
  const payload = (await response.json()) as {
    files?: Array<{ path?: string; filename?: string; mime_type?: string }>;
    errors?: Array<{ error?: string }>;
  };
  const uploaded = payload.files?.find((item) => item.path);
  if (!uploaded?.path) {
    throw new Error(payload.errors?.[0]?.error || 'upload_failed');
  }
  return {
    path: uploaded.path,
    filename: uploaded.filename || file.name,
    mime_type: uploaded.mime_type,
  };
}

export function designerAssetTextUrl(uri: string | null | undefined): string | null {
  const value = (uri || '').trim();
  if (!value || /^https?:\/\//i.test(value)) return null;
  const localPath = fileUriToLocalPath(value);
  if (!localPath) return null;
  return `/file-api/file-content?path=${encodeURIComponent(localPath)}&encoding=auto`;
}
