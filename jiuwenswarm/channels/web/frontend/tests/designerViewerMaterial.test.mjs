import assert from 'node:assert/strict';
import test from 'node:test';

import {
  previewMaterialForNode,
  resolveDesignerViewerMaterial,
} from '../node_modules/.cache/designer-viewer-material/designerMaterials.js';

function material(overrides) {
  return {
    label: 'item',
    placeholder: false,
    previewUrl: null,
    textUrl: null,
    uri: 'file:///item',
    ...overrides,
  };
}

const materials = [
  material({
    id: 'user_ref:castle',
    nodeId: 'n_brief',
    role: 'user_reference',
    kind: 'image',
    previewUrl: '/castle.png',
    uri: 'file:///castle.png',
    label: 'castle.png',
  }),
  material({
    id: 'n_brief:0',
    nodeId: 'n_brief',
    role: 'brief',
    kind: 'text',
    textUrl: '/brief.md',
    uri: 'file:///brief.md',
    label: 'brief',
  }),
  material({
    id: 'n_image:0',
    nodeId: 'n_image',
    kind: 'image',
    previewUrl: '/shot.png',
    uri: 'file:///shot.png',
  }),
  material({
    id: 'n_image:1',
    nodeId: 'n_image',
    kind: 'text',
    textUrl: '/shot.md',
    uri: 'file:///shot.md',
  }),
];

test('text node preview opens its markdown instead of an attached reference', () => {
  assert.equal(previewMaterialForNode(materials, 'n_brief', 'text')?.id, 'n_brief:0');
  assert.equal(resolveDesignerViewerMaterial(materials, 'n_brief')?.id, 'n_brief:0');
  assert.equal(resolveDesignerViewerMaterial(materials, 'n_brief:0')?.id, 'n_brief:0');
});

test('an explicit reference id still opens that reference', () => {
  assert.equal(resolveDesignerViewerMaterial(materials, 'user_ref:castle')?.id, 'user_ref:castle');
});

test('image node preview keeps the image when a markdown sidecar is also attached', () => {
  assert.equal(previewMaterialForNode(materials, 'n_image', 'image')?.id, 'n_image:0');
  assert.equal(resolveDesignerViewerMaterial(materials, 'n_image')?.id, 'n_image:0');
});
