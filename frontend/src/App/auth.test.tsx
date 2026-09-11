/** @jest-environment node */
import React from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { act, create, ReactTestRenderer } from 'react-test-renderer';
import { Home } from 'PublicApp/Home';

import { ROUTES } from 'routes';
import { useGetUserDataQuery } from 'services/user';

import { LoginByGithub } from 'App/Login/LoginByGithub';

const mockDispatch = jest.fn();
const mockPrivateQuery = jest.fn();
let mockToken: string | undefined;
let mockUserQuery: {
    currentData?: { username: string };
    data?: { username: string };
    error?: { status: number };
    isFetching: boolean;
    isLoading: boolean;
};

jest.mock('hooks', () => ({
    useAppDispatch: () => mockDispatch,
    useAppSelector: () => mockToken,
}));

jest.mock('libs', () => ({ goToUrl: jest.fn() }));

jest.mock('services/auth', () => ({
    useGithubAuthorizeMutation: () => [jest.fn(), { isLoading: false }],
}));

jest.mock('services/user', () => ({
    useGetUserDataQuery: jest.fn((_, { skip }: { skip: boolean }) =>
        skip ? { isLoading: false, isFetching: false } : mockUserQuery,
    ),
}));

jest.mock('./slice', () => ({
    selectAuthToken: jest.fn(),
    setUserData: (payload: unknown) => ({ type: 'app/setUserData', payload }),
}));

jest.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

jest.mock('routes', () => ({
    ROUTES: {
        BASE: '/',
        RUNS: { LIST: '/runs' },
        AUTH: {
            LOGIN: '/auth',
            GITHUB_CALLBACK: '/auth/github/callback',
            OKTA_CALLBACK: '/auth/okta/callback',
            ENTRA_CALLBACK: '/auth/entra/callback',
            GOOGLE_CALLBACK: '/auth/google/callback',
            TOKEN: '/auth/token',
        },
    },
}));

jest.mock('layouts/AppLayout', () => ({
    __esModule: true,
    default: ({ children }: { children: React.ReactNode }) => {
        // The real layout starts account, project, billing, and onboarding requests when mounted.
        mockPrivateQuery();
        return <section aria-label="Account">{children}</section>;
    },
}));

jest.mock('@cloudscape-design/design-tokens', () => ({ colorBackgroundHomeHeader: 'transparent' }));

jest.mock('components', () => {
    const Wrapper = ({ children }: { children: React.ReactNode }) => <>{children}</>;
    return {
        // Render the real home and login headers without mounting their Cloudscape presentation.
        Box: ({ variant, children }: { variant?: string; children: React.ReactNode }) =>
            variant === 'h1' ? <h1>{children}</h1> : <>{children}</>,
        BreadcrumbGroup: () => null,
        Button: ({
            children,
            href,
            onFollow,
        }: {
            children: React.ReactNode;
            href?: string;
            onFollow?: (event: { preventDefault: () => void }) => void;
        }) => (
            <a href={href} onClick={onFollow}>
                {children}
            </a>
        ),
        Alert: Wrapper,
        Container: Wrapper,
        Header: Wrapper,
        NavigateLink: Wrapper,
        ContentLayout: ({ header }: { header: React.ReactNode }) => <>{header}</>,
        Grid: Wrapper,
        Link: Wrapper,
        SpaceBetween: Wrapper,
    };
});

jest.mock('PublicApp/Home/styles.module.scss', () => ({}));
jest.mock('./Login/SelfHostedLogin', () => ({ SelfHostedLogin: () => <h1>Server login</h1> }));
jest.mock('./Loading', () => ({ Loading: () => <p role="status">Loading</p> }));
jest.mock('./AuthErrorMessage', () => ({ AuthErrorMessage: () => <h1>Storage unavailable</h1> }));

const publicPaths = [ROUTES.BASE, ROUTES.AUTH.LOGIN];
const ignoredAuthPaths = Object.values(ROUTES.AUTH).filter((path) => path !== ROUTES.AUTH.LOGIN);
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
let App: React.FC;
let rendered: ReactTestRenderer | undefined;

const CurrentPath = () => <output>{useLocation().pathname}</output>;

const renderApp = (path: string) => {
    act(() => {
        rendered = create(
            <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
                <Routes>
                    <Route path={ROUTES.BASE} element={<Home />} />
                    <Route path={ROUTES.AUTH.LOGIN} element={<LoginByGithub />} />
                    <Route element={<App />}>
                        <Route path="/runs" element={<h1>Runs</h1>} />
                        {ignoredAuthPaths.map((authPath) => (
                            <Route key={authPath} path={authPath} element={<h1>Authentication page</h1>} />
                        ))}
                    </Route>
                </Routes>
                <CurrentPath />
            </MemoryRouter>,
        );
    });
    return rendered!;
};

beforeAll(() => {
    jest.replaceProperty(process, 'env', { ...process.env, UI_VERSION: 'sky' });
    Object.defineProperty(globalThis, 'window', {
        configurable: true,
        value: { localStorage: {} },
    });
    App = jest.requireActual<typeof import('./index')>('./index').default;
});

beforeEach(() => {
    Object.defineProperty(globalThis, 'window', { value: { localStorage: {} } });
    mockToken = undefined;
    mockUserQuery = { isFetching: false, isLoading: false };
});

afterEach(() => {
    act(() => rendered?.unmount());
    rendered = undefined;
});

