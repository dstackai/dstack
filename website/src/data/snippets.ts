// Code snippets shown in the home page tab groups: cloud backends and on-prem
// clusters (YAML), plus the open-source install commands (shell). The first line
// of each YAML snippet is a comment naming the file it represents.
const BACKEND_HEADER = '# ~/.dstack/server/config.yml';
const FLEET_HEADER = '# my-fleet.dstack.yml';

export const backendConfigs = (
  [
    {
      id: 'aws',
      label: 'AWS',
      yaml: `projects:
  - name: main
    backends:
      - type: aws
        creds:
          type: access_key
          access_key: KKAAUKLIZ5EHKICAOASV
          secret_key: pn158lMqSBJiySwpQ9ubwmI6VUU3/W2fdJdFwfgO`,
    },
    {
      id: 'gcp',
      label: 'GCP',
      yaml: `projects:
  - name: main
    backends:
      - type: gcp
        project_id: my-gcp-project
        creds:
          type: service_account
          filename: ~/.dstack/server/gcp-024ed630eab5.json`,
    },
    {
      id: 'lambda',
      label: 'Lambda',
      yaml: `projects:
  - name: main
    backends:
      - type: lambda
        creds:
          type: api_key
          api_key: eersct_yrpiey-naaeedst-tk-_cb6ba38e1128464aea9bcc619e4ba2a5.iijPMi07obgt6TZ87v5qAEj61RVxhd0p`,
    },
    {
      id: 'nebius',
      label: 'Nebius',
      yaml: `projects:
  - name: main
    backends:
      - type: nebius
        creds:
          type: service_account
          service_account_id: serviceaccount-e00dhnv9ftgb3cqmej
          public_key_id: publickey-e00ngaex668htswqy4
          private_key_file: ~/path/to/key.pem`,
    },
    {
      id: 'crusoe',
      label: 'Crusoe',
      yaml: `projects:
  - name: main
    backends:
      - type: crusoe
        project_id: my-crusoe-project
        creds:
          type: access_key
          access_key: CRUSOE3X9PLANROAQ2KZ
          secret_key: 8fJqV2mWcR7tY1nB6xD4eL0pS5gH3aZ9uK7iO2wQ`,
    },
    {
      id: 'runpod',
      label: 'RunPod',
      yaml: `projects:
  - name: main
    backends:
      - type: runpod
        creds:
          type: api_key
          api_key: US9XTPDIV8AR42MMINY8TCKRB8S4E7LNRQ6CAUQ9`,
    },
    {
      id: 'azure',
      label: 'Azure',
      yaml: `projects:
  - name: main
    backends:
      - type: azure
        subscription_id: 06c82ce3-28ff-4285-a146-c5e981a9d808
        tenant_id: f84a7584-88e4-4fd2-8e97-623f0a715ee1
        creds:
          type: client
          client_id: acf3f73a-597b-46b6-98d9-748d75018ed0
          client_secret: 1Kb8Q~o3Q2hdEvrul9yaj5DJDFkuL3RG7lger2VQ`,
    },
    {
      id: 'verda',
      label: 'Verda',
      yaml: `projects:
  - name: main
    backends:
      - type: verda
        creds:
          type: api_key
          client_id: xfaHBqYEsArqhKWX-e52x3HH7w8T
          client_secret: B5ZU5Qx9Nt8oGMlmMhNI3iglK8bjMhagTbylZy4WzncZe39995f7Vxh8`,
    },
    {
      id: 'digitalocean',
      label: 'Digital Ocean',
      yaml: `projects:
  - name: main
    backends:
      - type: digitalocean
        project_name: my-digital-ocean-project
        creds:
          type: api_key
          api_key: dop_v1_examplekey3f8a1c9e2b7d6045a1c8e3f9b2d7a6c4e1f0b9d8`,
    },
    {
      id: 'jarvislabs',
      label: 'JarvisLabs',
      yaml: `projects:
  - name: main
    backends:
      - type: jarvislabs
        creds:
          type: api_key
          api_key: jlab_8Kd2Pq7Vn4Rt9Wm3Xy6Zb1Lc5Fg0HsJ4Tn7Vr2Wq9`,
    },
    {
      id: 'cloudrift',
      label: 'CloudRift',
      yaml: `projects:
  - name: main
    backends:
      - type: cloudrift
        creds:
          type: api_key
          api_key: rift_2prgY1d0laOrf2BblTwx2B2d1zcf1zIp4tZYpj5j88qmNgz38pxNlpX3vAo`,
    },
  ] as const
).map(backend => ({ ...backend, yaml: `${BACKEND_HEADER}\n${backend.yaml}` }));

export const clusterConfigs = [
  {
    id: 'kubernetes',
    label: 'Kubernetes',
    yaml: `${BACKEND_HEADER}
projects:
  - name: main
    backends:
      - type: kubernetes

        kubeconfig:
          filename: ~/.kube/config

        contexts:
          - name: gpu-cluster-a
          - name: gpu-cluster-b`,
  },
  {
    id: 'ssh',
    label: 'SSH',
    yaml: `${FLEET_HEADER}
type: fleet
name: my-fleet

placement: cluster

ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/id_rsa
  hosts:
    - 3.255.177.51
    - 3.255.177.52`,
  },
] as const;

// Pad every snippet in a tab group to the same line count so all tabs are equal height. Filler
// lines hold a single space rather than being empty: the highlighter omits the trailing newline
// after the last line, so an empty final line would collapse to zero height. Requires wrapLines
// off (1 line = 1 row), otherwise long values would wrap and break the line-count = height mapping.
export const padYamlToLines = (yaml: string, maxLines: number) =>
  yaml + '\n '.repeat(maxLines - yaml.split('\n').length);

export const maxBackendYamlLines = Math.max(...backendConfigs.map(backend => backend.yaml.split('\n').length));
export const maxClusterYamlLines = Math.max(...clusterConfigs.map(cluster => cluster.yaml.split('\n').length));

// Open-source install commands (uv / pip / Docker), each followed by the
// `dstack server` startup output. Rendered as shell in the "Get started" block.
export const installMethods = [
  {
    id: 'uv',
    label: 'uv',
    code: `$ uv tool install "dstack[all]" -U
$ dstack server

Applying ~/.dstack/server/config.yml...

The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
The server is running at http://127.0.0.1:3000/`,
  },
  {
    id: 'pip',
    label: 'pip',
    code: `$ pip install "dstack[all]" -U
$ dstack server

Applying ~/.dstack/server/config.yml...

The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
The server is running at http://127.0.0.1:3000/`,
  },
  {
    id: 'docker',
    label: 'Docker',
    code: `$ docker run -p 3000:3000 \\
    -v $HOME/.dstack/server/:/root/.dstack/server \\
    dstackai/dstack

Applying ~/.dstack/server/config.yml...

The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
The server is running at http://127.0.0.1:3000/`,
  },
] as const;

export const maxInstallLines = Math.max(...installMethods.map(method => method.code.split('\n').length));
