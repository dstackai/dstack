import { getTokenAwareNamePatternFilterRequestParams } from './filters';

describe('filters helpers', () => {
    test('loads the full list when reopening an existing token value', () => {
        expect(
            getTokenAwareNamePatternFilterRequestParams({
                filteringText: 'main',
                limit: 100,
                propertyKey: 'project_name',
                tokens: [{ propertyKey: 'project_name', operator: '=', value: 'main' }],
            }),
        ).toEqual({ limit: 100 });
    });

    test('keeps the typed text when the value is being edited', () => {
        expect(
            getTokenAwareNamePatternFilterRequestParams({
                filteringText: 'mai',
                limit: 100,
                propertyKey: 'project_name',
                tokens: [{ propertyKey: 'project_name', operator: '=', value: 'main' }],
            }),
        ).toEqual({ limit: 100, name_pattern: 'mai' });
    });

    test('ignores matching values from other properties', () => {
        expect(
            getTokenAwareNamePatternFilterRequestParams({
                filteringText: 'main',
                limit: 100,
                propertyKey: 'project_name',
                tokens: [{ propertyKey: 'username', operator: '=', value: 'main' }],
            }),
        ).toEqual({ limit: 100, name_pattern: 'main' });
    });
});
