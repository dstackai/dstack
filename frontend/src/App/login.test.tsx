/** @jest-environment node */
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { act, create, ReactTestRenderer } from 'react-test-renderer';
import { product } from 'product';

import { ROUTES } from 'routes';
import { useGetAuthProvidersQuery } from 'services/auth';

import { getProductConfig } from '../../product.config.cjs';
import { Login } from './Login';

type ProvidersResult = {
    data?: { name: string; enabled: boolean }[];
    isLoading: boolean;
    isError?: boolean;
};
let mockProviders: ProvidersResult;
let rendered: ReactTestRenderer | undefined;
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');

jest.mock('product', () => ({ product: { ...jest.requireActual('../../product.config.cjs').getProductConfig('factory') } }));
jest.mock('hooks', () => ({ useAppSelector: () => undefined }));
jest.mock('services/auth', () => ({ useGetAuthProvidersQuery: jest.fn(() => mockProviders) }));
jest.mock('services/user', () => ({ useGetUserDataQuery: () => ({ isFetching: false }) }));
jest.mock('./slice', () => ({ selectAuthToken: jest.fn() }));
jest.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string, options?: { product: string }) => (options ? `Welcome to ${options.product}` : key),
    }),
}));
jest.mock('PublicApp', () => ({ PublicApp: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
jest.mock('@cloudscape-design/design-tokens', () => ({ colorBackgroundHomeHeader: 'transparent' }));
jest.mock('components', () => {
    const Wrapper = ({ children }: { children: React.ReactNode }) => <>{children}</>;
    const Anchor = ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>;
    return {
        Box: ({ variant, children }: { variant?: string; children: React.ReactNode }) =>
            variant === 'h1' ? <h1>{children}</h1> : <>{children}</>,
        Container: Wrapper,
        Header: Wrapper,
        ContentLayout: ({ header, children }: { header: React.ReactNode; children: React.ReactNode }) => (
            <>
                {header}
                {children}
            </>
        ),
        Link: Anchor,
        NavigateLink: Anchor,
        SpaceBetween: Wrapper,
        Spinner: () => <p role="status">Loading providers</p>,
    };
});
jest.mock('./Login/LoginByGithub', () => ({ LoginByGithub: () => <button>GitHub</button> }));
jest.mock('./Login/EntraID/LoginByEntraID', () => ({ LoginByEntraID: () => <button>Entra</button> }));
jest.mock('./Login/LoginByGoogle', () => ({ LoginByGoogle: () => <button>Google</button> }));
jest.mock('./Login/LoginByOkta', () => ({ LoginByOkta: () => <button>Okta</button> }));
jest.mock('./Login/LoginByTokenForm', () => ({ LoginByTokenForm: () => <form>Token</form> }));
jest.mock('./Loading', () => ({ Loading: () => <p role="status">Loading user</p> }));

const renderLogin = (tokenOnly = false) => {
    act(() => {
        rendered = create(
            <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
                <Login tokenOnly={tokenOnly} />
            </MemoryRouter>,
        );
    });
    return rendered!.root;
};

beforeEach(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: { localStorage: {} } });
    Object.assign(product, getProductConfig('factory'));
    mockProviders = { data: [], isLoading: false };
});
afterEach(() => {
    act(() => rendered?.unmount());
    rendered = undefined;
});
afterAll(() => {
    if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow);
    else Reflect.deleteProperty(globalThis, 'window');
});

test.each([
    ['oss', 'dstack'],
    ['enterprise', 'dstack Enterprise'],
    ['factory', 'dstack Factory'],
    ['sky', 'dstack Sky'],
])('%s login uses its branding and the server provider list', (version, name) => {
    Object.assign(product, getProductConfig(version));
    mockProviders.data = [
        { name: 'google', enabled: true },
        { name: 'github', enabled: false },
    ];
    const view = renderLogin();
    expect(view.findByType('h1').children).toEqual([`Welcome to ${name}`]);
    expect(view.findAllByType('button').map((button) => button.children)).toEqual([['Google']]);
    expect(view.findByProps({ href: ROUTES.AUTH.TOKEN })).toBeDefined();
});

test('Factory supports all configured providers without Sky terms', () => {
    mockProviders.data = ['github', 'okta', 'entra', 'google'].map((name) => ({ name, enabled: true }));
    const view = renderLogin();
    expect(view.findAllByType('button').map((button) => button.children)).toEqual([
        ['GitHub'],
        ['Okta'],
        ['Entra'],
        ['Google'],
    ]);
    expect(view.findAllByProps({ href: 'https://dstack.ai/terms/' })).toHaveLength(0);
});

test('Sky keeps its terms with GitHub login', () => {
    Object.assign(product, getProductConfig('sky'));
    mockProviders.data = [{ name: 'github', enabled: true }];
    const view = renderLogin();
    expect(view.findByType('button').children).toEqual(['GitHub']);
    expect(view.findByProps({ href: 'https://dstack.ai/terms/' })).toBeDefined();
});

test.each([
    { data: [], isLoading: false },
    { data: [{ name: 'github', enabled: false }], isLoading: false },
    { data: [{ name: 'unknown', enabled: true }], isLoading: false },
    { isError: true, isLoading: false },
])('falls back to token login when no supported provider is available: %j', (result) => {
    mockProviders = result;
    const view = renderLogin();
    expect(view.findByType('form').children).toEqual(['Token']);
    expect(view.findAllByType('button')).toHaveLength(0);
});

test('token login remains accessible while provider discovery loads', () => {
    mockProviders = { isLoading: true };
    const view = renderLogin();
    expect(view.findByProps({ role: 'status' }).children).toEqual(['Loading providers']);
    expect(view.findByProps({ href: ROUTES.AUTH.TOKEN })).toBeDefined();
});

test('the token page does not wait for provider discovery', () => {
    mockProviders = { isLoading: true };
    const view = renderLogin(true);
    expect(view.findByType('form').children).toEqual(['Token']);
    expect(useGetAuthProvidersQuery).toHaveBeenCalledWith(undefined, { skip: true });
    expect(view.findByProps({ href: ROUTES.BASE })).toBeDefined();
});

test('Factory inherits Enterprise features and Sky inherits Factory features', () => {
    expect(getProductConfig('enterprise')).toMatchObject({ hasEvents: true, hasBilling: false, hasPresets: false });
    for (const version of ['factory', 'sky']) {
        expect(getProductConfig(version)).toMatchObject({ hasEvents: true, hasBilling: true, hasPresets: true });
    }
    expect(getProductConfig(undefined)).toMatchObject({ id: 'oss', hasEvents: false, hasBilling: false, hasPresets: false });
});
