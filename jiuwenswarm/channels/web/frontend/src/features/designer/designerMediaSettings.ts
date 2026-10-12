/** Canvas-wide generation settings shown in the node toolbar. */

import type { DesignerImageSettings, DesignerMediaCapabilities, DesignerVideoSettings } from './executionGraphTypes';

function storedField(metadata: Record<string, unknown> | undefined, key: string, field: string): string {
  const raw = metadata?.[key];
  if (!raw || typeof raw !== 'object') return '';
  const value = (raw as Record<string, unknown>)[field];
  return typeof value === 'string' ? value.trim() : '';
}

function allowedOr(value: string, allowed: string[], fallback: string): string {
  const wanted = value.toLowerCase();
  return allowed.find((item) => item.toLowerCase() === wanted) ?? fallback;
}

/** Stored canvas settings; values the active model does not list fall back to the server's snapped value. */
export function effectiveVideoSettings(
  metadata: Record<string, unknown> | undefined,
  caps: DesignerMediaCapabilities,
): DesignerVideoSettings {
  const fallback = caps.settings?.video;
  return {
    aspect_ratio: allowedOr(
      storedField(metadata, 'video_settings', 'aspect_ratio'),
      caps.video.ratios,
      fallback?.aspect_ratio ?? caps.video.default_ratio,
    ),
    resolution: allowedOr(
      storedField(metadata, 'video_settings', 'resolution'),
      caps.video.resolutions,
      fallback?.resolution ?? caps.video.default_resolution,
    ),
  };
}

export function effectiveImageSettings(
  metadata: Record<string, unknown> | undefined,
  caps: DesignerMediaCapabilities,
): DesignerImageSettings {
  return {
    aspect_ratio: allowedOr(
      storedField(metadata, 'image_settings', 'aspect_ratio'),
      caps.image.ratios,
      caps.settings?.image.aspect_ratio ?? caps.image.default_ratio,
    ),
  };
}
