const listSuccess: IHub[] = new Array(50).fill({}).map((i, index) => ({
    id: index,
    hub_name: `hub_${index}`,
    permission: index < 8 ? 'write' : 'read',
}));

export default {
    list: {
        success: listSuccess,
    },
};
