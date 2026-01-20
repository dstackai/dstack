import React from 'react';
import { get } from 'lodash';
import * as yup from 'yup';

export const FLEET_MIN_INSTANCES_INFO = {
    header: <h2>Min number of instances</h2>,
    body: (
        <>
            <p>
                If you create a fleet here, it's recommended to set <code>Min number of instances</code> to <code>0</code>. In
                this case, <code>dstack</code> will provision instances only when you run a dev environment, task, or service.
            </p>

            <p>
                If you set <code>Min number of instances</code> above <code>0</code>, <code>dstack</code> will try to provision
                them right away. Note, setting <code>Min number of instances</code> above <code>0</code> is supported for
                VM-based backends only.
            </p>

            <p>
                To learn more about fleets, see the{' '}
                <a href={'https://dstack.ai/docs/concepts/fleets'} target="_blank">
                    documentation
                </a>
                .
            </p>
        </>
    ),
};

export const FLEET_MAX_INSTANCES_INFO = {
    header: <h2>Max number of instances</h2>,
    body: (
        <>
            <p>
                Set <code>Max number of instances</code> only if you need to limit the number of instances in the fleet.
            </p>

            <p>
                To learn more about fleets, see the{' '}
                <a href={'https://dstack.ai/docs/concepts/fleets'} target="_blank">
                    documentation
                </a>
                .
            </p>
        </>
    ),
};

export const FLEET_IDLE_DURATION_INFO = {
    header: <h2>Idle duration</h2>,
    body: (
        <>
            <p>Idle instances can be reused when you submit a dev environment, task, or service.</p>

            <p>
                Set <code>Idle duration</code> to control how long instances stay <code>idle</code> before they are terminated.
            </p>

            <p>
                Set <code>Idle duration</code> to <code>0s</code> if you want instances to be terminated immediately after they
                are no longer needed.
            </p>

            <p>
                Note, <code>dstack</code> doesn't terminates if their total number would be below{' '}
                <code>Min number of instances</code>.
            </p>

            <p>
                To learn more about fleets, see the{' '}
                <a href={'https://dstack.ai/docs/concepts/fleets'} target="_blank">
                    documentation
                </a>
                .
            </p>
        </>
    ),
};

const requiredFieldError = 'This is required field';
const numberFieldError = 'This is number field';

export const getMinInstancesValidator = (maxInstancesFieldPath: string) =>
    yup
        .number()
        .required(requiredFieldError)
        .typeError(numberFieldError)
        .min(0)
        .test('is-smaller-than-max', 'The minimum value must be less than the maximum value.', (value, context) => {
            const maxInstances = get(context.parent, maxInstancesFieldPath);

            if (typeof maxInstances !== 'number' || typeof value !== 'number') {
                return true;
            }

            return value <= maxInstances;
        });

export const getMaxInstancesValidator = (minInstancesFieldPath: string) =>
    yup
        .number()
        .typeError(numberFieldError)
        .min(1)
        .test('is-greater-than-min', 'The maximum value must be greater than the minimum value', (value, context) => {
            const minInstances = get(context.parent, minInstancesFieldPath);

            if (typeof minInstances !== 'number' || typeof value !== 'number') {
                return true;
            }

            return value >= minInstances;
        });

export const idleDurationValidator = yup.string().matches(/^\d+[smhdw]$/, 'Invalid duration');
