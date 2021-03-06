export default {
    notFound: () => '/404',
    auth: () => '/auth',
    authLogin: () => '/auth/login',
    verifyUser: () => '/auth/verify',
    authSignUp: () => '/auth/signup',
    authForgetPassword: () => '/auth/forget-password',
    authResetPassword: () => '/auth/reset-password',
    confirmEmailMessage: () => '/auth/confirm-message',

    // stacks
    stacks: () => '/',
    userStacks: (user = ':user') => `/${user}`,
    categoryStacks: (category = ':category(applications|models)') => `/${category}`,
    categoryUserStacks: (user = ':user', category = ':category(applications|models)') => `/${user}/${category}`,
    stackDetails: (user = ':user', id = ':stack') => `/${user}/${id}` + (id === ':stack' ? '+' : ''),

    //reports
    reports: (user = ':user') => `/${user}/d`,
    reportsDetails: (user = ':user', id = ':id') => `/${user}/d/${id}`,

    // jobs
    jobs: (user = ':user') => `/${user}/j`,
    jobsDetails: (user = ':user', id = ':id') => `/${user}/j/${id}`,

    // settings
    settings: () => '/settings',
    accountSettings: () => '/settings/account',
    usersSettings: () => '/settings/users',
};
