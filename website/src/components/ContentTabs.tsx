import { KeyboardEvent, ReactNode, useId, useRef, useState } from 'react';

type ContentTab = {
  id: string;
  label: string;
  content: ReactNode;
  footer?: ReactNode;
  className?: string;
};

export function ContentTabs({ ariaLabel, className, tabs }: {
  ariaLabel: string;
  className?: string;
  tabs: ContentTab[];
}) {
  const [activeTabId, setActiveTabId] = useState(tabs[0].id);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();
  const activeTab = tabs.find(tab => tab.id === activeTabId) ?? tabs[0];

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const nextIndex = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index + tabs.length - 1) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    }[event.key];
    if (nextIndex === undefined) return;
    event.preventDefault();
    setActiveTabId(tabs[nextIndex].id);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <div className={['gs-box', className, activeTab.className].filter(Boolean).join(' ')}>
      <div className="gs-tabs" role="tablist" aria-label={ariaLabel}>
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            ref={element => { tabRefs.current[index] = element; }}
            id={`${id}-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={activeTab.id === tab.id}
            aria-controls={`${id}-panel`}
            tabIndex={activeTab.id === tab.id ? 0 : -1}
            className={`gs-tab${activeTab.id === tab.id ? ' gs-tab--on' : ''}`}
            onClick={() => setActiveTabId(tab.id)}
            onKeyDown={event => onTabKeyDown(event, index)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        className="gs-skybody"
        id={`${id}-panel`}
        role="tabpanel"
        aria-labelledby={`${id}-${activeTab.id}`}
        tabIndex={0}
      >
        {activeTab.content}
      </div>
      {activeTab.footer != null && (
        <div className="gs-boxfoot">
          {activeTab.footer}
        </div>
      )}
    </div>
  );
}
