const successInfo: IUserSmall = {
    user_name: 'test_user',
};

const failedInfo = { status: 403, error: 'Forbidden' };

function broofa() {
    return 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0,
            v = c == 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

const successList: IUser[] = new Array(50).fill({}).map((i, index) => ({
    id: index,
    user_name: `user_${index}`,
    token: broofa(),
    email: `user_${index}@email.ru`,
    permission_level: Math.random() > 0.5 ? 'Read' : 'Admin',
}));

export default {
    info: {
        success: successInfo,
        failed: failedInfo,
    },

    list: {
        success: successList,
    },
};
