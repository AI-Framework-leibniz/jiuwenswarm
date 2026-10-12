import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { designerGraphClient } from '../../designerGraphClient';
import {
  effectiveImageSettings,
  effectiveVideoDuration,
  effectiveVideoSettings,
  generatesTimedVideo,
} from '../../designerMediaSettings';
import { useDesignerRunStore } from '../../designerRunStore';
import { useDesignerStore } from '../../designerStore';
import type { DesignerMediaCapabilities, DesignerMediaSettingsPatch } from '../../executionGraphTypes';

type DesignerMediaSettingsFormProps = {
  nodeId: string;
  nodeType: 'image' | 'video';
};

type ChoiceGroupProps = {
  label: string;
  options: string[];
  value: string;
  disabled: boolean;
  testId: string;
  onSelect: (value: string) => void;
};

function ChoiceGroup({ label, options, value, disabled, testId, onSelect }: ChoiceGroupProps) {
  return (
    <div className="designer-media-settings__field" role="radiogroup" aria-label={label} data-testid={testId}>
      <span className="designer-media-settings__label">{label}</span>
      <div className="designer-media-settings__choices">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={option === value}
            className={`designer-media-settings__choice${option === value ? ' is-selected' : ''}`}
            disabled={disabled}
            onClick={() => {
              if (option !== value) onSelect(option);
            }}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Canvas-wide ratio / resolution for this node's media type, plus a video node's own length. */
export function DesignerMediaSettingsForm({ nodeId, nodeType }: DesignerMediaSettingsFormProps) {
  const { t } = useTranslation();
  const graphId = useDesignerStore((state) => state.domainGraph?.graph_id ?? '');
  const metadata = useDesignerStore((state) => state.domainGraph?.metadata);
  const durationSec = useDesignerStore(
    (state) => state.domainGraph?.nodes.find((node) => node.id === nodeId)?.config?.duration_sec,
  );
  const timed = useDesignerStore((state) => nodeType === 'video' && generatesTimedVideo(state.domainGraph, nodeId));
  const updateNodeConfig = useDesignerStore((state) => state.updateNodeConfig);
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
  const seconds = timed ? effectiveVideoDuration(nodeId, durationSec, caps) : 0;

  return (
    <div
      className="designer-node-toolbar__params designer-media-settings"
      data-testid="designer-media-settings"
      data-media-type={nodeType}
    >
      <p className="designer-node-toolbar__params-title">
        {isVideo ? t('designer.mediaSettings.videoTitle') : t('designer.mediaSettings.imageTitle')}
      </p>
      <ChoiceGroup
        label={t('designer.toolbar.aspectRatio')}
        options={isVideo ? caps.video.ratios : caps.image.ratios}
        value={isVideo ? video.aspect_ratio : image.aspect_ratio}
        disabled={saving}
        testId={isVideo ? 'designer-media-settings-video-ratio' : 'designer-media-settings-image-ratio'}
        onSelect={(aspect_ratio) =>
          apply(isVideo ? { video_settings: { aspect_ratio } } : { image_settings: { aspect_ratio } })
        }
      />
      <ChoiceGroup
        label={t('designer.toolbar.resolution')}
        options={isVideo ? caps.video.resolutions : caps.image.resolutions}
        value={isVideo ? video.resolution : image.resolution}
        disabled={saving}
        testId={isVideo ? 'designer-media-settings-video-resolution' : 'designer-media-settings-image-resolution'}
        onSelect={(resolution) =>
          apply(isVideo ? { video_settings: { resolution } } : { image_settings: { resolution } })
        }
      />
      {timed ? (
        <label className="designer-media-settings__field" data-testid="designer-media-settings-video-duration">
          <span className="designer-media-settings__label">
            {t('designer.toolbar.duration')}
            <span className="designer-media-settings__value">
              {t('designer.mediaSettings.durationValue', { seconds })}
            </span>
          </span>
          <input
            type="range"
            className="designer-media-settings__slider"
            min={caps.video.min_sec}
            max={caps.video.max_sec}
            step={1}
            value={seconds}
            onChange={(event) => {
              const next = Number(event.target.value);
              updateNodeConfig(nodeId, (config) => ({ ...config, duration_sec: next }));
            }}
          />
        </label>
      ) : null}
      {error ? (
        <p className="designer-node-toolbar__params-hint is-error" data-testid="designer-media-settings-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
