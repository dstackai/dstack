from dstack._internal.core.backends.vastai.profile_options import VastAIProfileOptions

# TODO: when adding options for the first VM-based backend,
# implement the logic to check idle instances against backend options before reusing.
AnyBackendProfileOptions = VastAIProfileOptions
