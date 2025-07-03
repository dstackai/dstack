import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

import {
    DISCORD_URL,
    QUICK_START_URL,
    // TALLY_FORM_ID
} from 'consts';
import { useAppDispatch, useAppSelector } from 'hooks';
import { goToUrl } from 'libs';
import { useGetRunsQuery } from 'services/run';
import { useGetUserBillingInfoQuery } from 'services/user';

import { openTutorialPanel, selectTutorialPanel, selectUserName, updateTutorialPanelState } from 'App/slice';

import { useSideNavigation } from '../hooks';
import {
    BILLING_TUTORIAL,
    CONFIGURE_CLI_TUTORIAL,
    // CREDITS_TUTORIAL,
    JOIN_DISCORD_TUTORIAL,
    QUICKSTART_TUTORIAL,
} from './constants';

import { ITutorialItem } from 'App/types';

export const useTutorials = () => {
    const navigate = useNavigate();
    const dispatch = useAppDispatch();
    const { billingUrl } = useSideNavigation();
    const useName = useAppSelector(selectUserName);
    const { billingCompleted, configureCLICompleted, discordCompleted, tallyCompleted, quickStartCompleted, hideStartUp } =
        useAppSelector(selectTutorialPanel);

    const { data: userBillingData } = useGetUserBillingInfoQuery({ username: useName ?? '' }, { skip: !useName });
    const { data: runsData } = useGetRunsQuery({
        limit: 1,
    });

    const completeIsChecked = useRef<boolean>(false);

    useEffect(() => {
        if (userBillingData && runsData && !completeIsChecked.current) {
            const billingCompleted = userBillingData.balance > 0;
            const configureCLICompleted = runsData.length > 0;

            let tempHideStartUp = hideStartUp;

            if (hideStartUp === null) {
                tempHideStartUp = billingCompleted && configureCLICompleted;
            }

            // Set hideStartUp without updating localstorage
            dispatch(updateTutorialPanelState({ billingCompleted, configureCLICompleted, hideStartUp: tempHideStartUp }));

            if (!tempHideStartUp && process.env.UI_VERSION === 'sky') {
                dispatch(openTutorialPanel());
            }

            completeIsChecked.current = true;
        }
    }, [userBillingData, runsData]);

    const startBillingTutorial = useCallback(() => {
        navigate(billingUrl);
    }, [billingUrl]);

    const finishBillingTutorial = useCallback(() => {
        dispatch(updateTutorialPanelState({ billingCompleted: true }));
    }, []);

    const startConfigCliTutorial = useCallback(() => {}, [billingUrl]);

    const finishConfigCliTutorial = useCallback(() => {
        dispatch(updateTutorialPanelState({ configureCLICompleted: true }));
    }, []);

    const startDiscordTutorial = useCallback(() => {
        goToUrl(DISCORD_URL, true);
        dispatch(updateTutorialPanelState({ discordCompleted: true }));
    }, []);

    const startQuickStartTutorial = useCallback(() => {
        goToUrl(QUICK_START_URL, true);
        dispatch(updateTutorialPanelState({ quickStartCompleted: true }));
    }, []);

    // const startCreditsTutorial = useCallback(() => {
    //     if (typeof Tally !== 'undefined') {
    //         Tally.openPopup(TALLY_FORM_ID);
    //         dispatch(updateTutorialPanelState({ tallyCompleted: true }));
    //     }
    // }, []);

    const tutorials = useMemo<ITutorialItem[]>(() => {
        return [
            // {
            //     ...CREDITS_TUTORIAL,
            //     id: 1,
            //     startWithoutActivation: true,
            //     completed: tallyCompleted,
            //     startCallback: startCreditsTutorial,
            // },

            {
                ...CONFIGURE_CLI_TUTORIAL,
                id: 2,
                completed: configureCLICompleted,
                startCallback: startConfigCliTutorial,
                finishCallback: finishConfigCliTutorial,
            },

            {
                ...BILLING_TUTORIAL,
                id: 3,
                completed: billingCompleted,
                startCallback: startBillingTutorial,
                finishCallback: finishBillingTutorial,
            },

            {
                ...QUICKSTART_TUTORIAL,
                id: 4,
                startWithoutActivation: true,
                completed: quickStartCompleted,
                startCallback: startQuickStartTutorial,
            },

            {
                ...JOIN_DISCORD_TUTORIAL,
                id: 5,
                startWithoutActivation: true,
                completed: discordCompleted,
                startCallback: startDiscordTutorial,
            },
        ];
    }, [
        billingUrl,
        quickStartCompleted,
        discordCompleted,
        tallyCompleted,
        billingCompleted,
        configureCLICompleted,
        finishBillingTutorial,
        finishConfigCliTutorial,
    ]);

    return { tutorials } as const;
};
