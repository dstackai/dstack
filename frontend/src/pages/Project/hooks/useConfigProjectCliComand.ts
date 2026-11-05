import { useState } from 'react';

import { useAppSelector } from 'hooks';
import { copyToClipboard, TOKEN_MASK } from 'libs';

import { selectAuthToken } from 'App/slice';

type Args = {
    projectName: string;
};
export const useConfigProjectCliCommand = ({ projectName }: Args) => {
    const currentUserToken = useAppSelector(selectAuthToken);
    const [isTokenVisible, setIsTokenVisible] = useState(false);

    const getCliCommand = (token?: string) =>
        `dstack project add \\\n  --url ${location.origin} \\\n  --name ${projectName} \\\n  --token ${token}`;

    const cliCommand = getCliCommand(isTokenVisible ? currentUserToken : TOKEN_MASK);

    const copyCliCommand = () => {
        copyToClipboard(getCliCommand(currentUserToken));
    };

    return [cliCommand, copyCliCommand, isTokenVisible, setIsTokenVisible] as const;
};
