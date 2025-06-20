import type { PropertyFilterProps } from 'components';

export const tokensToRequestParams = <RequestParamsKeys extends string>(
    tokens: PropertyFilterProps.Query['tokens'],
    onlyActive?: boolean,
) => {
    const params: Record<RequestParamsKeys | 'only_active', string> = tokens.reduce((acc, token) => {
        if (token.propertyKey) {
            acc[token.propertyKey as RequestParamsKeys] = token.value;
        }

        return acc;
    }, {} as Record<RequestParamsKeys | 'only_active', string>);

    if (onlyActive) {
        params['only_active'] = 'true';
    }

    return params;
};

export const EMPTY_QUERY: PropertyFilterProps.Query = {
    tokens: [],
    operation: 'and',
};

export const requestParamsToTokens = <RequestParamsKeys extends string>({
    searchParams,
    filterKeys,
}: {
    searchParams: URLSearchParams;
    filterKeys: Record<string, RequestParamsKeys>;
}): PropertyFilterProps.Query => {
    const tokens = [];

    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore
    for (const [paramKey, paramValue] of searchParams.entries()) {
        if (Object.values(filterKeys).includes(paramKey)) {
            tokens.push({ propertyKey: paramKey, operator: '=', value: paramValue });
        }
    }

    if (!tokens.length) {
        return EMPTY_QUERY;
    }

    return {
        ...EMPTY_QUERY,
        tokens,
    };
};
