module.exports = {
    rootDir: '.',
    clearMocks: true,
    testEnvironment: 'node',
    moduleDirectories: ['node_modules', 'src'],
    testMatch: [
        '<rootDir>/src/App/auth.test.tsx',
        '<rootDir>/src/App/login.test.tsx',
        '<rootDir>/src/services/preset.test.tsx',
        '<rootDir>/src/services/run.test.ts',
        '<rootDir>/src/libs/run.test.ts',
        '<rootDir>/src/pages/Models/**/*.test.{ts,tsx}',
    ],
    transform: {
        '\\.[jt]sx?$': 'babel-jest',
    },
};
