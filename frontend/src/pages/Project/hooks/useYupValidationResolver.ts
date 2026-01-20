import { useCallback } from 'react';
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-expect-error
export function useYupValidationResolver<TData>(validationSchema) {
    return useCallback(
        async (data: TData) => {
            try {
                const values = await validationSchema.validate(data, {
                    abortEarly: false,
                });

                return {
                    values,
                    errors: {},
                };
            } catch (errors) {
                return {
                    values: {},
                    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                    // @ts-expect-error
                    errors: errors.inner.reduce(
                        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                        // @ts-expect-error
                        (allErrors, currentError) => ({
                            ...allErrors,
                            [currentError.path]: {
                                type: currentError.type ?? 'validation',
                                message: currentError.message,
                            },
                        }),
                        {},
                    ),
                };
            }
        },
        [validationSchema],
    );
}
