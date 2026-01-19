import React from 'react';
import { get } from 'lodash';
import * as yup from 'yup';

export const FLEET_MIN_INSTANCES_INFO = {
    header: <h2>Min number of instances</h2>,
    body: (
        <>
            <p>Some text</p>
        </>
    ),
};

export const FLEET_MAX_INSTANCES_INFO = {
    header: <h2>Max number of instances</h2>,
    body: (
        <>
            <p>Some text</p>
        </>
    ),
};

export const FLEET_IDLE_DURATION_INFO = {
    header: <h2>Idle duration</h2>,
    body: (
        <>
            <p>Some text</p>
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

export const idleDurationValidator = yup.string().matches(/^[1-9]\d*[smhdw]$/, 'Invalid duration');
