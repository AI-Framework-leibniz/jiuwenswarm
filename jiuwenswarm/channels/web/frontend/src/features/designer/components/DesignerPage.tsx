import { Loader2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  collectDesignerMaterials,
  collectPendingRevisions,
} from '../designerMaterials';
import { useDesignerChatStore } from '../designerChatStore';
import { bindDesignerRuntime, useDesignerRunStore } from '../designerRunStore';
import { isDesignerPreviewGraph } from '../designerBootstrapGraph';
import { useDesignerStore } from '../designerStore';
import { useDesignerUiStore } from '../designerUiStore';
import { DesignerMaterialViewer } from '../DesignerMaterialViewer';
import { DesignerRevisionChooser } from '../DesignerRevisionChooser';
import { DesignerCanvas } from './DesignerCanvas';
import { DesignerChatPanel, DesignerEmptyState } from './DesignerChatPanel';
import { DesignerRunControl } from './DesignerRunControl';
import { designerWorkspaceClient, type DesignerSessionSummary } from '../designerGraphClient';
import { DesignerTrajectoryPanel } from './DesignerTrajectoryPanel';
import { useWorkspaceStore } from '../../../stores/workspaceStore';
import './DesignerPage.css';

type DesignerPageProps = {
  projectId?: string;
  sessionId?: string;
  onOpenSession?: (projectId: string, sessionId: string, options?: { replace?: boolean }) => void;
};

