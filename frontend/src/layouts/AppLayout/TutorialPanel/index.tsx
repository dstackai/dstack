import React from 'react';

import { TutorialPanel as TutorialPanelGeneric, TutorialPanelProps } from 'components';

import { tutorialPanelI18nStrings } from './constants';
import { useTutorials } from './hooks';

export interface Props extends Partial<TutorialPanelProps> {
    test?: string;
}

export const TutorialPanel: React.FC<Props> = () => {
    const { tutorials } = useTutorials();

    return <TutorialPanelGeneric i18nStrings={tutorialPanelI18nStrings} tutorials={tutorials} />;
};
