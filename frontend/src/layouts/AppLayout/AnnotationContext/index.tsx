import React, { PropsWithChildren, useMemo, useState } from 'react';

import { AnnotationContext as AnnotationContextGeneric, AnnotationContextProps } from 'components';

import { useAppDispatch, useAppSelector } from 'hooks';

import { selectToolsPanelState, setToolsTab } from 'App/slice';

import { overlayI18nStrings } from '../TutorialPanel/constants';
import { useTutorials } from '../TutorialPanel/hooks';

import { ITutorialItem, ToolsTabs } from 'App/types';

export const AnnotationContext: React.FC<PropsWithChildren> = ({ children }) => {
    const dispatch = useAppDispatch();
    const [activeTutorialId, setActiveTutorialId] = useState<number>();
    const { tab } = useAppSelector(selectToolsPanelState);

    const { tutorials } = useTutorials();

    const currentTutorial = useMemo(() => {
        if (!activeTutorialId) return null;

        return tutorials.find((t) => t.id === activeTutorialId) ?? null;
    }, [activeTutorialId, tutorials]);

    const onStepChange: AnnotationContextProps['onStepChange'] = () => {
        if (tab !== ToolsTabs.TUTORIAL) dispatch(setToolsTab(ToolsTabs.TUTORIAL));
    };

    return (
        <AnnotationContextGeneric
            currentTutorial={currentTutorial}
            onStepChange={onStepChange}
            onStartTutorial={(event) => {
                const tutorial = event.detail.tutorial as ITutorialItem;

                if (tutorial.startCallback) {
                    tutorial.startCallback(tutorial);
                }

                if (!tutorial.startWithoutActivation) {
                    setActiveTutorialId(tutorial.id);
                }
            }}
            onExitTutorial={() => {
                setActiveTutorialId(undefined);
            }}
            onFinish={() => {
                if (currentTutorial && currentTutorial.finishCallback) {
                    currentTutorial.finishCallback(currentTutorial);
                }

                setActiveTutorialId(undefined);
            }}
            i18nStrings={overlayI18nStrings}
        >
            {children}
        </AnnotationContextGeneric>
    );
};
