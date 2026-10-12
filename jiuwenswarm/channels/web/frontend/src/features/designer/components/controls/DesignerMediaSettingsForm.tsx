import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { designerGraphClient } from '../../designerGraphClient';
import { effectiveImageSettings, effectiveVideoSettings } from '../../designerMediaSettings';
import { useDesignerRunStore } from '../../designerRunStore';
import { useDesignerStore } from '../../designerStore';
import type { DesignerMediaCapabilities, DesignerMediaSettingsPatch } from '../../executionGraphTypes';

type DesignerMediaSettingsFormProps = {
  nodeId: string;
  nodeType: 'image' | 'video';
};

/** Canvas-wide ratio / resolution for this node's media type, limited to what the configured model accepts. */
export function DesignerMediaSettingsForm({ nodeId, nodeType }: DesignerMediaSettingsFormProps) {
  const { t } = useTranslation();
  const graphId = useDesignerStore((state) => state.domainGraph?.graph_id ?? '');
  const metadata = useDesignerStore((state) => state.domainGraph?.metadata);
  // A finished storyboard run can change clip lengths, so refetch with the run.
  const runVersion = useDesignerRunStore((state) => `${state.run?.run_id ?? ''}:${state.run?.updated_at ?? ''}`);
  const patchMediaSettings = useDesignerStore((state) => state.patchMediaSettings);
  const [caps, setCaps] = useState<DesignerMediaCapabilities | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!graphId) return undefined;
    let cancelled = false;
    setError('');
    designerGraphClient
      .mediaCapabilities(graphId)
      .then((result) => {
        if (!cancelled) setCaps(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(
            t('designer.mediaSettings.loadError', {
              message: reason instanceof Error ? reason.message : String(reason),
            }),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [graphId, runVersion, t]);

  const apply = (patch: DesignerMediaSettingsPatch) => {
    setSaving(true);
    setError('');
    patchMediaSettings(patch)
      .catch((reason: unknown) => {
        setError(
          t('designer.mediaSettings.saveError', {
            message: reason instanceof Error ? reason.message : String(reason),
          }),
        );
      })
      .finally(() => setSaving(false));
  };

  if (!caps) {
    return (
      <div className="designer-node-toolbar__params" data-testid="designer-media-settings">
        <p
          className="designer-node-toolbar__params-hint"
          data-testid={error ? 'designer-media-settings-error' : 'designer-media-settings-loading'}
        >
          {error || t('designer.mediaSettings.loading')}
        </p>
      </div>
    );
  }

  const isVideo = nodeType === 'video';
  const video = effectiveVideoSettings(metadata, caps);
  const image = effectiveImageSettings(metadata, caps);
  const clipSeconds = isVideo ? caps.clip_durations?.[nodeId] : undefined;

  return (
    <div className="designer-node-toolbar__params" data-testid="designer-media-settings" data-media-type={nodeType}>
      <p className="designer-node-toolbar__params-title">
        {isVideo ? t('designer.mediaSettings.videoTitle') : t('designer.mediaSettings.imageTitle')}
      </p>
      <label className="designer-node-toolbar__param">
        {t('designer.toolbar.aspectRatio')}
        <select
          value={isVideo ? video.aspect_ratio : image.aspect_ratio}
          disabled={saving}
          data-testid={isVideo ? 'designer-media-settings-video-ratio' : 'designer-media-settings-image-ratio'}
          onChange={(event) =>
            apply(
              isVideo
                ? { video_settings: { aspect_ratio: event.target.value } }
                : { image_settings: { aspect_ratio: event.target.value } },
            )
          }
        >
          {(isVideo ? caps.video.ratios : caps.image.ratios).map((ratio) => (
            <option key={ratio} value={ratio}>
              {ratio}
            </option>
          ))}
        </select>
      </label>
      {isVideo ? (
        <label className="designer-node-toolbar__param">
          {t('designer.toolbar.resolution')}
          <select
            value={video.resolution}
            disabled={saving}
            data-testid="designer-media-settings-video-resolution"
            onChange={(event) => apply({ video_settings: { resolution: event.target.value } })}
          >
            {caps.video.resolutions.map((resolution) => (
              <option key={resolution} value={resolution}>
                {resolution}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {clipSeconds !== undefined ? (
        <div className="designer-node-toolbar__param" data-testid="designer-media-settings-video-duration">
          {t('designer.toolbar.duration')}
          <span className="designer-node-toolbar__param-value">
            {t('designer.mediaSettings.durationValue', { seconds: clipSeconds })}
          </span>
        </div>
      ) : null}
      {clipSeconds !== undefined ? (
        <p className="designer-node-toolbar__params-hint" data-testid="designer-media-settings-duration-hint">
          {t('designer.mediaSettings.durationHint', { min: caps.video.min_sec, max: caps.video.max_sec })}
        </p>
      ) : null}
      {error ? (
        <p className="designer-node-toolbar__params-hint is-error" data-testid="designer-media-settings-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