afterAll(() => {
    jest.restoreAllMocks();
    if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow);
    else Reflect.deleteProperty(globalThis, 'window');
});

describe('Sky public and protected pages', () => {
    test.each(publicPaths)('visitors can open %s without loading account data', (path) => {
        const view = renderApp(path);

        expect(view.root.findByType('output').children).toEqual([path]);
        expect(view.root.findByType('h1').children).toEqual(['Welcome to dstack Sky']);
        expect(useGetUserDataQuery).toHaveBeenCalledWith({ token: undefined }, { skip: true });
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });

    test('the home sign-in link opens the dedicated auth page', () => {
        const view = renderApp(ROUTES.BASE);
        const signInLink = view.root.findByType('a');
        expect(signInLink.props.href).toBe(ROUTES.AUTH.LOGIN);

        act(() => signInLink.props.onClick({ preventDefault: jest.fn() }));

        expect(view.root.findByType('output').children).toEqual([ROUTES.AUTH.LOGIN]);
        expect(view.root.findByType('h1').children).toEqual(['Welcome to dstack Sky']);
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });

    test.each(publicPaths)('a validated user opening %s reaches their runs', (path) => {
        mockToken = 'valid-token';
        mockUserQuery.currentData = mockUserQuery.data = { username: 'alice' };
        const view = renderApp(path);

        expect(view.root.findByType('output').children).toEqual(['/runs']);
        expect(view.root.findByType('h1').children).toEqual(['Runs']);
        expect(mockDispatch).toHaveBeenCalledWith({ type: 'app/setUserData', payload: { username: 'alice' } });
    });

    test.each([
        [ROUTES.BASE, ROUTES.BASE],
        [ROUTES.AUTH.LOGIN, ROUTES.AUTH.LOGIN],
        [ROUTES.RUNS.LIST, ROUTES.AUTH.LOGIN],
    ])('a rejected token at %s settles on %s', (path, expectedPath) => {
        mockToken = 'expired-token';
        mockUserQuery.error = { status: 401 };
        const view = renderApp(path);

        expect(view.root.findByType('output').children).toEqual([expectedPath]);
        expect(view.root.findByType('h1').children).toEqual(['Welcome to dstack Sky']);
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });

    test.each(publicPaths)('a rejected token stays at %s even when its user data is cached', (path) => {
        mockToken = 'expired-token';
        mockUserQuery.currentData = mockUserQuery.data = { username: 'alice' };
        mockUserQuery.error = { status: 401 };
        const view = renderApp(path);

        expect(view.root.findByType('output').children).toEqual([path]);
        expect(view.root.findByType('h1').children).toEqual(['Welcome to dstack Sky']);
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });

    test('a rejected token cannot restore cached account data on a protected page', () => {
        mockToken = 'expired-token';
        mockUserQuery.currentData = mockUserQuery.data = { username: 'alice' };
        mockUserQuery.error = { status: 403 };
        const view = renderApp(ROUTES.RUNS.LIST);

        expect(view.root.findByType('output').children).toEqual([ROUTES.AUTH.LOGIN]);
        expect(mockDispatch).not.toHaveBeenCalled();
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });

    test('a visitor opening a protected page reaches the auth page', () => {
        const view = renderApp('/runs');

        expect(view.root.findByType('output').children).toEqual([ROUTES.AUTH.LOGIN]);
        expect(view.root.findByType('h1').children).toEqual(['Welcome to dstack Sky']);
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });

    test.each([...publicPaths, ROUTES.RUNS.LIST])('%s waits for token validation before showing private content', (path) => {
        mockToken = 'pending-token';
        mockUserQuery.isFetching = mockUserQuery.isLoading = true;
        const view = renderApp(path);

        expect(view.root.findByProps({ role: 'status' }).children).toEqual(['Loading']);
        expect(view.root.findByType('output').children).toEqual([path]);
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });

    test.each([...publicPaths, ROUTES.RUNS.LIST])(
        '%s waits for a new token even when data from the previous token is available',
        (path) => {
            mockToken = 'new-token';
            mockUserQuery.data = { username: 'previous-user' };
            mockUserQuery.isFetching = true;
            const view = renderApp(path);

            expect(view.root.findByProps({ role: 'status' }).children).toEqual(['Loading']);
            expect(view.root.findByType('output').children).toEqual([path]);
            expect(mockDispatch).not.toHaveBeenCalled();
            expect(mockPrivateQuery).not.toHaveBeenCalled();
        },
    );

    test.each(publicPaths)('%s remains available when local storage is unavailable', (path) => {
        Object.defineProperty(globalThis, 'window', { value: {} });
        mockToken = 'saved-token';
        const view = renderApp(path);

        expect(view.root.findByType('h1').children).toEqual(['Welcome to dstack Sky']);
        expect(useGetUserDataQuery).toHaveBeenCalledWith({ token: 'saved-token' }, { skip: true });
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });

    test.each(ignoredAuthPaths)('authentication page %s remains outside the auth guard', (path) => {
        mockToken = 'expired-token';
        mockUserQuery.error = { status: 401 };
        const view = renderApp(path);

        expect(view.root.findByType('output').children).toEqual([path]);
        expect(view.root.findByType('h1').children).toEqual(['Authentication page']);
        expect(mockPrivateQuery).not.toHaveBeenCalled();
    });
});
