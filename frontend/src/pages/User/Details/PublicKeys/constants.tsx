import React from 'react';

export const SSH_KEYS_INFO = {
    header: <h2>SSH Keys</h2>,
    body: (
        <>
            <p>
                These SSH keys are for direct SSH access to runs from your local client without running{' '}
                <code>dstack attach</code>.
            </p>
            <p>
                If you use <code>dstack attach</code> (or attached <code>dstack apply</code>), <code>dstack</code> manages a
                client SSH key and local SSH shortcut automatically. In that workflow, you usually don&apos;t need to upload
                additional keys.
            </p>
            <p>
                Without <code>dstack attach</code>, <code>{'ssh <run-name>'}</code> is not configured on your machine. Use the
                full proxied SSH connection details from run details instead. This requires SSH proxy to be enabled on the
                server.
            </p>
            <p>
                To authorize this direct path, upload your public key (for example, <code>~/.ssh/id_ed25519.pub</code>), and
                keep the matching private key on your client. Uploaded keys are additional and do not replace the system-managed
                key used by <code>dstack attach</code>/<code>dstack apply</code>.
            </p>
        </>
    ),
};
