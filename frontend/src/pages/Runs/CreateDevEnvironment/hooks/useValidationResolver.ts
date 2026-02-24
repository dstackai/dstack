import { useCallback, useMemo } from 'react';
import * as yup from 'yup';

import { IRunEnvironmentFormKeys, IRunEnvironmentFormValues } from '../types';

const requiredFieldError = 'This is a required field';
const namesFieldError = 'Only latin characters, dashes, and digits';
const urlFormatError = 'Only URLs';
const workingDirFormatError = 'Must be an absolute path';
const passwordNotCopiedError = 'Copy the password before proceeding';

export const useYupValidationResolver = (template?: ITemplate) => {
    const validationSchema = useMemo(() => {
        const schema: Partial<
            Record<IRunEnvironmentFormKeys, yup.StringSchema | yup.ArraySchema<yup.StringSchema> | yup.BooleanSchema>
        > = {
            project: yup.string().required(requiredFieldError),
            template: yup.array().min(1, requiredFieldError).of(yup.string()).required(requiredFieldError),
            config_yaml: yup.string().required(requiredFieldError),
        };

        if (template?.parameters?.length) {
            template.parameters.forEach((param) => {
                switch (param.type) {
                    case 'name':
                        schema['name'] = yup.string().matches(/^[a-z][a-z0-9-]{1,40}$/, namesFieldError);
                        break;

                    case 'ide':
                        schema['ide'] = yup.string().required(requiredFieldError);
                        break;

                    case 'resources':
                        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                        // @ts-expect-error
                        schema['offer'] = yup.object().required(requiredFieldError);
                        break;

                    case 'python_or_docker':
                        schema['image'] = yup.string().when('docker', {
                            is: true,
                            then: yup.string().required(requiredFieldError),
                        });
                        break;

                    case 'repo':
                        schema['repo_url'] = yup.string().when('repo_enabled', {
                            is: true,
                            then: yup
                                .string()
                                // eslint-disable-next-line no-useless-escape
                                .matches(/^(https?):\/\/([^\s\/?#]+)((?:\/[^\s?#]*)*)(?::\/(.*))?$/i, urlFormatError)
                                .required(requiredFieldError),
                        });
                        break;

                    case 'working_dir':
                        schema['working_dir'] = yup.string().matches(/^\//, workingDirFormatError);
                        break;

                    case 'env':
                        if (param.value === '$random-password') {
                            schema['password'] = yup
                                .string()
                                .required(requiredFieldError)
                                .test(
                                    'password-copied',
                                    passwordNotCopiedError,
                                    function () {
                                        return this.parent.password_copied === true;
                                    },
                                );
                        } else {
                            schema['password'] = yup.string().required(requiredFieldError);
                        }
                        break;

                    default:
                        break;
                }
            });
        }

        return yup.object(schema);
    }, [template]);

    return useCallback(
        async (data: IRunEnvironmentFormValues) => {
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
};
