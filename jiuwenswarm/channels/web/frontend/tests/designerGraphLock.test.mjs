import assert from 'node:assert/strict';
import test from 'node:test';
import { isDesignerGraphEditingLocked } from '../node_modules/.cache/designer-graph-lock/designerGraphLock.js';

const promptGraph = {
  graph_id: 'g1',
  source: 'prompt',
  nodes: [{ id: 'n1' }, { id: 'n2' }],
};

test('a built graph stays locked until every node finishes', () => {
  assert.equal(
    isDesignerGraphEditingLocked({
      bootstrapInProgress: false,
      graph: promptGraph,
      nodeStates: { n1: { status: 'completed' }, n2: { status: 'pending' } },
      runStatus: 'paused',
    }),
    true,
  );
  assert.equal(
    isDesignerGraphEditingLocked({
      bootstrapInProgress: false,
      graph: promptGraph,
      nodeStates: { n1: { status: 'completed' }, n2: { status: 'completed' } },
      runStatus: 'completed',
    }),
    false,
  );
});

test('building and an active run lock the graph', () => {
  assert.equal(
    isDesignerGraphEditingLocked({
      bootstrapInProgress: true,
      graph: null,
      nodeStates: {},
      runStatus: null,
    }),
    true,
  );
  assert.equal(
    isDesignerGraphEditingLocked({
      bootstrapInProgress: false,
      graph: { graph_id: 'g2', source: 'manual', nodes: [{ id: 'n1' }] },
      nodeStates: { n1: { status: 'pending' } },
      runStatus: 'running',
    }),
    true,
  );
});

test('a failed built graph unlocks so it can be edited', () => {
  assert.equal(
    isDesignerGraphEditingLocked({
      bootstrapInProgress: false,
      graph: promptGraph,
      nodeStates: { n1: { status: 'completed' }, n2: { status: 'failed' } },
      runStatus: 'failed',
    }),
    false,
  );
});

test('a manual canvas stays editable before the first run', () => {
  assert.equal(
    isDesignerGraphEditingLocked({
      bootstrapInProgress: false,
      graph: { graph_id: 'g2', source: 'manual', nodes: [{ id: 'n1' }] },
      nodeStates: {},
      runStatus: null,
    }),
    false,
  );
});
