global.requestAnimationFrame = (callback): number => {
    setTimeout(callback, 0);
    return 0;
};
