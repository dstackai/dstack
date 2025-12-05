function bufferToHex(buffer: ArrayBuffer): string {
    return Array.from(new Uint8Array(buffer))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
}

export async function slugify(prefix: string, unique_key: string, hash_size: number = 8): Promise<string> {
    const encoder = new TextEncoder();
    const data = encoder.encode(unique_key);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const fullHash = bufferToHex(hashBuffer);
    return `${prefix}-${fullHash.substring(0, hash_size)}`;
}

export function getRepoName(url: string): string {
    const cleaned = url
        .replace(/^https?:\/\//i, '')
        .replace(/:\/(\S*)/, '')
        .replace(/\/+$/, '')
        .replace(/\.git$/, '');
    const parts = cleaned.split('/').filter(Boolean);
    return parts.length ? parts[parts.length - 1] : '';
}

export function getPathWithoutProtocol(url: string): string {
    return url.replace(/^https?:\/\//i, '');
}

export function getRepoUrlWithOutDir(url: string): string {
    const parsedUrl = url.match(/^([^:]+(?::[^:]+)?)/)?.[1];

    return parsedUrl ?? url;
}

export function getRepoDirFromUrl(url: string): string | undefined {
    const dirName = url.replace(/^https?:\/\//i, '').match(/:\/(\S*)/)?.[1];

    return dirName ? `/${dirName}` : undefined;
}
