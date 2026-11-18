/** @jest-environment node */
import React from 'react';
import { act, create, ReactTestRenderer } from 'react-test-renderer';

import { copyToClipboard, TOKEN_MASK } from 'libs';

import { useConfigProjectCliCommand } from './useConfigProjectCliComand';

jest.mock('libs', () => ({ ...jest.requireActual('libs'), copyToClipboard: jest.fn() }));
jest.mock('App/slice', () => ({ selectAuthToken: jest.fn() }));
jest.mock('hooks', () => ({ useAppSelector: () => 'secret-token' }));

let result: ReturnType<typeof useConfigProjectCliCommand>;
let renderer: ReactTestRenderer;

const Harness = () => {
    result = useConfigProjectCliCommand({ projectName: 'main' });
    return null;
};

beforeAll(() => {
    Object.defineProperty(globalThis, 'location', { value: { origin: 'https://dstack.example' }, configurable: true });
});

beforeEach(() => {
    jest.mocked(copyToClipboard).mockReset();
    act(() => {
        renderer = create(<Harness />);
    });
});

afterEach(() => act(() => renderer.unmount()));

describe('useConfigProjectCliCommand', () => {
    test('hides the token by default', () => {
        const [cliCommand] = result;

        expect(cliCommand).toContain(`--token ${TOKEN_MASK}`);
        expect(cliCommand).not.toContain('secret-token');
    });

    test('shows the token when requested', () => {
        act(() => result[3](true));

        const [cliCommand, , isTokenVisible] = result;
        expect(isTokenVisible).toBe(true);
        expect(cliCommand).toContain('--token secret-token');
    });

    test('copies the command with the real token while it is hidden', () => {
        const [, copyCliCommand] = result;

        copyCliCommand();

        expect(copyToClipboard).toHaveBeenCalledWith(expect.stringContaining('--token secret-token'));
    });
});
