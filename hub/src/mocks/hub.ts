const listSuccess: IHub[] = new Array(50).fill({}).map((i, index) => ({
    id: index,
    name: `hub_${index}`,
}));

export default {
    list: {
        success: listSuccess,
    },
};