export function DesignerPage({ projectId, sessionId, onOpenSession }: DesignerPageProps) {
  const { t } = useTranslation();
  const effectiveProjectId = projectId;

  const loadStatus = useDesignerStore((state) => state.loadStatus);
  const loadError = useDesignerStore((state) => state.loadError);
  const domainGraph = useDesignerStore((state) => state.domainGraph);
  const graphId = useDesignerStore((state) => state.graphId);
  const bootstrapInProgress = useDesignerStore((state) => state.bootstrapInProgress);
  const resetForGraph = useDesignerRunStore((state) => state.resetForGraph);
  const boundGraphId = useDesignerRunStore((state) => state.boundGraphId);
  const run = useDesignerRunStore((state) => state.run);
  const runError = useDesignerRunStore((state) => state.runError);
  const runWarning = useDesignerRunStore((state) => state.runWarning);
  const chooseOutput = useDesignerRunStore((state) => state.chooseOutput);
  const selectedMaterialId = useDesignerUiStore((state) => state.selectedMaterialId);
  const viewerOpen = useDesignerUiStore((state) => state.viewerOpen);
  const chooserNodeId = useDesignerUiStore((state) => state.chooserNodeId);
  const editRequestKey = useDesignerUiStore((state) => state.editRequestKey);
  const setSelectedMaterialId = useDesignerUiStore((state) => state.setSelectedMaterialId);
  const closeViewer = useDesignerUiStore((state) => state.closeViewer);
  const closeRevision = useDesignerUiStore((state) => state.closeRevision);
  const resetUi = useDesignerUiStore((state) => state.reset);
  const workspaceLoadSeqRef = useRef(0);
  const loadedKeyRef = useRef('');
  const onOpenSessionRef = useRef(onOpenSession);
  onOpenSessionRef.current = onOpenSession;
  const [sessions, setSessions] = useState<DesignerSessionSummary[]>([]);
  const [creatingSession, setCreatingSession] = useState(false);
  const [trajectoryOpen, setTrajectoryOpen] = useState(true);
  useEffect(() => bindDesignerRuntime(), []);

  useEffect(() => {
    if (!effectiveProjectId || bootstrapInProgress) return;
    const requestedKey = `${effectiveProjectId}:${sessionId || ''}`;
    if (sessionId && loadedKeyRef.current === requestedKey) return;
    const loadSeq = ++workspaceLoadSeqRef.current;
    useDesignerStore.getState().reset();
    void designerWorkspaceClient.get(effectiveProjectId, sessionId)
      .then((workspace) => {
        if (workspaceLoadSeqRef.current !== loadSeq) return;
        const opened = String(workspace.session?.session_id || '');
        loadedKeyRef.current = `${effectiveProjectId}:${opened}`;
        setSessions(workspace.sessions || []);
        useDesignerStore.getState().applyGraph(workspace.graph);
        useDesignerChatStore.getState().replaceMessages(
          workspace.graph.graph_id,
          workspace.messages,
        );
        if (opened && opened !== sessionId) {
          onOpenSessionRef.current?.(effectiveProjectId, opened, { replace: true });
        }
      })
      .catch((reason) => {
        if (workspaceLoadSeqRef.current !== loadSeq) return;
        const message = reason instanceof Error ? reason.message : String(reason);
        useDesignerStore.getState().failBootstrapEntry(message);
      });
    return () => {
      if (workspaceLoadSeqRef.current === loadSeq) {
        workspaceLoadSeqRef.current += 1;
      }
    };
  }, [
    bootstrapInProgress,
    effectiveProjectId,
    sessionId,
  ]);

  const openSession = useCallback((nextSessionId: string) => {
    if (!effectiveProjectId || !nextSessionId || nextSessionId === sessionId) return;
    onOpenSession?.(effectiveProjectId, nextSessionId);
  }, [effectiveProjectId, onOpenSession, sessionId]);

  const createSession = useCallback(() => {
    if (!effectiveProjectId || creatingSession) return;
    setCreatingSession(true);
    void designerWorkspaceClient.createSession({ projectId: effectiveProjectId })
      .then((workspace) => {
        const opened = String(workspace.session?.session_id || '');
        loadedKeyRef.current = `${effectiveProjectId}:${opened}`;
        setSessions(workspace.sessions || []);
        useDesignerStore.getState().applyGraph(workspace.graph);
        useDesignerChatStore.getState().replaceMessages(
          workspace.graph.graph_id,
          workspace.messages,
        );
        if (opened) onOpenSessionRef.current?.(effectiveProjectId, opened);
      })
      .catch((reason) => {
        const message = reason instanceof Error ? reason.message : String(reason);
        useDesignerStore.getState().failBootstrapEntry(message);
      })
      .finally(() => setCreatingSession(false));
  }, [creatingSession, effectiveProjectId, onOpenSession]);

  useEffect(() => {
    const nextId = domainGraph?.graph_id ?? null;
    if (nextId !== boundGraphId) {
      resetUi();
      resetForGraph(domainGraph);
      useDesignerChatStore.getState().bindGraph(nextId);
    }
    if (domainGraph && !isDesignerPreviewGraph(domainGraph)) {
      useDesignerChatStore.getState().ensureGraphPrompt(domainGraph, {
        doneText: t('designer.chat.bootstrapDone'),
      });
    }
  }, [boundGraphId, domainGraph, resetForGraph, resetUi, t]);

  useEffect(() => {
    if (!effectiveProjectId) return;
    const workspace = useWorkspaceStore.getState();
    void workspace.loadProjectSessions(effectiveProjectId);
    void workspace.loadProjects();
  }, [domainGraph?.graph_id, domainGraph?.title, effectiveProjectId]);

  useEffect(() => {
    const opened = String(sessionId || domainGraph?.metadata?.session_id || '');
    const title = domainGraph?.title?.trim() || '';
    if (!opened || !title || title === '设计项目') return;
    setSessions((current) => current.map((item) => (
      item.session_id === opened ? { ...item, title } : item
    )));
  }, [domainGraph, sessionId]);

  const materials = useMemo(
    () => collectDesignerMaterials(domainGraph, run),
    [domainGraph, run],
  );
  const pendingRevisions = useMemo(
    () => collectPendingRevisions(domainGraph, run),
    [domainGraph, run],
  );
  const autoPromotedRef = useRef(new Set<string>());
  useEffect(() => {
    const runId = run?.run_id;
    if (!runId || run?.status === 'running') return;
    for (const item of pendingRevisions) {
      const key = `${runId}:${item.nodeId}`;
      if (item.requiresSelection || autoPromotedRef.current.has(key)) continue;
      // Brief/storyboard versions remain pending until the user chooses one.
      autoPromotedRef.current.add(key);
      void chooseOutput(item.nodeId, 'new').then(() => {
        if (chooserNodeId === item.nodeId) closeRevision();
      });
    }
  }, [chooseOutput, chooserNodeId, closeRevision, pendingRevisions, run?.run_id, run?.status]);
  const activeRevision =
    pendingRevisions.find((item) => item.nodeId === chooserNodeId) ?? pendingRevisions[0];

  const graphReady = Boolean(domainGraph) && (!graphId || domainGraph?.graph_id === graphId);
  const showCanvas = graphReady;
  const showEmpty = !showCanvas && loadStatus === 'empty';
  const showError = !showCanvas && loadStatus === 'error';
  const showLoading =
    !showCanvas &&
    (loadStatus === 'loading' || loadStatus === 'idle' || loadStatus === 'bootstrapping');

  const projectTitle =
    domainGraph?.title?.trim() ||
    (showLoading || showEmpty || showError ? '' : t('designer.subtitle'));

  return (
    <div className="designer-page app-section" data-testid="designer-page">
      <header className="designer-page__toolbar" data-testid="designer-page-toolbar">
        <div className="designer-page__heading">
          <h1 className="designer-page__title" data-testid="designer-page-rail-title">
            {t('nav.design')}
          </h1>
          <p className="designer-page__subtitle" data-testid="designer-page-title">
            {projectTitle || t('designer.subtitle')}
          </p>
        </div>
        <div className="designer-page__toolbar-actions">
          {sessions.length > 0 ? (
            <div className="designer-session-switcher" data-testid="designer-session-switcher">
              <select
                className="designer-session-switcher__select"
                aria-label={t('designer.sessions.label')}
                data-testid="designer-session-select"
                value={sessionId || sessions[0]?.session_id || ''}
                onChange={(event) => openSession(event.target.value)}
              >
                {sessions.map((item) => (
                  <option key={item.session_id} value={item.session_id}>
                    {item.title || item.session_id}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="designer-session-switcher__new"
                data-testid="designer-session-new"
                disabled={creatingSession || bootstrapInProgress}
                onClick={createSession}
              >
                {t('designer.sessions.new')}
              </button>
            </div>
          ) : null}
          {showCanvas ? (
            <button
              type="button"
              className="designer-session-switcher__new"
              data-testid="designer-trajectory-toggle"
              aria-pressed={trajectoryOpen}
              onClick={() => setTrajectoryOpen((open) => !open)}
            >
              {trajectoryOpen ? t('designer.trajectory.hide') : t('designer.trajectory.show')}
            </button>
          ) : null}
          <DesignerRunControl
            graph={showCanvas ? domainGraph : null}
            disabled={
              !showCanvas ||
              bootstrapInProgress ||
              isDesignerPreviewGraph(domainGraph)
            }
          />
        </div>
      </header>
      {runError ? (
        <div
          className="app-toast-wrapper app-toast-wrapper--top-center"
          data-testid="designer-run-error-toast"
        >
          <div className="app-connection-toast" role="alert" data-testid="designer-error">
            {runError}
          </div>
        </div>
      ) : null}
      {runWarning ? (
        <p className="designer-page__warning" data-testid="designer-warning">
          {runWarning}
        </p>
      ) : null}

      <div className={`designer-page__workspace${trajectoryOpen && showCanvas ? ' is-trajectory-open' : ''}`}>
        <DesignerChatPanel />

        {showCanvas && domainGraph ? <DesignerCanvas graph={domainGraph} /> : null}
        {showCanvas && trajectoryOpen && effectiveProjectId && (sessionId || domainGraph?.metadata?.session_id) ? (
          <DesignerTrajectoryPanel
            projectId={effectiveProjectId}
            sessionId={String(sessionId || domainGraph?.metadata?.session_id || '')}
            graphId={domainGraph?.graph_id}
            running={run?.status === 'running'}
            onClose={() => setTrajectoryOpen(false)}
          />
        ) : null}

        {showLoading ? (
          <div className="designer-page__state" data-testid="designer-loading-state">
            <div className="designer-page__state-card">
              <Loader2 className="mx-auto mb-3 animate-spin" size={24} aria-hidden />
              <p className="designer-page__state-desc">
                {loadStatus === 'bootstrapping' ? t('designer.chat.thinking') : t('designer.loading')}
              </p>
            </div>
          </div>
        ) : null}

        {showEmpty ? <DesignerEmptyState variant="empty" /> : null}
        {showError ? <DesignerEmptyState variant="error" errorMessage={loadError} /> : null}
      </div>

      {viewerOpen ? (
        <DesignerMaterialViewer
          materials={materials}
          selectedId={selectedMaterialId}
          startEditKey={editRequestKey}
          onSelect={setSelectedMaterialId}
          onClose={closeViewer}
        />
      ) : null}
      {activeRevision && chooserNodeId ? (
        <DesignerRevisionChooser
          revision={activeRevision}
          busy={Boolean(run?.status === 'running')}
          onChoose={(choice) => {
            void chooseOutput(activeRevision.nodeId, choice).then(() => closeRevision());
          }}
          onClose={closeRevision}
        />
      ) : null}
    </div>
  );
}
