const shellQuote = (value: string) => (/^[\w.,:/-]+$/.test(value) ? value : `'${value.replace(/'/g, "'\\''")}'`);

export const getApplyCommand = (params: URLSearchParams) => {
    const args = ['dstack apply -f .dstack.yml'];
    const add = (flag: string, value?: string | null) => {
        if (value) args.push(flag, shellQuote(value));
    };
    const gpu =
        params.get('gpu_count') === '0'
            ? '0'
            : [params.get('gpu_vendor'), params.getAll('gpu_name').join(','), params.get('gpu_count'), params.get('gpu_memory')]
                  .filter(Boolean)
                  .join(':');

    add('--gpu', gpu);
    add('--cpu', [params.get('cpu_arch'), params.get('cpu_count')].filter(Boolean).join(':'));
    add('--memory', params.get('memory'));
    ['backend', 'region', 'fleet'].forEach((key) => params.getAll(key).forEach((value) => add(`--${key}`, value)));
    add('--spot-policy', params.get('spot_policy'));
    return args.join(' ');
};
