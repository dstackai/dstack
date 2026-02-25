const UPPERCASE_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const LOWERCASE_LETTERS = 'abcdefghijklmnopqrstuvwxyz';
const NUMBERS = '0123456789';
const SPECIAL_CHARACTERS = '@#$^_+-';

interface PasswordOptions {
    length: number;
    includeUppercase?: boolean;
    includeLowercase?: boolean;
    includeNumbers?: boolean;
    includeSpecial?: boolean;
}
function generatePassword(options: PasswordOptions): string {
    const { length, includeUppercase = true, includeLowercase = true, includeNumbers = true, includeSpecial = true } = options;

    let allowedChars = '';

    if (includeUppercase) allowedChars += UPPERCASE_LETTERS;
    if (includeLowercase) allowedChars += LOWERCASE_LETTERS;
    if (includeNumbers) allowedChars += NUMBERS;
    if (includeSpecial) allowedChars += SPECIAL_CHARACTERS;

    if (allowedChars.length === 0) {
        throw new Error('No character type is selected for the password');
    }

    if (length < 4) {
        throw new Error('The password must be at least 4 characters long');
    }

    let password = '';
    const randomValues = new Uint32Array(length);

    crypto.getRandomValues(randomValues);

    for (let i = 0; i < length; i++) {
        const randomIndex = randomValues[i] % allowedChars.length;
        password += allowedChars[randomIndex];
    }

    return password;
}

function generateSimplePassword(length: number): string {
    const ALL_CHARS = UPPERCASE_LETTERS + LOWERCASE_LETTERS + NUMBERS + SPECIAL_CHARACTERS;

    if (length < 1) {
        throw new Error('The password length must be a positive number');
    }

    let password = '';
    const randomValues = new Uint32Array(length);

    crypto.getRandomValues(randomValues);

    for (let i = 0; i < length; i++) {
        const randomIndex = randomValues[i] % ALL_CHARS.length;
        password += ALL_CHARS[randomIndex];
    }

    return password;
}

function generateSecurePassword(length: number): string {
    if (length < 4) {
        throw new Error('The minimum length for a secure password is 4 characters');
    }

    const charSets = [UPPERCASE_LETTERS, LOWERCASE_LETTERS, NUMBERS, SPECIAL_CHARACTERS];

    let password = '';
    password += UPPERCASE_LETTERS[Math.floor(Math.random() * UPPERCASE_LETTERS.length)];
    password += LOWERCASE_LETTERS[Math.floor(Math.random() * LOWERCASE_LETTERS.length)];
    password += NUMBERS[Math.floor(Math.random() * NUMBERS.length)];
    password += SPECIAL_CHARACTERS[Math.floor(Math.random() * SPECIAL_CHARACTERS.length)];

    const ALL_CHARS = charSets.join('');
    const remainingLength = length - 4;

    if (remainingLength > 0) {
        const randomValues = new Uint32Array(remainingLength);
        crypto.getRandomValues(randomValues);

        for (let i = 0; i < remainingLength; i++) {
            const randomIndex = randomValues[i] % ALL_CHARS.length;
            password += ALL_CHARS[randomIndex];
        }
    }

    return password
        .split('')
        .sort(() => Math.random() - 0.5)
        .join('');
}

export {
    generatePassword,
    generateSimplePassword,
    generateSecurePassword,
    UPPERCASE_LETTERS,
    LOWERCASE_LETTERS,
    NUMBERS,
    SPECIAL_CHARACTERS,
};

export type { PasswordOptions };
