import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clipDurationSeconds,
  effectiveImageSettings,
  effectiveVideoSettings,
} from '../node_modules/.cache/designer-media-settings/designerMediaSettings.js';

const caps = {
  video: {
    configured_model: 'wan3.0-video',
    model_id: 'wan3.0-video',
    provider: 'dashscope',
    ratios: ['16:9', '9:16', '1:1', '4:3', '3:4'],
    resolutions: ['480P', '720P', '1080P'],
    default_ratio: '16:9',
    default_resolution: '1080P',
    min_sec: 2,
    max_sec: 30,
    default_sec: 5,
  },
  image: { ratios: ['16:9', '9:16', '1:1', '4:3', '3:4', '3:2', '2:3', '21:9'], default_ratio: '16:9' },
  settings: {
    video: { aspect_ratio: '16:9', resolution: '720P' },
    image: { aspect_ratio: '1:1' },
  },
};

test('stored canvas settings are shown with the model spelling', () => {
  const metadata = { video_settings: { aspect_ratio: '9:16', resolution: '720p' } };
  assert.deepEqual(effectiveVideoSettings(metadata, caps), { aspect_ratio: '9:16', resolution: '720P' });
});

test('values the model does not list fall back to the server snapped settings', () => {
  const metadata = { video_settings: { aspect_ratio: '21:9', resolution: '2K' } };
  assert.deepEqual(effectiveVideoSettings(metadata, caps), { aspect_ratio: '16:9', resolution: '720P' });
  assert.deepEqual(effectiveImageSettings({}, caps), { aspect_ratio: '1:1' });
  const { settings: _settings, ...bare } = caps;
  assert.deepEqual(effectiveVideoSettings(undefined, bare), { aspect_ratio: '16:9', resolution: '1080P' });
  assert.deepEqual(effectiveImageSettings(undefined, bare), { aspect_ratio: '16:9' });
});

test('image ratio is independent of the video ratio', () => {
  const metadata = { video_settings: { aspect_ratio: '9:16' }, image_settings: { aspect_ratio: '21:9' } };
  assert.equal(effectiveImageSettings(metadata, caps).aspect_ratio, '21:9');
});

test('clip duration is the storyboard window clamped to the model range', () => {
  assert.equal(clipDurationSeconds('5.0-12.0s', 2, 30), 7);
  assert.equal(clipDurationSeconds('0-45s', 4, 15), 15);
  assert.equal(clipDurationSeconds('0-1s', 4, 15), 4);
  assert.equal(clipDurationSeconds('shot 3', 2, 30), 5);
});
