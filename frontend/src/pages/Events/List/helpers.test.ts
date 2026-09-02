import { getEventTargetTypeFilteringOption } from './helpers';

describe('event filter helpers', () => {
    test.each([
        [{ label: 'Instance', value: 'instance' }],
        [{ label: 'project', value: 'project' }],
        [{ label: 'Unknown', value: 'unknown' }],
        [{ label: '', value: '' }],
    ])('keeps the %s display label while using the API value', (targetType) => {
        expect(getEventTargetTypeFilteringOption(targetType, 'include_target_types')).toEqual({
            propertyKey: 'include_target_types',
            label: targetType.label,
            value: targetType.value,
        });
    });
});
