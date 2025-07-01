import type { PropertyFilterProps } from 'components';

export const tokensToSearchParams = <RequestParamsKeys extends string>(
    tokens: PropertyFilterProps.Query['tokens'],
    onlyActive?: boolean,
) => {
    const params = new URLSearchParams();

    tokens.forEach((token) => {
        if (token.propertyKey) {
            params.append(token.propertyKey as RequestParamsKeys, token.value);
        }
    });

    if (onlyActive) {
        params.append('only_active', 'true');
    }

    return params;
};

export const tokensToRequestParams = <RequestParamsKeys extends string>({
    tokens,
    arrayFieldKeys,
}: {
    tokens: PropertyFilterProps.Query['tokens'];
    arrayFieldKeys?: RequestParamsKeys[];
}) => {
    return tokens.reduce<Record<RequestParamsKeys, string | string[]>>(
        (acc, token) => {
            const propertyKey = token.propertyKey as RequestParamsKeys;

            if (!propertyKey) {
                return acc;
            }

            if (arrayFieldKeys?.includes(propertyKey)) {
                if (Array.isArray(acc[propertyKey])) {
                    acc[propertyKey].push(token.value);
                } else {
                    acc[propertyKey] = [token.value];
                }

                return acc;
            }

            acc[propertyKey] = token.value;

            return acc;
        },
        {} as Record<RequestParamsKeys, string>,
    );
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
