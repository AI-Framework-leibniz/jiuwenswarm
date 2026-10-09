import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  designerWorkspaceClient,
  type DesignerTrajectoryEvent,
} from '../designerGraphClient';

type DesignerTrajectoryPanelProps = {
  projectId: string;
  sessionId: string;
  graphId?: string;
  running?: boolean;
  onClose: () => void;
};

function formatEventTime(ts: number | undefined): string {
  if (!ts) return '';
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function DesignerTrajectoryPanel({
  projectId,
  sessionId,
  graphId,
  running = false,
  onClose,
}: DesignerTrajectoryPanelProps) {
  const { t } = useTranslation();
  const [events, setEvents] = useState<DesignerTrajectoryEvent[]>([]);

  useEffect(() => {
    if (!projectId || !sessionId) return;
    let cancelled = false;
    const load = () => {
      void designerWorkspaceClient.trajectory({ projectId, sessionId })
        .then((payload) => {
          if (cancelled) return;
          if (graphId && payload.graph_id && payload.graph_id !== graphId) return;
          setEvents(payload.events || []);
        })
        .catch(() => {
          if (!cancelled) setEvents([]);
        });
    };
    load();
    if (!running) {
      return () => {
        cancelled = true;
      };
    }
    const timer = window.setInterval(load, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [graphId, projectId, running, sessionId]);

  return (
    <aside className="designer-trajectory" data-testid="designer-trajectory-panel">
      <header className="designer-trajectory__header">
        <h2 className="designer-trajectory__title">{t('designer.trajectory.title')}</h2>
        <button
          type="button"
          className="designer-trajectory__close"
          onClick={onClose}
          data-testid="designer-trajectory-hide"
        >
          {t('designer.trajectory.hide')}
        </button>
      </header>
      {events.length === 0 ? (
        <p className="designer-trajectory__empty" data-testid="designer-trajectory-empty">
          {t('designer.trajectory.empty')}
        </p>
      ) : (
        <ol className="designer-trajectory__list">
          {events.map((event, index) => (
            <li
              key={`${event.run_id || 'run'}-${event.ts_ms || index}-${event.kind}-${index}`}
              className={`designer-trajectory__item${event.status === 'error' ? ' is-error' : ''}`}
              data-testid="designer-trajectory-event"
            >
              <span className="designer-trajectory__time">{formatEventTime(event.ts_ms)}</span>
              <span className="designer-trajectory__summary">
                {event.summary || event.action || event.kind}
              </span>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
