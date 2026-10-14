/**
 * Shared design-task create helpers.
 *
 * Mirrors the work-mode pattern from Design&work alignment (#12 / 9989a5e):
 * bind to the sidebar's selected real project when present, otherwise the
 * virtual default mount (default_design after the SwarmFlow split).
 */

import {
  normalizeDesignProjectId,
  useWorkspaceStore,
} from '../../stores/workspaceStore';
import type { Session } from '../../types';
import type { DesignerWorkspace } from './designerGraphClient';

/** Real project id from the sidebar selection, if any. */
export function resolveDesignCreateProjectId(): string | undefined {
  const selected = useWorkspaceStore.getState().selectedProject;
  if (!selected || selected.is_default) return undefined;
  return selected.project_id;
}

/** After designer.workspace.create: refresh list, expand, and seed the sidebar. */
export async function applyCreatedDesignWorkspace(
  workspace: DesignerWorkspace,
  options?: { titleFallback?: string },
): Promise<{ projectId: string; sessionId: string }> {
  const projectId = normalizeDesignProjectId(workspace.project.project_id);
  const sessionId = workspace.session.session_id;
  const title = workspace.session.title || options?.titleFallback || sessionId;
  const store = useWorkspaceStore.getState();
  await store.loadProjects();
  const project = store.projects.find((item) => item.project_id === projectId);
  if (project) {
    store.setSelectedProject(project.is_default ? null : project);
  }
  if (!store.expandedProjectIds[projectId]) {
    store.toggleProjectExpanded(projectId);
  }
  const seed: Session = {
    session_id: sessionId,
    title,
    display_title: title,
    project_id: projectId,
    project_dir: workspace.session.project_dir || '',
    work_mode: 'design',
    mode: 'team',
    status: 'active',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    last_user_message_at: Date.now() / 1000,
    message_count: 0,
  };
  store.upsertSession(seed, { isNew: true });
  await store.loadProjectSessions(projectId);
  return { projectId, sessionId };
}
