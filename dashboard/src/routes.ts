export const main = () => '/';

const isOnLanding = process.env.LANDING === 'on';

//app auth
export const login = isOnLanding ? () => '/login' : main;
export const signUp = () => '/signup';
