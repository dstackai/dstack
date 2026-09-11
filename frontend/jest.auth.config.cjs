module.exports = {
    rootDir: '.',
    clearMocks: true,
    testEnvironment: 'node',
    moduleDirectories: ['node_modules', 'src'],
    testMatch: ['<rootDir>/src/App/auth.test.tsx', '<rootDir>/src/services/preset.test.tsx'],
    transform: {
        '\\.[jt]sx?$': 'babel-jest',
    },
};
