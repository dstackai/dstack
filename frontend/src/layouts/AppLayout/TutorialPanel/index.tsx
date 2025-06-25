import React, { useLayoutEffect, useRef } from 'react';
import { createRoot, Root } from 'react-dom/client';

import { Box, Toggle, TutorialPanel as TutorialPanelGeneric, TutorialPanelProps } from 'components';

import { useAppDispatch, useAppSelector } from 'hooks';

import { selectTutorialPanel, setHideAtStartup } from 'App/slice';

import { tutorialPanelI18nStrings } from './constants';
import { useTutorials } from './hooks';

export interface Props extends Partial<TutorialPanelProps> {
    test?: string;
}

export const TutorialPanel: React.FC<Props> = () => {
    const dispatch = useAppDispatch();
    const { tutorials } = useTutorials();
    const tutorialRootRef = useRef<Root>(null);
    const { hideStartUp } = useAppSelector(selectTutorialPanel);

    const onChangeShowStartUp = (value: boolean) => {
        dispatch(setHideAtStartup(!value));
    };

    const renderShowAtStartup = () => {
        return (
            <Box padding={{ vertical: 'm' }}>
                <Toggle onChange={({ detail }) => onChangeShowStartUp(detail.checked)} checked={!hideStartUp}>
                    Show at startup
                </Toggle>
            </Box>
        );
    };

    useLayoutEffect(() => {
        const tutorialPanelElement = document.querySelector('[class*="awsui_tutorial-panel"]');

        if (tutorialPanelElement && !tutorialRootRef.current) {
            const divElement = document.createElement('div');
            tutorialPanelElement.appendChild(divElement);
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            tutorialRootRef.current = createRoot(divElement);
        }

        if (tutorialRootRef.current) {
            tutorialRootRef.current.render(renderShowAtStartup());
        }
    }, [hideStartUp]);

    return <TutorialPanelGeneric i18nStrings={tutorialPanelI18nStrings} tutorials={tutorials} />;
};
