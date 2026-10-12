import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DesignerAssetsPanel } from './DesignerAssetsPanel';

export function DesignerAssetsSidebar() {
  const { t } = useTranslation();
  const [scope, setScope] = useState<'session' | 'project'>('session');

  return (
    <aside
      className="designer-assets-sidebar"
      aria-label={t('designer.sidebar.canvas')}
      data-testid="designer-assets-sidebar"
    >
      <div className="designer-assets-sidebar__header">
        <h2 className="designer-assets-sidebar__title" data-testid="designer-assets-sidebar-title">
          {scope === 'project' ? t('designer.sidebar.project') : t('designer.sidebar.canvas')}
        </h2>
        <div className="designer-assets-sidebar__scopes" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={scope === 'session'}
            className={scope === 'session' ? 'is-active' : undefined}
            data-testid="designer-assets-scope-session"
            onClick={() => setScope('session')}
          >
            {t('designer.sidebar.canvas')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={scope === 'project'}
            className={scope === 'project' ? 'is-active' : undefined}
            data-testid="designer-assets-scope-project"
            onClick={() => setScope('project')}
          >
            {t('designer.sidebar.project')}
          </button>
        </div>
      </div>
      <DesignerAssetsPanel scope={scope} />
    </aside>
  );
}
