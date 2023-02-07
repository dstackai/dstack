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
    user_name: `user_${index}`,
    token: broofa(),
    global_role: (function () {
        const val = Math.random();
        let permission: TUserRole = 'read';

        switch (true) {
            case val > 0.65:
                permission = 'read';
                break;
            case val <= 0.65 && val >= 0.3:
                permission = 'admin';
                break;
            case val < 0.3:
                permission = 'run';
                break;
        }

        return permission;
    })(),
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
