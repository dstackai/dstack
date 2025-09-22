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

export type RequestParam = string | { min: number } | { max: number };

const convertTokenValueToRequestParam = (token: PropertyFilterProps.Query['tokens'][number]): RequestParam => {
    const { value, operator } = token;

    if (operator === '>=') {
        return { min: Number(value) };
    }

    if (operator === '<=') {
        return { max: Number(value) };
    }

    return value;
};

export const tokensToRequestParams = <RequestParamsKeys extends string>({
    tokens,
    arrayFieldKeys,
}: {
    tokens: PropertyFilterProps.Query['tokens'];
    arrayFieldKeys?: RequestParamsKeys[];
}) => {
    return tokens.reduce<Record<RequestParamsKeys, RequestParam | string[]>>(
        (acc, token) => {
            const propertyKey = token.propertyKey as RequestParamsKeys;

            if (!propertyKey) {
                return acc;
            }

            const convertedValue = convertTokenValueToRequestParam(token);

            if (arrayFieldKeys?.includes(propertyKey)) {
                if (Array.isArray(acc[propertyKey])) {
                    acc[propertyKey].push(convertedValue as string);
                } else {
                    acc[propertyKey] = [convertedValue as string];
                }

                return acc;
            }

            acc[propertyKey] = convertedValue;

            return acc;
        },
        {} as Record<RequestParamsKeys, RequestParam>,
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

export const requestParamsToArray = <Key extends string>({
    searchParams,
    paramName,
}: {
    searchParams: URLSearchParams;
    paramName: Key;
}) => {
    const paramValues: string[] = [];
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore

    for (const [paramKey, paramValue] of searchParams.entries()) {
        if (paramKey === paramName) {
            paramValues.push(paramValue);
        }
    }

    return paramValues;
};
